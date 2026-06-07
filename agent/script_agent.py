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


def filter_relevant_context(
    skl: dict,
    scene_title: str,
    scene_location: str,
    scene_time: str,
    characters_present: list[str],
) -> dict:
    """Filter SKL to include only context relevant to a given scene.

    Implements "Retrieval Before Generation" principle (MVP 1):
    - Characters: only those appearing in this scene
    - Events: those involving scene characters OR occurring at the same location
    - Relations: those involving scene characters
    - Outline: always passed through (global context)
    """
    chars = []
    for c in skl.get("characters", []):
        if c.get("name", "") in characters_present:
            chars.append(c)

    char_set = set(characters_present)
    events = []
    for e in skl.get("events", []):
        e_participants = set(e.get("participants", []))
        e_location = e.get("location", "")
        if e_participants & char_set:
            events.append(e)
        elif scene_location and e_location and _location_overlaps(scene_location, e_location):
            events.append(e)

    rels = []
    for r in skl.get("relations", []):
        fc = r.get("from_char", "")
        tc = r.get("to_char", "")
        if fc in char_set or tc in char_set:
            rels.append(r)

    return {
        "characters": chars,
        "events": events,
        "relations": rels,
        "outline": skl.get("outline", {}),
    }


def _location_overlaps(loc1: str, loc2: str) -> bool:
    """Check if two location strings refer to the same place."""
    if not loc1 or not loc2:
        return False
    loc1, loc2 = loc1.strip(), loc2.strip()
    if loc1 == loc2:
        return True
    if loc1 in loc2 or loc2 in loc1:
        return True
    for n in range(min(len(loc1), len(loc2)), 2, -1):
        for i in range(len(loc1) - n + 1):
            gram = loc1[i:i + n]
            if gram in loc2:
                return True
    return False


class ScriptAgent:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def analyze_structure(self, story_text: str) -> list:
        if self.llm is None:
            return []
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + STORY_STRUCTURE_PROMPT,
            story_text,
        )
        return response.get("acts", [])

    def write_screenplay(self, story_text: str, genre: str = "general") -> str:
        if self.llm is None:
            return ""
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
        """Generate screenplay content for a single scene using filtered SKL context."""
        if self.llm is None:
            return ScriptNode(id=scene_title, content=[])
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
            try:
                script_node = self.write_scene(
                    scene_title=scene.get("title", ""),
                    scene_location=scene.get("location", ""),
                    scene_time=scene.get("time", ""),
                    characters_present=scene.get("characters_present", []),
                    scene_summary=scene.get("summary", ""),
                    skl_context=skl_context,
                )
            except Exception as e:
                script_node = ScriptNode(id=scene_id, content=[])
            results[scene_id] = script_node
        return results
