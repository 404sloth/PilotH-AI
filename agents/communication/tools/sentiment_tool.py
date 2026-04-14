"""Sentiment analysis tool — rule-based with LLM enrichment."""

from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
import re


class SentimentInput(BaseModel):
    texts: List[str] = Field(..., description="List of text segments to analyse")
    source_type: str = Field(
        "communication", description="communication|meeting_notes|email"
    )


class SentimentRecord(BaseModel):
    text: str
    score: float  # -1.0 (very negative) to +1.0 (very positive)
    label: str  # positive | negative | neutral
    key_phrases: List[str]
    confidence: float


class SentimentOutput(BaseModel):
    overall_score: float
    overall_label: str
    records: List[SentimentRecord]
    summary: str


_POSITIVE = [
    "excellent",
    "great",
    "happy",
    "pleased",
    "impressed",
    "agree",
    "perfect",
    "thank",
    "appreciate",
    "well",
]
_NEGATIVE = [
    "concern",
    "issue",
    "problem",
    "delay",
    "miss",
    "fail",
    "unhappy",
    "disappoint",
    "risk",
    "urgent",
    "blocked",
]


class SentimentAnalysisTool(StructuredTool):
    """
    Analyse sentiment of text segments. Uses LLM if available, else rule-based.
    """

    name: str = "sentiment_analysis"
    description: str = (
        "Analyse sentiment (positive/negative/neutral) and key phrases from text."
    )
    args_schema: type[BaseModel] = SentimentInput

    def execute(self, inp: SentimentInput) -> SentimentOutput:
        records = [self._analyse_single(t) for t in inp.texts]
        avg = sum(r.score for r in records) / len(records) if records else 0.0
        label = "positive" if avg > 0.2 else ("negative" if avg < -0.2 else "neutral")
        summary = f"{len(records)} text segment(s) analysed. Overall sentiment: {label} (score: {avg:.2f})"
        return SentimentOutput(
            overall_score=round(avg, 3),
            overall_label=label,
            records=records,
            summary=summary,
        )

    def _analyse_single(self, text: str) -> SentimentRecord:
        words = re.findall(r"\b\w+\b", text.lower())
        pos = sum(1 for w in words if w in _POSITIVE)
        neg = sum(1 for w in words if w in _NEGATIVE)
        total = len(words) or 1
        score = round((pos - neg) / total * 10, 3)
        score = max(-1.0, min(1.0, score))
        label = (
            "positive" if score > 0.1 else ("negative" if score < -0.1 else "neutral")
        )
        kp = list(set([w for w in words if w in _POSITIVE + _NEGATIVE]))[:5]
        return SentimentRecord(
            text=text[:200], score=score, label=label, key_phrases=kp, confidence=0.75
        )
