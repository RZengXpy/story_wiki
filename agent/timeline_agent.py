"""TimelineAgent — builds and refines story timeline with causal inference.

Implements "Local → Global" and "Explainable" principles from think.md.
"""
from dataclasses import dataclass, field
from typing import Optional
from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT


TIMELINE_INFERENCE_PROMPT = """Analyze the following story events and infer the causal relationships between them.

For each event pair where one event leads to another, identify:
- cause_event: the event that triggers the chain
- effect_event: the event that follows
- causal_link: brief description of how the cause leads to the effect

Also determine the overall story timeline and identify:
- inciting_incident: the event that sets the main plot in motion
- climax: the event of highest tension
- resolution: the final event that concludes the story

Return a JSON object with:
- causal_chains: list of {cause_event, effect_event, causal_link}
- inciting_incident: name of the inciting incident event
- climax_event: name of the climax event
- resolution_event: name of the resolution event
- narrative_pacing_notes: any observations about pacing"""


@dataclass
class TimelineEntry:
    """A single entry in the story timeline."""
    time_marker: str
    location: str
    event_title: str
    event_type: str
    participants: list[str] = field(default_factory=list)
    chapter_title: str = ""
    causal_predecessors: list[str] = field(default_factory=list)
    causal_successors: list[str] = field(default_factory=list)


@dataclass
class TimelineResult:
    """Complete timeline analysis result."""
    entries: list[TimelineEntry]
    causal_chains: list[dict] = field(default_factory=list)
    inciting_incident: str = ""
    climax_event: str = ""
    resolution_event: str = ""
    pacing_notes: str = ""


_TIME_ORDER = {
    "黎明": 0, "凌晨": 0, "清晨": 1, "早晨": 1, "早上": 1, "上午": 2,
    "中午": 3, "午间": 3, "午后": 3,
    "下午": 4, "傍晚": 5, "黄昏": 5,
    "晚上": 6, "夜里": 7, "深夜": 8, "午夜": 8,
}


class TimelineAgent:
    """Builds and refines story timeline from events with optional causal inference."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def build_timeline(
        self,
        events: list,
        chapter_titles: dict[str, str],
    ) -> list[TimelineEntry]:
        """Build sorted timeline from events using time_marker (rule-based fallback)."""
        timeline: list[TimelineEntry] = []
        for e in events:
            e_dict = e if isinstance(e, dict) else e.__dict__
            marker = e_dict.get("time_marker", "")
            src = e_dict.get("source", {}) if isinstance(e_dict.get("source"), dict) else {}
            cid = src.get("chapter_id", "") if isinstance(src, dict) else ""
            chapter_title = chapter_titles.get(cid, "")
            timeline.append(TimelineEntry(
                time_marker=marker or "未标注",
                location=e_dict.get("location", ""),
                event_title=e_dict.get("title", ""),
                event_type=e_dict.get("event_type", ""),
                participants=e_dict.get("participants", []),
                chapter_title=chapter_title,
            ))
        timeline.sort(key=lambda x: (_TIME_ORDER.get(x.time_marker, 50), x.chapter_title, x.event_title))
        return timeline

    def infer_causal_chains(
        self,
        events: list,
        timeline: list[TimelineEntry],
    ) -> TimelineResult:
        """Use LLM to infer causal relationships between events.

        Falls back to rule-based timeline if no LLM client is available.
        """
        if self.llm is None:
            # No LLM: return rule-based timeline without causal chains
            return TimelineResult(entries=timeline)

        # Build event summaries for LLM context
        event_summaries = []
        for e in events:
            e_dict = e if isinstance(e, dict) else e.__dict__
            event_summaries.append(
                f"- [{e_dict.get('event_type', 'transition')}] "
                f"{e_dict.get('title', 'Unknown')}: "
                f"{e_dict.get('description', '')}"
            )

        event_text = "\n".join(event_summaries)
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + TIMELINE_INFERENCE_PROMPT,
            event_text,
        )

        cause_chains = response.get("causal_chains", [])

        # Annotate timeline entries with causal predecessors/successors
        cause_map: dict[str, list[str]] = {}
        effect_map: dict[str, list[str]] = {}
        for chain in cause_chains:
            cause = chain.get("cause_event", "")
            effect = chain.get("effect_event", "")
            if cause and effect:
                cause_map.setdefault(cause, []).append(effect)
                effect_map.setdefault(effect, []).append(cause)

        for entry in timeline:
            entry.causal_predecessors = effect_map.get(entry.event_title, [])
            entry.causal_successors = cause_map.get(entry.event_title, [])

        return TimelineResult(
            entries=timeline,
            causal_chains=cause_chains,
            inciting_incident=response.get("inciting_incident", ""),
            climax_event=response.get("climax_event", ""),
            resolution_event=response.get("resolution_event", ""),
            pacing_notes=response.get("narrative_pacing_notes", ""),
        )

    def analyze(self, events: list, chapter_titles: dict[str, str]) -> TimelineResult:
        """Full timeline analysis: build + causal inference."""
        timeline = self.build_timeline(events, chapter_titles)
        return self.infer_causal_chains(events, timeline)
