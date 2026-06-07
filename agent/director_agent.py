"""Director Agent — generates Screenplay Bible from SKL.

Architectural position:
  SKL (from Governance) → Director Agent → Screenplay Bible → Script Agent (parallel)

This is the FIRST LLM call at the screenplay generation stage.
It establishes the creative vision and constraints that all scene scripts will follow,
implementing the "Bible-First" principle of professional screenwriting.

Screenplay Bible contains:
  - genre, tone, visual style
  - story structure (act breakdown)
  - character portraits (from SKL)
  - themes and motifs
  - setting/atmosphere
  - dialogue style guidelines
"""
from dataclasses import dataclass, field
from typing import Optional

from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT


DIRECTOR_AGENT_PROMPT = """You are a professional film director and screenwriter.
Based on the story knowledge below, generate a comprehensive Screenplay Bible.

The Bible establishes the creative vision that will guide all scene writing.
Be specific and concrete — avoid generic advice.

Return a JSON object with these keys:
{
  "genre": "primary genre (e.g. 'psychological thriller', 'period drama', 'noir mystery')",
  "subgenre": "subgenre or blend if applicable",
  "tone": "overall emotional register (e.g. 'suspenseful and atmospheric', 'intimate and melancholic')",
  "visual_style": "camera and visual approach (e.g. ' handheld for tension', 'wide establishing shots')",
  "setting_period": "time and place of the story",
  "atmosphere": "dominant mood and sensory details (2-3 key atmospheric elements)",
  "themes": ["list of 2-4 central themes with brief explanations"],
  "motifs": ["list of 2-3 visual/narrative motifs that recur throughout"],
  "act_breakdown": {
    "act1": "what establishes the world, character, and central conflict in ~25% of runtime",
    "act2": "how the conflict escalates, complicates, and forces character change in ~50% of runtime",
    "act3": "how the conflict resolves (or deliberately doesn't) in ~25% of runtime"
  },
  "character_portraits": [
    {
      "name": "character name",
      "role": "protagonist | antagonist | supporting",
      "psychology": "2-3 sentence psychological portrait",
      "speech_pattern": "how they talk (dialect, formality, tics, catchphrases)",
      "visual_appearance": "key visual descriptors for casting/direction"
    }
  ],
  "dialogue_style": "overall dialogue philosophy (e.g. 'subtext-heavy, characters rarely say what they mean directly')",
  "pacing_notes": "how the story beats — slow tension vs. action, where it breathes, where it accelerates",
  "target_runtime": "estimated runtime in minutes",
  "rating_approach": "target age rating and content approach (e.g. 'PG-13, intensity through implication not gore')"
}"""


@dataclass
class ScreenplayBible:
    """The creative vision document produced by the Director Agent."""
    genre: str = ""
    subgenre: str = ""
    tone: str = ""
    visual_style: str = ""
    setting_period: str = ""
    atmosphere: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    motifs: list[str] = field(default_factory=list)
    act_breakdown: dict = field(default_factory=dict)
    character_portraits: list[dict] = field(default_factory=list)
    dialogue_style: str = ""
    pacing_notes: str = ""
    target_runtime: str = ""
    rating_approach: str = ""

    def to_dict(self) -> dict:
        return {
            "genre": self.genre,
            "subgenre": self.subgenre,
            "tone": self.tone,
            "visual_style": self.visual_style,
            "setting_period": self.setting_period,
            "atmosphere": self.atmosphere,
            "themes": self.themes,
            "motifs": self.motifs,
            "act_breakdown": self.act_breakdown,
            "character_portraits": self.character_portraits,
            "dialogue_style": self.dialogue_style,
            "pacing_notes": self.pacing_notes,
            "target_runtime": self.target_runtime,
            "rating_approach": self.rating_approach,
        }


