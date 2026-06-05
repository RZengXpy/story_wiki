"""StoryForgeWorkflow — orchestrates agents + consistency check to build a StoryGraph."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.llm_client import LLMClient
from core.story_graph import (
    StoryGraph,
    CharacterNode,
    RelationNode,
    EventNode,
    SceneNode,
    CharacterRole,
    EventType,
)
from agent import CharacterAgent, SceneAgent, ScriptAgent


@dataclass
class WorkflowResult:
    success: bool
    graph: Optional[StoryGraph] = None
    error_message: str = ""
    step_results: dict = field(default_factory=dict)

    def summary(self) -> str:
        if not self.success:
            return f"[失败] {self.error_message}"
        g = self.graph
        return (
            f"[成功] 角色={len(g.characters)} | 场景={len(g.scenes)} "
            f"| 事件={len(g.events)} | 关系={len(g.relations)} | 警告={len(g.warnings)}"
        )


class StoryForgeWorkflow:
    def __init__(self, model: str, api_key: str, run_consistency_check: bool = True):
        self.llm = LLMClient(model=model, api_key=api_key)
        self.run_consistency_check = run_consistency_check

    def run(self, novel_text: str, title: str = "", author: str = "") -> WorkflowResult:
        try:
            char_agent = CharacterAgent(self.llm)
            scene_agent = SceneAgent(self.llm)
            script_agent = ScriptAgent(self.llm)

            char_data = char_agent.extract_characters(novel_text)
            scene_data = scene_agent.parse_scenes(novel_text)

            graph = StoryGraph(metadata={
                "title": title,
                "author": author,
                "genre": "thriller",
                "created_at": datetime.now().isoformat(),
                "adapted_by": "StoryForge",
            })

            for c in char_data:
                role_map = {
                    "protagonist": CharacterRole.PROTAGONIST,
                    "antagonist": CharacterRole.ANTAGONIST,
                }
                graph.characters.append(CharacterNode(
                    id=c.name,
                    name=c.name,
                    role=role_map.get(c.role, CharacterRole.SUPPORTING),
                    description=c.description,
                    first_appearance="第一章",
                ))

            for s in scene_data:
                graph.scenes.append(SceneNode(
                    id=s.title,
                    title=s.title,
                    location=s.location,
                    time=s.time_of_day,
                    act=1,
                    characters_present=s.characters,
                    summary=s.description,
                ))

            if self.run_consistency_check:
                graph.warnings = self._consistency_check(graph, novel_text)

            result = WorkflowResult(success=True, graph=graph)
            result.step_results = {
                "characters": char_data,
                "scenes": scene_data,
            }
            return result

        except Exception as e:
            return WorkflowResult(success=False, error_message=str(e))

    def _consistency_check(self, graph: StoryGraph, novel_text: str) -> list:
        from core.story_graph import WarningNode, WarningCode, WarningSeverity
        warnings = []

        char_names = {c.name for c in graph.characters}
        for scene in graph.scenes:
            for ch in scene.characters_present:
                if ch and ch not in char_names:
                    warnings.append(WarningNode(
                        code=WarningCode.CHARACTER_DISCREPANCY,
                        message=f"场景「{scene.title}」中出现未识别角色：{ch}",
                        severity=WarningSeverity.WARNING,
                        scene_ids=[scene.id],
                        characters_involved=[ch],
                    ))

        return warnings
