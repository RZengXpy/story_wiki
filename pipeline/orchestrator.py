from core.llm_client import LLMClient
from agent.character_agent import CharacterAgent
from agent.scene_agent import SceneAgent
from agent.script_agent import ScriptAgent
from schema.models import Script


class StoryPipeline:
    def __init__(self, llm_client: LLMClient):
        self.char_agent = CharacterAgent(llm_client)
        self.scene_agent = SceneAgent(llm_client)
        self.script_agent = ScriptAgent(llm_client)

    def run(self, novel_text: str, genre: str = "general") -> dict:
        characters = self.char_agent.extract_characters(novel_text)
        scenes = self.scene_agent.parse_scenes(novel_text)
        screenplay = self.script_agent.write_screenplay(novel_text, genre)
        return {
            "characters": characters,
            "scenes": scenes,
            "screenplay": screenplay,
        }