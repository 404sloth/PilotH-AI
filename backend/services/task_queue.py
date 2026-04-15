"""
Task Queue Manager — handles async task execution, retries, and persistence.

Responsibilities:
  - Queue tasks for async execution by agents
  - Persist tasks to SQLite (survives server restarts)
  - Retry failed tasks with exponential backoff
  - Track task status (queued | running | completed | failed | cancelled)
  - Emit progress updates via WebSocket
  - Integrate with LLM for response generation
  - Handle PII data sanitization before logging
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Coroutine

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a single async task."""
    task_id: str
    agent_name: str
    action: str
    payload: Dict[str, Any]
    session_id: Optional[str] = None
    status: TaskStatus = TaskStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    sanitized: bool = False  # PII data has been sanitized

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "action": self.action,
            "payload": self.payload,
            "session_id": self.session_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def duration_secs(self) -> Optional[float]:
        """Return task duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class TaskQueueManager:
    """
    Manages a queue of tasks for async execution.
    Tasks persist to SQLite and survive server restarts.
    """

    def __init__(
        self,
        max_workers: int = 5,
        enable_llm_summaries: bool = True,
        enable_pii_sanitization: bool = True,
    ):
        """
        Initialize task queue.

        Args:
            max_workers: Max concurrent tasks
            enable_llm_summaries: Use LLM to generate final response summaries
            enable_pii_sanitization: Sanitize PII before storing logs
        """
        self.max_workers = max_workers
        self.enable_llm_summaries = enable_llm_summaries
        self.enable_pii_sanitization = enable_pii_sanitization

        self._tasks: Dict[str, Task] = {}
        self._callbacks: List[Callable[[Task], Coroutine[Any, Any, None]]] = []
        self._running_workers = set()
        self._db_ready = False

        # Restore persisted tasks on startup
        self._init_db()
        self._restore_from_db()

    # ── Public API ────────────────────────────────────────────────────────────

    def enqueue(
        self,
        agent_name: str,
        action: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Enqueue a new task.

        Args:
            agent_name: Target agent name
            action: Action to execute
            payload: Input parameters
            session_id: Session context
            max_retries: Retry limit on failure

        Returns:
            task_id (UUID)
        """
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            agent_name=agent_name,
            action=action,
            payload=payload,
            session_id=session_id,
            max_retries=max_retries,
        )

        # Sanitize PII if enabled
        if self.enable_pii_sanitization:
            from observability.pii_sanitizer import sanitize_payload
            task.payload = sanitize_payload(task.payload)
            task.sanitized = True

        self._tasks[task_id] = task
        self._persist_task(task)

        logger.info(
            "[TaskQueue] Enqueued task_id=%s agent=%s action=%s session=%s",
            task_id, agent_name, action, session_id,
        )
        return task_id

    async def process_queue(self) -> None:
        """
        Process queued tasks with concurrency control.
        This should be run in the background (e.g., FastAPI lifespan).
        """
        logger.info("[TaskQueue] Starting processor with max_workers=%d", self.max_workers)

        while True:
            try:
                # Get next queued task
                task = self._get_next_queued_task()
                if not task:
                    await asyncio.sleep(1)  # No tasks, wait
                    continue

                # Spawn worker if under limit
                if len(self._running_workers) < self.max_workers:
                    worker = asyncio.create_task(self._execute_task(task))
                    self._running_workers.add(worker)
                    worker.add_done_callback(self._running_workers.discard)
                else:
                    await asyncio.sleep(0.5)  # Wait for a worker to finish

            except Exception as e:
                logger.exception("[TaskQueue] Processor loop error: %s", e)
                await asyncio.sleep(5)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID (from memory or DB)."""
        task = self._tasks.get(task_id)
        if not task:
            task = self._load_from_db(task_id)
        return task

    def get_tasks_by_session(self, session_id: str) -> List[Task]:
        """Get all tasks for a session."""
        return [t for t in self._tasks.values() if t.session_id == session_id]

    def get_pending_tasks(self) -> List[Task]:
        """Get all queued or running tasks."""
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.RETRYING)
        ]

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued or running task."""
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
            task.status = TaskStatus.CANCELLED
            self._update_db_status(task_id, TaskStatus.CANCELLED)
            logger.info("[TaskQueue] Cancelled task_id=%s", task_id)
            return True
        return False

    def register_callback(
        self,
        fn: Callable[[Task], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Register a callback to be called when a task completes.
        Useful for WebSocket broadcasts.

        fn(task) should be an async function that receives the completed Task.
        """
        self._callbacks.append(fn)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task with retry logic and error handling."""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self._update_db_status(task.task_id, TaskStatus.RUNNING)

        try:
            # Route to agent
            result = await self._route_to_agent(task)

            # Generate LLM summary if enabled
            if self.enable_llm_summaries:
                summary = await self._generate_summary(task, result)
                result["llm_summary"] = summary

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()

            logger.info(
                "[TaskQueue] Completed task_id=%s in %.2fs",
                task.task_id,
                task.duration_secs(),
            )

        except Exception as e:
            task.error = str(e)
            logger.warning(
                "[TaskQueue] Task failed task_id=%s attempt=%d error=%s",
                task.task_id,
                task.retry_count + 1,
                e,
            )

            # Retry with backoff
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                backoff = 2 ** task.retry_count  # Exponential backoff
                logger.info(
                    "[TaskQueue] Retrying task_id=%s in %ds",
                    task.task_id,
                    backoff,
                )
                await asyncio.sleep(backoff)
                # Re-queue by setting status back to QUEUED
                task.status = TaskStatus.QUEUED
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                logger.error(
                    "[TaskQueue] Task exhausted retries task_id=%s",
                    task.task_id,
                )

        finally:
            self._update_db(task)
            await self._notify_callbacks(task)

    async def _route_to_agent(self, task: Task) -> Dict[str, Any]:
        """Route task to the appropriate agent."""
        from backend.services.agent_registry import get_agent

        agent = get_agent(task.agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {task.agent_name}")

        # Call agent's action
        result = await agent.invoke(task.action, task.payload, task.session_id)
        return result

    async def _generate_summary(
        self,
        task: Task,
        result: Dict[str, Any],
    ) -> Optional[str]:
        """
        Use LLM to generate a human-friendly summary of the result.
        PII is redacted before passing to LLM.
        """
        try:
            from llm.model_factory import get_llm
            from observability.pii_sanitizer import sanitize_output

            llm = get_llm()

            # Sanitize result for LLM
            sanitized_result = sanitize_output(result)

            prompt = f"""
Given the following agent action result, provide a brief 2-3 sentence summary suitable
for displaying to a human user. Be clear and concise. Do NOT include any technical jargon
or PII.

Agent: {task.agent_name}
Action: {task.action}
Result: {json.dumps(sanitized_result, indent=2)}

Summary:
"""

            from langchain_core.messages import HumanMessage

            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()

        except Exception as e:
            logger.warning("[TaskQueue] Summary generation failed: %s", e)
            return None

    async def _notify_callbacks(self, task: Task) -> None:
        """Call all registered callbacks with the completed task."""
        for callback in self._callbacks:
            try:
                await callback(task)
            except Exception as e:
                logger.warning("[TaskQueue] Callback failed: %s", e)

    def _get_next_queued_task(self) -> Optional[Task]:
        """Get oldest queued task (FIFO)."""
        queued = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
        if queued:
            queued.sort(key=lambda t: t.created_at)
            return queued[0]
        return None

    # ── Persistence (SQLite) ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create task queue table if it doesn't exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS task_queue (
            task_id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            action TEXT NOT NULL,
            payload TEXT NOT NULL,  -- JSON
            session_id TEXT,
            status TEXT DEFAULT 'queued',
            result TEXT,  -- JSON
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            created_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL,
            sanitized INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_task_status ON task_queue(status);
        CREATE INDEX IF NOT EXISTS idx_task_session ON task_queue(session_id);
        CREATE INDEX IF NOT EXISTS idx_task_agent ON task_queue(agent_name);
        """
        try:
            from integrations.data_warehouse.sqlite_client import get_db_connection

            with get_db_connection() as conn:
                for stmt in ddl.strip().split(";"):
                    s = stmt.strip()
                    if s:
                        conn.execute(s)
                conn.commit()
            self._db_ready = True
            logger.debug("[TaskQueue] Database initialized")
        except Exception as e:
            logger.warning("[TaskQueue] DB init failed: %s", e)

    def _persist_task(self, task: Task) -> None:
        """Insert or update task in database."""
        if not self._db_ready:
            return

        try:
            from integrations.data_warehouse.sqlite_client import get_db_connection

            with get_db_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO task_queue
                       (task_id, agent_name, action, payload, session_id,
                        status, result, error, retry_count, max_retries,
                        created_at, started_at, completed_at, sanitized)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task.task_id,
                        task.agent_name,
                        task.action,
                        json.dumps(task.payload, default=str),
                        task.session_id,
                        task.status.value,
                        json.dumps(task.result, default=str) if task.result else None,
                        task.error,
                        task.retry_count,
                        task.max_retries,
                        task.created_at,
                        task.started_at,
                        task.completed_at,
                        int(task.sanitized),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.debug("[TaskQueue] Failed to persist task: %s", e)

    def _update_db_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status in database."""
        if not self._db_ready:
            return

        try:
            from integrations.data_warehouse.sqlite_client import get_db_connection

            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE task_queue SET status=? WHERE task_id=?",
                    (status.value, task_id),
                )
                conn.commit()
        except Exception as e:
            logger.debug("[TaskQueue] Failed to update status: %s", e)

    def _update_db(self, task: Task) -> None:
        """Update full task record in database."""
        self._persist_task(task)

    def _load_from_db(self, task_id: str) -> Optional[Task]:
        """Load a task from database by ID."""
        if not self._db_ready:
            return None

        try:
            from integrations.data_warehouse.sqlite_client import get_db_connection

            with get_db_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM task_queue WHERE task_id=?",
                    (task_id,),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_task(dict(row))
        except Exception as e:
            logger.debug("[TaskQueue] Failed to load task: %s", e)
        return None

    def _restore_from_db(self) -> None:
        """Load all unfinished tasks from database on startup."""
        if not self._db_ready:
            return

        try:
            from integrations.data_warehouse.sqlite_client import get_db_connection

            with get_db_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM task_queue WHERE status IN ('queued', 'running', 'retrying')"
                )
                rows = cur.fetchall()
                for row in rows:
                    task = self._row_to_task(dict(row))
                    self._tasks[task.task_id] = task

            if len(self._tasks) > 0:
                logger.info(
                    "[TaskQueue] Restored %d unfinished task(s)",
                    len(self._tasks),
                )
        except Exception as e:
            logger.warning("[TaskQueue] Failed to restore tasks: %s", e)

    def _row_to_task(self, row: Dict[str, Any]) -> Task:
        """Convert database row to Task object."""
        return Task(
            task_id=row["task_id"],
            agent_name=row["agent_name"],
            action=row["action"],
            payload=json.loads(row.get("payload") or "{}"),
            session_id=row.get("session_id"),
            status=TaskStatus(row.get("status", "queued")),
            result=json.loads(row.get("result") or "null") if row.get("result") else None,
            error=row.get("error"),
            retry_count=row.get("retry_count", 0),
            max_retries=row.get("max_retries", 3),
            created_at=row.get("created_at", time.time()),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            sanitized=bool(row.get("sanitized", 0)),
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_queue_manager: Optional[TaskQueueManager] = None


def get_task_queue() -> TaskQueueManager:
    """Return the process-global TaskQueueManager singleton."""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = TaskQueueManager()
    return _queue_manager
