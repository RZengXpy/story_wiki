"""ScriptAgent — converts story knowledge (SKL) into structured screenplay YAML.

Implements think.md Principle VIII: Retrieval Before Generation.
All scenes are generated in parallel using asyncio.to_thread().
"""
import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from core.llm_client import LLMClient
from core.prompts import (
    SYSTEM_PROMPT,
    SCRIPT_WRITING_PROMPT,
    STORY_STRUCTURE_PROMPT,
    SCENE_SCREENPLAY_PROMPT,
)
from core.story_graph import ScriptNode, ScriptItem

if TYPE_CHECKING:
    from agent.director_agent import ScreenplayBible

try:
    from core.progress import ProgressTracker
except ImportError:
    ProgressTracker = None

logger = logging.getLogger(__name__)


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
        bible: "ScreenplayBible | None" = None,
    ) -> ScriptNode:
        """Generate screenplay for a single scene using filtered SKL context + Bible."""
        return self._write_scene_sync(
            scene_title=scene_title,
            scene_location=scene_location,
            scene_time=scene_time,
            characters_present=characters_present,
            scene_summary=scene_summary,
            skl_context=skl_context,
            bible=bible,
        )

    async def _write_one_scene(
        self, idx: int, scene: dict, skl_context: dict,
        bible: "ScreenplayBible | None" = None,
    ) -> tuple[int, str, "ScriptNode | Exception"]:
        """Write a single scene's screenplay (called in parallel)."""
        scene_id = scene.get("id", scene.get("title", f"scene_{idx}"))
        try:
            script_node = self._write_scene_sync(
                scene_title=scene.get("title", ""),
                scene_location=scene.get("location", ""),
                scene_time=scene.get("time", ""),
                characters_present=scene.get("characters_present", []),
                scene_summary=scene.get("summary", ""),
                skl_context=skl_context,
                bible=bible,
            )
            return idx, scene_id, script_node
        except Exception as e:
            logger.warning("场景剧本生成失败 [%s]: %s", scene_id, e)
            return idx, scene_id, e

    def _write_scene_sync(
        self,
        scene_title: str,
        scene_location: str,
        scene_time: str,
        characters_present: list[str],
        scene_summary: str,
        skl_context: dict,
        bible: "ScreenplayBible | None" = None,
    ) -> ScriptNode:
        """Synchronous scene writing (called in a thread by asyncio.to_thread)."""
        char_lines = []
        for c in skl_context.get("characters", []):
            name = c.get("name", "")
            if name in characters_present:
                desc = c.get("description", "")
                traits = ", ".join(c.get("traits", []))
                role = c.get("role", "supporting")
                char_lines.append(f"- {name} ({role}): {desc} | Traits: {traits}")

        event_lines = []
        for e in skl_context.get("events", []):
            event_lines.append(f"- [{e.get('event_type', '')}] {e.get('title', '')}: {e.get('description', '')}")

        rel_lines = []
        for r in skl_context.get("relations", []):
            fc, tc = r.get("from_char", ""), r.get("to_char", "")
            if fc in characters_present or tc in characters_present:
                rel_lines.append(f"- {fc} --[{r.get('relation_type', '')}]--> {tc}: {r.get('description', '')}")

        # Build Bible context section
        bible_section = self._build_bible_section(bible) if bible else ""

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

Story outline: {skl_context.get('outline', {}).get('main_conflict', 'Unknown conflict')}

{bible_section}"""

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

    def _build_bible_section(self, bible: "ScreenplayBible") -> str:
        """Build the Bible context section for the prompt."""
        sections = ["# Screenplay Bible"]

        if bible.genre:
            sections.append(f"Genre: {bible.genre}")
        if bible.subgenre:
            sections.append(f"Subgenre: {bible.subgenre}")
        if bible.tone:
            sections.append(f"Tone: {bible.tone}")
        if bible.visual_style:
            sections.append(f"Visual Style: {bible.visual_style}")
        if bible.setting_period:
            sections.append(f"Setting/Period: {bible.setting_period}")
        if bible.atmosphere:
            sections.append(f"Atmosphere: {', '.join(bible.atmosphere)}")

        if bible.themes:
            sections.append(f"Themes: {', '.join(bible.themes)}")
        if bible.motifs:
            sections.append(f"Motifs: {', '.join(bible.motifs)}")

        if bible.character_portraits:
            sections.append("\nCharacter Portraits:")
            for p in bible.character_portraits:
                sections.append(f"- {p.get('name', '')}: {p.get('psychology', '')}")
                if p.get('speech_pattern'):
                    sections.append(f"  Speech: {p.get('speech_pattern')}")

        if bible.act_breakdown:
            sections.append(f"\nAct Structure:")
            for act, desc in bible.act_breakdown.items():
                sections.append(f"  {act}: {desc}")

        if bible.dialogue_style:
            sections.append(f"\nDialogue Style: {bible.dialogue_style}")
        if bible.pacing_notes:
            sections.append(f"Pacing: {bible.pacing_notes}")

        return "\n".join(sections)

    async def write_all_scenes_async(
        self,
        scenes: list[dict],
        skl_context: dict,
        tracker: Optional["ProgressTracker"] = None,
        bible: "ScreenplayBible | None" = None,
    ) -> dict[str, ScriptNode]:
        """Generate screenplay for all scenes concurrently.

        Uses asyncio.gather() to run all scene generation in parallel,
        reducing wall-clock time from O(n) to O(1) for the script phase.
        Each scene still uses exactly 1 LLM call.
        """
        if not scenes:
            return {}

        tasks = [
            self._write_one_scene(idx, scene, skl_context, bible)
            for idx, scene in enumerate(scenes)
        ]

        results_raw = await asyncio.gather(*tasks)

        results: dict[str, ScriptNode] = {}
        failed = 0
        succeeded = 0

        # Sort by index to maintain scene order
        results_raw.sort(key=lambda x: x[0])

        for idx, scene_id, result in results_raw:
            if isinstance(result, Exception):
                results[scene_id] = ScriptNode(id=scene_id, content=[])
                failed += 1
            else:
                results[scene_id] = result
                succeeded += 1

            if tracker:
                tracker.on_scene_start(idx + 1, scene_id)
                tracker.on_scene_done(idx + 1, scene_id)

        if failed > 0:
            logger.warning(
                "剧本生成完成: 成功 %d, 失败 %d (失败的场景已返回空剧本)",
                succeeded, failed,
            )

        return results

    def write_all_scenes(
        self,
        scenes: list[dict],
        skl_context: dict,
        tracker: Optional["ProgressTracker"] = None,
        bible: "ScreenplayBible | None" = None,
    ) -> dict[str, ScriptNode]:
        """Synchronous wrapper — calls the async parallel implementation."""
        return asyncio.run(self.write_all_scenes_async(scenes, skl_context, tracker, bible))