def _build_skl_summary(gsk) -> str:
    """Build a compact text summary of the SKL for the Director Agent prompt."""
    lines = []

    # Title and metadata
    lines.append(f"# {gsk.title or 'Untitled Story'}")
    if gsk.outline:
        o = gsk.outline
        if o.get("genre"):
            lines.append(f"Genre: {o['genre']}")
        if o.get("theme"):
            lines.append(f"Theme: {o['theme']}")
        if o.get("main_conflict"):
            lines.append(f"Main Conflict: {o['main_conflict']}")

    # Characters
    lines.append(f"\n## Characters ({len(gsk.characters)})")
    for c in gsk.characters:
        role_tag = f"[{c.role}]" if hasattr(c, 'role') else ""
        lines.append(f"- {c.name} {role_tag}: {c.description}")
        if hasattr(c, 'traits') and c.traits:
            lines.append(f"  Traits: {', '.join(c.traits)}")

    # Events summary
    if gsk.events:
        lines.append(f"\n## Key Events ({len(gsk.events)})")
        event_types = {}
        for e in gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            t = e_dict.get("event_type", "unknown")
            event_types[t] = event_types.get(t, 0) + 1
        lines.append(f"Event types: {event_types}")
        for e in gsk.events[:10]:
            e_dict = e if isinstance(e, dict) else {}
            lines.append(f"- [{e_dict.get('event_type', '')}] {e_dict.get('title', '')}: {e_dict.get('description', '')[:80]}")

    # Scenes
    if gsk.scenes:
        lines.append(f"\n## Scenes ({len(gsk.scenes)})")
        for s in gsk.scenes:
            loc = s.location or "unknown"
            chars = ", ".join(s.characters[:3]) if hasattr(s, 'characters') else ""
            lines.append(f"- {s.title}: {loc} ({chars})")

    # Relations
    if gsk.relations:
        lines.append(f"\n## Relationships ({len(gsk.relations)})")
        for r in gsk.relations[:8]:
            lines.append(f"- {r.from_char} --[{r.relation_type}]--> {r.to_char}: {r.description[:50]}")

    # Locations
    if gsk.locations:
        lines.append(f"\n## Locations")
        for loc in gsk.locations[:5]:
            name = getattr(loc, 'name', str(loc))
            freq = getattr(loc, 'frequency', 0)
            lines.append(f"- {name} (appears {freq}x)")

    # Timeline
    if gsk.timeline:
        lines.append(f"\n## Timeline ({len(gsk.timeline)} events)")
        for entry in gsk.timeline[:5]:
            tm = getattr(entry, 'time_marker', '?')
            ev = getattr(entry, 'event_title', '?')
            lines.append(f"- {tm}: {ev}")

    return "\n".join(lines)


class DirectorAgent:
    """Generates Screenplay Bible from Story Knowledge (SKL)."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def create_bible(self, gsk) -> ScreenplayBible:
        """Generate a Screenplay Bible from the global story knowledge.

        This is ONE LLM call at the beginning of the screenplay generation stage.
        The Bible then guides all parallel scene generation.

        Args:
            gsk: GlobalStoryKnowledge instance (from Knowledge Merger + Governance)

        Returns:
            ScreenplayBible with creative vision for the screenplay
        """
        if self.llm is None:
            return ScreenplayBible()

        skl_summary = _build_skl_summary(gsk)
        user_prompt = f"Story Knowledge:\n{skl_summary}"

        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + DIRECTOR_AGENT_PROMPT,
            user_prompt,
            temperature=0.5,
        )

        return ScreenplayBible(
            genre=response.get("genre", "general"),
            subgenre=response.get("subgenre", ""),
            tone=response.get("tone", ""),
            visual_style=response.get("visual_style", ""),
            setting_period=response.get("setting_period", ""),
            atmosphere=response.get("atmosphere", []),
            themes=response.get("themes", []),
            motifs=response.get("motifs", []),
            act_breakdown=response.get("act_breakdown", {}),
            character_portraits=response.get("character_portraits", []),
            dialogue_style=response.get("dialogue_style", ""),
            pacing_notes=response.get("pacing_notes", ""),
            target_runtime=response.get("target_runtime", ""),
            rating_approach=response.get("rating_approach", ""),
        )
