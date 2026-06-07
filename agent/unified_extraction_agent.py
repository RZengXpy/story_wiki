"""UnifiedExtractionAgent — single-pass, single-LLM-call knowledge extraction per chapter.

Implements think.md Principle III: "Unified Knowledge Extraction"
  Chapter → [ONE LLM call] → Local Knowledge

Output includes:
  - characters / relations / events / scenes
  - chapter_summary / chapter_goal / chapter_conflict (per chapter)
  - Aggregated result joins all chapter summaries/goals/conflicts into global outline

This replaces the previous pattern where multiple agents each re-read the same chapter.
"""
from dataclasses import dataclass, field
from typing import Optional

from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT
from schema.models import Character, Scene, Relation, SourceTrace
from agent.event_agent import Event


UNIFIED_EXTRACTION_PROMPT = """Extract all story knowledge from this chapter in a single pass.

Return a JSON object with exactly these keys:
{
  "characters": [
    {
      "name": "full name (use the name most used in the chapter)",
      "description": "who this character is in 1-2 sentences",
      "traits": ["trait1", "trait2", "trait3"],
      "role": "protagonist | antagonist | supporting"
    }
  ],
  "relations": [
    {
      "from_char": "character A name",
      "to_char": "character B name",
      "relation_type": "family | friend | enemy | romantic | professional | stranger",
      "description": "how this relationship manifests in the story"
    }
  ],
  "events": [
    {
      "title": "short descriptive title (1 line)",
      "event_type": "conflict | revelation | transition | turning_point | resolution",
      "description": "what happens in 1-2 sentences",
      "participants": ["list of character names involved"],
      "location": "where this event occurs",
      "time_marker": "approximate time (e.g. 'afternoon', 'midnight', 'next morning')",
      "cause": "what caused this event (if inferable from the text)",
      "consequence": "what this event leads to (if inferable from the text)"
    }
  ],
  "scenes": [
    {
      "title": "short descriptive title for this scene",
      "location": "where the scene takes place",
      "time_of_day": "day | night | dawn | dusk | afternoon | evening",
      "description": "2-3 sentence visual description of what we see",
      "characters": ["list of character names appearing in this scene"]
    }
  ],
  "chapter_summary": "2-3 sentence summary of what this chapter is about",
  "chapter_goal": "what the protagonist wants to achieve in this chapter",
  "chapter_conflict": "what obstacle or tension prevents that goal in this chapter"
}

IMPORTANT RULES:
- Extract 3-8 events per chapter — focus on the most important ones
- Extract ALL character relationships that are explicitly described or clearly implied
- Extract all distinct scenes (a new scene = different location OR different time OR major shift)
- A character who appears with multiple names should use the most complete/formal name
- If a character's role is unclear, default to "supporting"
- Do NOT invent information not present in the text
- Use consistent character names throughout — if the text uses a nickname and a real name for the same person, use the real name
- chapter_summary/chapter_goal/chapter_conflict are REQUIRED — if unclear, write your best inference
"""


@dataclass
class UnifiedExtractionResult:
    """Result of a single-pass chapter extraction."""
    chapter_id: str = ""
    chapter_title: str = ""
    chapter_summary: str = ""
    chapter_goal: str = ""
    chapter_conflict: str = ""
    characters: list[Character] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


