from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, SCENE_PARSING_PROMPT
from schema.models import Scene, SourceTrace


class SceneAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def parse_scenes(self, story_text: str) -> list[Scene]:
        """Parse scenes from full text (legacy, single-pass)."""
        return self.parse_from_text(story_text)

    def parse_from_text(self, story_text: str) -> list[Scene]:
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + SCENE_PARSING_PROMPT,
            story_text,
        )
        scenes = []
        for data in response.get("scenes", []):
            scenes.append(Scene(
                title=data.get("title", ""),
                location=data.get("location", ""),
                time_of_day=data.get("time_of_day", "day"),
                description=data.get("description", ""),
                characters=data.get("characters", []),
                notes=data.get("notes", ""),
            ))
        return scenes

    def parse_from_chapters(self, chapters: list, llm: LLMClient) -> list[Scene]:
        """Parse scenes chapter-by-chapter, each tagged with source."""
        all_scenes = []
        for ch in chapters:
            if hasattr(ch, "content") and ch.content.strip():
                scenes = self.parse_from_text(ch.content)
                for s in scenes:
                    s.source = SourceTrace(
                        chapter_id=ch.id,
                        chapter_title=ch.title,
                        char_range=(ch.start_char, ch.end_char),
                    )
                all_scenes.extend(scenes)
        return all_scenes
