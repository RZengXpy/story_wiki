from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, CHARACTER_EXTRACTION_PROMPT
from schema.models import Character


class CharacterAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract_characters(self, story_text: str) -> list[Character]:
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + CHARACTER_EXTRACTION_PROMPT,
            story_text,
        )
        characters = []
        for data in response.get("characters", []):
            characters.append(Character(
                name=data["name"],
                description=data.get("description", ""),
                traits=data.get("traits", []),
                role=data.get("role", "supporting"),
            ))
        return characters