class UnifiedExtractionAgent:
    """Extracts all knowledge types from a chapter in a single LLM call."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def extract(self, chapter_text: str, chapter_id: str, chapter_title: str) -> UnifiedExtractionResult:
        """Extract all knowledge from a chapter in one LLM call.

        This is the core method that implements think.md Principle III:
        - ONE LLM call per chapter (not one per agent type)
        - All knowledge types extracted simultaneously
        - Each item tagged with SourceTrace for traceability
        """
        if not chapter_text.strip():
            return UnifiedExtractionResult()

        if self.llm is None:
            return UnifiedExtractionResult()

        source = SourceTrace(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            char_range=(0, len(chapter_text)),
        )

        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + UNIFIED_EXTRACTION_PROMPT,
            chapter_text,
            temperature=0.3,
        )

        characters = self._build_characters(response.get("characters", []), source)
        scenes = self._build_scenes(response.get("scenes", []), source)
        events = self._build_events(response.get("events", []), chapter_id, chapter_title)
        relations = self._build_relations(response.get("relations", []), source)

        return UnifiedExtractionResult(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            chapter_summary=response.get("chapter_summary", "").strip(),
            chapter_goal=response.get("chapter_goal", "").strip(),
            chapter_conflict=response.get("chapter_conflict", "").strip(),
            characters=characters,
            scenes=scenes,
            events=events,
            relations=relations,
        )

    def _build_characters(self, raw_list: list, source: SourceTrace) -> list[Character]:
        characters = []
        for data in raw_list:
            raw_name = data.get("name", "")
            name = raw_name.strip()
            if not name:  # filter empty/whitespace-only names
                continue
            char = Character(
                name=name,
                description=data.get("description", "").strip(),
                traits=data.get("traits", []),
                role=data.get("role", "supporting"),
                source=source,
            )
            characters.append(char)
        return characters

    def _build_scenes(self, raw_list: list, source: SourceTrace) -> list[Scene]:
        scenes = []
        for data in raw_list:
            raw_title = data.get("title", "")
            title = raw_title.strip()
            if not title:  # filter empty/whitespace-only titles
                continue
            scene = Scene(
                title=title,
                location=data.get("location", "").strip(),
                time_of_day=data.get("time_of_day", "day").strip(),
                description=data.get("description", "").strip(),
                characters=data.get("characters", []),
                notes="",
                source=source,
            )
            scenes.append(scene)
        return scenes

    def _build_events(self, raw_list: list, chapter_id: str, chapter_title: str) -> list[Event]:
        events = []
        for data in raw_list:
            raw_title = data.get("title", "")
            title = raw_title.strip() if isinstance(raw_title, str) else ""
            if not title:
                continue
            event = Event(
                title=title,
                event_type=data.get("event_type", "transition").strip(),
                description=data.get("description", "").strip(),
                participants=data.get("participants", []),
                location=data.get("location", "").strip(),
                time_marker=data.get("time_marker", "").strip(),
                cause=data.get("cause", "").strip(),
                consequence=data.get("consequence", "").strip(),
                source={
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                },
            )
            events.append(event)
        return events

    def _build_relations(self, raw_list: list, source: SourceTrace) -> list[Relation]:
        relations = []
        for data in raw_list:
            from_raw = data.get("from_char", "")
            to_raw = data.get("to_char", "")
            if not from_raw.strip() or not to_raw.strip():
                continue
            rel = Relation(
                from_char=from_raw.strip(),
                to_char=to_raw.strip(),
                relation_type=data.get("relation_type", "stranger").strip(),
                description=data.get("description", "").strip(),
                source=source,
            )
            relations.append(rel)
        return relations


# ── Batch extraction (same agent, multiple chapters sequentially) ──────────────


def extract_all_chapters(
    chapters: list,
    llm: Optional[LLMClient],
    tracker=None,
) -> UnifiedExtractionResult:
    """Extract knowledge from all chapters sequentially.

    Returns a UnifiedExtractionResult with all knowledge from all chapters.
    The aggregated result includes per-chapter summaries/goals/conflicts joined together.
    """
    agent = UnifiedExtractionAgent(llm)

    all_chars: list[Character] = []
    all_scenes: list[Scene] = []
    all_events: list = []
    all_relations: list[Relation] = []
    chapter_summaries: list[str] = []
    chapter_goals: list[str] = []
    chapter_conflicts: list[str] = []

    for idx, ch in enumerate(chapters):
        ch_id = getattr(ch, "id", f"ch_{idx+1:03d}")
        ch_title = getattr(ch, "title", "")
        ch_content = getattr(ch, "content", "")

        if tracker:
            tracker.on_chapter_start(idx, ch_title)

        result = agent.extract(ch_content, ch_id, ch_title)

        all_chars.extend(result.characters)
        all_scenes.extend(result.scenes)
        all_events.extend(result.events)
        all_relations.extend(result.relations)
        if result.chapter_summary:
            chapter_summaries.append(f"第{idx+1}章 {ch_title}: {result.chapter_summary}")
        if result.chapter_goal:
            chapter_goals.append(f"第{idx+1}章 {ch_title}: {result.chapter_goal}")
        if result.chapter_conflict:
            chapter_conflicts.append(f"第{idx+1}章 {ch_title}: {result.chapter_conflict}")

        if tracker:
            tracker.on_chapter_done(idx + 1, ch_title)

    return UnifiedExtractionResult(
        chapter_id="aggregated",
        chapter_title="",
        chapter_summary="\n".join(chapter_summaries),
        chapter_goal="\n".join(chapter_goals),
        chapter_conflict="\n".join(chapter_conflicts),
        characters=all_chars,
        scenes=all_scenes,
        events=all_events,
        relations=all_relations,
    )
