from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, SCRIPT_WRITING_PROMPT, STORY_STRUCTURE_PROMPT
from schema.models import Script, Act


class ScriptAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def analyze_structure(self, story_text: str) -> list[Act]:
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + STORY_STRUCTURE_PROMPT,
            story_text,
        )
        acts = []
        for data in response.get("acts", []):
            act = Act(title=data.get("title", ""))
            acts.append(act)
        return acts

    def write_screenplay(self, story_text: str, genre: str = "general") -> str:
        return self.llm.generate(
            SYSTEM_PROMPT + "\n\n" + SCRIPT_WRITING_PROMPT,
            f"Genre: {genre}\n\nStory:\n{story_text}",
            temperature=0.7,
        )