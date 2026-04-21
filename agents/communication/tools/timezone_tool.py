"""Timezone converter tool."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class TimezoneInput(BaseModel):
    datetime_str: str = Field(..., description="ISO 8601 datetime string")
    from_tz: str = Field(..., description="Source timezone (e.g. Asia/Kolkata)")
    to_tz: str = Field(..., description="Target timezone (e.g. America/New_York)")
    to_human: bool = Field(True, description="Return human-readable string")


class TimezoneOutput(BaseModel):
    input_datetime: str
    from_tz: str
    to_tz: str
    converted: str
    human_readable: Optional[str] = None
    offset_hours: Optional[float] = None


from langchain_core.runnables import RunnableConfig


class TimezoneConverterTool(StructuredTool):
    """Convert a datetime string from one timezone to another."""

    name: str = "timezone_converter"
    description: str = (
        "Convert a datetime between timezones. Handles DST automatically."
    )
    args_schema: type[BaseModel] = TimezoneInput

    def execute(
        self, inp: TimezoneInput, config: Optional[RunnableConfig] = None
    ) -> TimezoneOutput:
        try:
            from datetime import datetime

            try:
                import zoneinfo

                from_zone = zoneinfo.ZoneInfo(inp.from_tz)
                to_zone = zoneinfo.ZoneInfo(inp.to_tz)
            except ImportError:
                # Python < 3.9 fallback
                from dateutil import tz as dateutil_tz

                from_zone = dateutil_tz.gettz(inp.from_tz)
                to_zone = dateutil_tz.gettz(inp.to_tz)

            # Parse
            dt_str = inp.datetime_str.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(dt_str)
            except ValueError:
                dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=from_zone)
            else:
                dt = dt.astimezone(from_zone)

            converted = dt.astimezone(to_zone)
            offset = (
                converted.utcoffset().total_seconds() / 3600
                if converted.utcoffset()
                else None
            )

            human = (
                converted.strftime("%A, %d %B %Y at %I:%M %p %Z")
                if inp.to_human
                else None
            )

            return TimezoneOutput(
                input_datetime=inp.datetime_str,
                from_tz=inp.from_tz,
                to_tz=inp.to_tz,
                converted=converted.isoformat(),
                human_readable=human,
                offset_hours=offset,
            )
        except Exception as e:
            return TimezoneOutput(
                input_datetime=inp.datetime_str,
                from_tz=inp.from_tz,
                to_tz=inp.to_tz,
                converted=inp.datetime_str,
                human_readable=f"Conversion failed: {e}",
            )
