"""Event Agent — extracts story events with source tracing."""
from dataclasses import dataclass, field
from typing import Optional

from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT

EVENT_EXTRACTION_PROMPT = """Extract key events from the following story chapter.

For each event, provide:
- title: short descriptive title (1 line)
- event_type: one of conflict | revelation | transition | turning_point | resolution
- description: what happens (1-2 sentences)
- participants: list of character names involved
- location: where the event occurs
- time_marker: approximate time (e.g. "afternoon", "midnight", "next morning")
- cause: what caused this event (if inferable)
- consequence: what this event leads to (if inferable)
- source: the chapter reference

Return a JSON object with an "events" array. Be concise and extract only the most important events (3-8 per chapter)."""


@dataclass
class Event:
    title: str
    event_type: str
    description: str = ""
    participants: list[str] = field(default_factory=list)
    location: str = ""
    time_marker: str = ""
    cause: str = ""
    consequence: str = ""
    source: dict = field(default_factory=dict)


class EventAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract_events(self, chapter_text: str, chapter_id: str, chapter_title: str = "") -> list[Event]:
        """Extract events from a single chapter with source trace."""
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + EVENT_EXTRACTION_PROMPT,
            chapter_text,
        )

        events = []
        for data in response.get("events", []):
            events.append(Event(
                title=data.get("title", ""),
                event_type=data.get("event_type", "transition"),
                description=data.get("description", ""),
                participants=data.get("participants", []),
                location=data.get("location", ""),
                time_marker=data.get("time_marker", ""),
                cause=data.get("cause", ""),
                consequence=data.get("consequence", ""),
                source={"chapter_id": chapter_id, "chapter_title": chapter_title},
            ))
        return events

    def extract_events_from_chapters(self, chapters: list, llm: LLMClient) -> list[Event]:
        """Extract events from multiple chapters."""
        all_events = []
        for ch in chapters:
            if hasattr(ch, "content"):
                chapter_events = self.extract_events(ch.content, ch.id, ch.title)
                all_events.extend(chapter_events)
        return all_events
