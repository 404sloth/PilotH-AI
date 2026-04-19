"""Email draft tool — LLM-driven email generation."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from tools.base_tool import StructuredTool


class EmailDraftInput(BaseModel):
    email_type: str = Field(..., description="followup|invite|summary|reminder|agenda")
    recipients: List[str] = Field(..., description="Recipient names or emails")
    subject: Optional[str] = None
    context: str = Field(..., description="Meeting context, action items, notes")
    sender_name: Optional[str] = "The Meeting Organiser"
    tone: str = Field(
        "professional", description="professional|friendly|formal|concise"
    )


class EmailDraftOutput(BaseModel):
    subject: str
    body: str
    to: List[str]
    cc: List[str] = []
    preview: str = ""


class EmailDraftTool(StructuredTool):
    """Generate a professional email draft using LLM based on meeting context."""

    name: str = "email_draft"
    description: str = (
        "Draft a meeting-related email (follow-up, invite, summary) using AI."
    )
    args_schema: type[BaseModel] = EmailDraftInput

    def execute(self, inp: EmailDraftInput, config: Optional[RunnableConfig] = None) -> EmailDraftOutput:
        subject = (
            inp.subject or f"[{inp.email_type.replace('_', ' ').title()}] Meeting Notes"
        )

        prompt = f"""You are a {inp.tone} business communication assistant. Write an email.

Type: {inp.email_type}
Recipients: {", ".join(inp.recipients)}
From: {inp.sender_name}
Context: {inp.context}

Return ONLY the email body text (no subject line). Keep it concise and actionable."""

        body = self._call_llm(prompt, config)

        return EmailDraftOutput(
            subject=subject,
            body=body,
            to=inp.recipients,
            preview=body[:120] + "..." if len(body) > 120 else body,
        )

    def _call_llm(self, prompt: str, config: Optional[RunnableConfig] = None) -> str:
        try:
            from llm.model_factory import get_llm
            from langchain_core.messages import HumanMessage

            llm = get_llm(temperature=0.4)
            return llm.invoke([HumanMessage(content=prompt)], config=config).content.strip()
        except Exception:
            return (
                "Dear Team,\n\nThank you for joining today's meeting. "
                "Please review the action items assigned to you and update the status by the due dates.\n\n"
                "Best regards,\nThe Meeting Organiser"
            )
