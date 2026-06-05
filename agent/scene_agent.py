from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, SCENE_PARSING_PROMPT
from schema.models import Scene


class SceneAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def parse_scenes(self, story_text: str) -> list[Scene]:
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