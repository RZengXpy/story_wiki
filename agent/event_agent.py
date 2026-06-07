"""Event Agent — event extraction + causal governance.

Provides two sets of capabilities:
  1. Extraction: extract events from chapter text (used by UnifiedExtractionAgent)
  2. Governance: merge duplicate events, build causal chains,
     identify key events (inciting incident, climax, resolution).

Implements think.md Principle IV: "Agent 负责治理而非抽取"
"""
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT

if TYPE_CHECKING:
    from core.knowledge_merger import GlobalStoryKnowledge


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
    """Event extraction and causal governance agent."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    # ── Extraction ───────────────────────────────────────────────────────

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
            if hasattr(ch, "content") and ch.content.strip():
                chapter_events = self.extract_events(ch.content, ch.id, ch.title)
                all_events.extend(chapter_events)
        return all_events

    # ── Governance (think.md Principle IV) ────────────────────────────────

    def merge_events(self, gsk: "GlobalStoryKnowledge") -> list[dict]:
        """Deduplicate events by title within the SKL. Returns audit records."""
        audit = []
        seen_titles: dict[str, int] = {}
        to_remove: list[int] = []

        for idx, e in enumerate(gsk.events):
            e_dict = e if isinstance(e, dict) else {}
            title = e_dict.get("title", "").strip()
            if not title:
                continue

            if title in seen_titles:
                existing_idx = seen_titles[title]
                existing = gsk.events[existing_idx]
                existing_dict = existing if isinstance(existing, dict) else {}
                # Merge: keep longer description, merge participants
                existing_participants = set(existing_dict.get("participants", []))
                new_participants = set(e_dict.get("participants", []))
                merged = existing_participants | new_participants
                if isinstance(existing, dict):
                    existing["participants"] = list(merged)
                # Keep description that is longer
                if len(e_dict.get("description", "")) > len(existing_dict.get("description", "")):
                    if isinstance(existing, dict):
                        existing["description"] = e_dict.get("description", "")
                audit.append({
                    "action": "merge_event",
                    "title": title,
                    "merged_indices": [existing_idx, idx],
                })
                to_remove.append(idx)
            else:
                seen_titles[title] = idx

        for idx in reversed(to_remove):
            gsk.events.pop(idx)
        return audit

    def build_causal_chains(self, gsk: "GlobalStoryKnowledge") -> list[dict]:
        """Build causal chains between events.

        Returns a list of {cause, effect, link} chains.
        Uses the cause/consequence fields already present in events.
        Deduplicates chains where cause==effect.
        """
        chains = []
        seen: set[tuple[str, str]] = set()

        for e in gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            cause = e_dict.get("cause", "").strip()
            consequence = e_dict.get("consequence", "").strip()
            title = e_dict.get("title", "")

            # cause → current event
            if cause:
                key = (cause, title)
                if key not in seen:
                    seen.add(key)
                    chains.append({
                        "cause_event": cause,
                        "effect_event": title,
                        "causal_link": f"'{cause}' leads to '{title}'",
                        "direction": "cause_to_effect",
                    })
            # current event → consequence
            if consequence:
                key = (title, consequence)
                if key not in seen:
                    seen.add(key)
                    chains.append({
                        "cause_event": title,
                        "effect_event": consequence,
                        "causal_link": f"'{title}' leads to '{consequence}'",
                        "direction": "effect_to_consequence",
                    })

        return chains

    def identify_key_events(self, gsk: "GlobalStoryKnowledge") -> dict:
        """Identify key narrative events: inciting incident, climax, resolution.

        Strategy:
        - Inciting incident: earliest "turning_point" or "revelation" event
        - Climax: event with "turning_point" type OR most participants
        - Resolution: event with "resolution" type
        """
        result = {
            "inciting_incident": None,
            "climax": None,
            "resolution": None,
        }

        if not gsk.events:
            return result

        # Group by type
        by_type: dict[str, list] = {"turning_point": [], "revelation": [], "resolution": [], "conflict": []}

        for idx, e in enumerate(gsk.events):
            e_dict = e if isinstance(e, dict) else {}
            e_type = e_dict.get("event_type", "")
            if e_type in by_type:
                by_type[e_type].append((idx, e_dict))

        # Inciting incident: earliest turning_point or revelation
        if by_type["turning_point"]:
            result["inciting_incident"] = by_type["turning_point"][0][1].get("title", "")
        elif by_type["revelation"]:
            result["inciting_incident"] = by_type["revelation"][0][1].get("title", "")

        # Climax: turning_point with most participants, or most participants overall
        best_climax = None
        best_participants = 0
        for idx, e_dict in by_type["turning_point"] + by_type["conflict"]:
            n = len(e_dict.get("participants", []))
            if n > best_participants:
                best_participants = n
                best_climax = e_dict.get("title", "")
        if best_climax:
            result["climax"] = best_climax

        # Resolution: resolution type event
        if by_type["resolution"]:
            result["resolution"] = by_type["resolution"][0][1].get("title", "")

        return result

    def filter_key_events(self, gsk: "GlobalStoryKnowledge", threshold: int = 3) -> list:
        """Filter to only events with threshold+ participants (important events)."""
        key = []
        for e in gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            if len(e_dict.get("participants", [])) >= threshold:
                key.append(e_dict)
        return key
