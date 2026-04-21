"""Slack notifier tool — mock implementation ready for real Slack API."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
import logging

logger = logging.getLogger(__name__)


class SlackInput(BaseModel):
    channel: str = Field(
        ..., description="Slack channel or user handle (e.g. #general or @james)"
    )
    message: str = Field(..., description="Message text (supports Slack markdown)")
    mentions: List[str] = Field(
        default_factory=list, description="Slack handles to mention"
    )
    blocks: Optional[dict] = None  # Slack Block Kit JSON (optional)


class SlackOutput(BaseModel):
    sent: bool
    channel: str
    ts: Optional[str] = None  # Slack message timestamp
    permalink: Optional[str] = None
    mock: bool = True


from langchain_core.runnables import RunnableConfig


class SlackNotifierTool(StructuredTool):
    """
    Send a Slack notification.
    Mock: logs the message and returns success.
    Production: replace _send with real slack_sdk call.
    """

    name: str = "slack_notifier"
    description: str = (
        "Send a Slack message to a channel or user with optional @mentions."
    )
    args_schema: type[BaseModel] = SlackInput

    def execute(
        self, inp: SlackInput, config: Optional[RunnableConfig] = None
    ) -> SlackOutput:
        mention_str = " ".join(f"<@{h.lstrip('@')}>" for h in inp.mentions)
        full_msg = f"{mention_str} {inp.message}".strip()

        return self._send(inp.channel, full_msg)

    def _send(self, channel: str, message: str) -> SlackOutput:
        # PRODUCTION: Replace with real implementation:
        # from slack_sdk import WebClient
        # client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        # resp = client.chat_postMessage(channel=channel, text=message)
        # return SlackOutput(sent=True, channel=channel, ts=resp["ts"], mock=False)

        logger.info("[SLACK MOCK] → %s: %s", channel, message[:120])
        return SlackOutput(
            sent=True, channel=channel, ts=f"mock.{id(message)}", mock=True
        )
