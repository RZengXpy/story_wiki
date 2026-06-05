from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, CHARACTER_EXTRACTION_PROMPT
from schema.models import Character, SourceTrace


class CharacterAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract_characters(self, story_text: str) -> list[Character]:
        """Extract characters from full text (legacy, single-pass)."""
        return self.extract_from_text(story_text)

    def extract_from_text(self, story_text: str) -> list[Character]:
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

    def extract_from_chapters(self, chapters: list, llm: LLMClient) -> list[Character]:
        """Extract characters chapter-by-chapter, each tagged with source."""
        all_chars = []
        for ch in chapters:
            if hasattr(ch, "content") and ch.content.strip():
                chars = self.extract_from_text(ch.content)
                for c in chars:
                    c.source = SourceTrace(
                        chapter_id=ch.id,
                        chapter_title=ch.title,
                        char_range=(ch.start_char, ch.end_char),
                    )
                all_chars.extend(chars)
        return all_chars
