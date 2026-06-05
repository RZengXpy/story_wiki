"""OutlineAgent — generates story outline from novel text."""
from dataclasses import dataclass, field
from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, OUTLINE_GENERATION_PROMPT


@dataclass
class ActSummary:
    act_number: int
    title: str
    summary: str
    key_scenes: list[str] = field(default_factory=list)


@dataclass
class StoryOutline:
    genre: str = ""
    theme: str = ""
    main_conflict: str = ""
    arc_summary: str = ""
    act_summaries: list[ActSummary] = field(default_factory=list)
    key_plot_points: list[str] = field(default_factory=list)


class OutlineAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_outline(self, story_text: str) -> StoryOutline:
        """Generate a structured story outline from the full novel text."""
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + OUTLINE_GENERATION_PROMPT,
            story_text,
        )
        outline_data = response.get("outline", {})

        act_summaries = []
        raw_acts = outline_data.get("act_summaries", [])
        if isinstance(raw_acts, list):
            for i, act_data in enumerate(raw_acts, start=1):
                if isinstance(act_data, dict):
                    act_summaries.append(ActSummary(
                        act_number=i,
                        title=act_data.get("title", f"Act {i}"),
                        summary=act_data.get("summary", ""),
                        key_scenes=act_data.get("key_scenes", []),
                    ))
                elif isinstance(act_data, str):
                    act_summaries.append(ActSummary(
                        act_number=i,
                        title=f"Act {i}",
                        summary=act_data,
                        key_scenes=[],
                    ))

        return StoryOutline(
            genre=outline_data.get("genre", ""),
            theme=outline_data.get("theme", ""),
            main_conflict=outline_data.get("main_conflict", ""),
            arc_summary=outline_data.get("arc_summary", ""),
            act_summaries=act_summaries,
            key_plot_points=outline_data.get("key_plot_points", []),
        )
