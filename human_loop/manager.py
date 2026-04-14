from langgraph.errors import NodeInterrupt
import uuid

class HITLManager:
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        self.pending = {}

    def request_approval(self, state: dict, context: str) -> str:
        approval_id = str(uuid.uuid4())
        self.pending[approval_id] = {"state": state, "context": context}
        raise NodeInterrupt(f"Approval required: {approval_id}")

    def resume(self, approval_id: str, decision: bool, feedback: str = ""):
        task = self.pending.pop(approval_id)
        task["state"]["human_decision"] = decision
        task["state"]["human_feedback"] = feedback
        return task["state"]