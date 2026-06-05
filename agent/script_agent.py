"""ScriptAgent — converts story knowledge (SKL) into structured screenplay YAML."""
from typing import Optional
from core.llm_client import LLMClient
from core.prompts import (
    SYSTEM_PROMPT,
    SCRIPT_WRITING_PROMPT,
    STORY_STRUCTURE_PROMPT,
    SCENE_SCREENPLAY_PROMPT,
)
from core.story_graph import ScriptNode, ScriptItem


class ScriptAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def analyze_structure(self, story_text: str) -> list[dict]:
        """Analyze story structure, returns list of acts."""
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + STORY_STRUCTURE_PROMPT,
            story_text,
        )
        return response.get("acts", [])

    def write_screenplay(self, story_text: str, genre: str = "general") -> str:
        """Write a full screenplay from raw story text (legacy method)."""
        return self.llm.generate(
            SYSTEM_PROMPT + "\n\n" + SCRIPT_WRITING_PROMPT,
            f"Genre: {genre}\n\nStory:\n{story_text}",
            temperature=0.7,
        )

    def write_scene(
        self,
        scene_title: str,
        scene_location: str,
        scene_time: str,
        characters_present: list[str],
        scene_summary: str,
        skl_context: dict,
    ) -> ScriptNode:
        """Generate screenplay content for a single scene using SKL context."""
        # Build character context
        char_lines = []
        for c in skl_context.get("characters", []):
            name = c.get("name", "")
            if name in characters_present:
                desc = c.get("description", "")
                traits = ", ".join(c.get("traits", []))
                role = c.get("role", "supporting")
                char_lines.append(f"- {name} ({role}): {desc} | Traits: {traits}")

        # Build event context
        event_lines = []
        for e in skl_context.get("events", []):
            event_lines.append(f"- [{e.get('event_type', '')}] {e.get('title', '')}: {e.get('description', '')}")

        # Build relation context
        rel_lines = []
        for r in skl_context.get("relations", []):
            fc, tc = r.get("from_char", ""), r.get("to_char", "")
            if fc in characters_present or tc in characters_present:
                rel_lines.append(f"- {fc} --[{r.get('relation_type', '')}]--> {tc}: {r.get('description', '')}")

        user_prompt = f"""Scene: {scene_title}
Location: {scene_location}
Time: {scene_time}
Characters: {', '.join(characters_present)}

Scene summary: {scene_summary}

Characters in this story:
{chr(10).join(char_lines) if char_lines else "(no character details available)"}

Related events:
{chr(10).join(event_lines) if event_lines else "(no related events)"}

Relevant relationships:
{chr(10).join(rel_lines) if rel_lines else "(no relevant relationships)"}

Story outline: {skl_context.get('outline', {}).get('main_conflict', 'Unknown conflict')}"""

        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + SCENE_SCREENPLAY_PROMPT,
            user_prompt,
            temperature=0.7,
        )

        script_node = ScriptNode(id=scene_title, content=[])
        for item in response.get("script", []):
            item_type = item.get("type", "action")
            text = item.get("text", "")
            character = item.get("character", "")
            script_node.content.append(ScriptItem(
                type=item_type,
                text=text,
                character=character,
            ))
        return script_node

    def write_all_scenes(
        self,
        scenes: list[dict],
        skl_context: dict,
    ) -> dict[str, ScriptNode]:
        """Generate screenplay for all scenes, returns scene_id -> ScriptNode."""
        results = {}
        for scene in scenes:
            scene_id = scene.get("id", scene.get("title", f"scene_{len(results)}"))
            script_node = self.write_scene(
                scene_title=scene.get("title", ""),
                scene_location=scene.get("location", ""),
                scene_time=scene.get("time", ""),
                characters_present=scene.get("characters_present", []),
                scene_summary=scene.get("summary", ""),
                skl_context=skl_context,
            )
            results[scene_id] = script_node
        return results
