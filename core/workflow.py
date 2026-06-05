"""StoryForgeWorkflow — chapter-based orchestration with SKL building."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.llm_client import LLMClient
from core.chapter_parser import parse_chapters, get_chapter_by_id
from core.story_graph import (
    StoryGraph,
    CharacterNode,
    RelationNode,
    EventNode,
    SceneNode,
    CharacterRole,
    EventType,
)
from agent import CharacterAgent, SceneAgent, ScriptAgent, EventAgent


@dataclass
class WorkflowResult:
    success: bool
    graph: Optional[StoryGraph] = None
    error_message: str = ""
    step_results: dict = field(default_factory=dict)
    chapters: list = field(default_factory=list)

    def summary(self) -> str:
        if not self.success:
            return f"[失败] {self.error_message}"
        g = self.graph
        return (
            f"[成功] 章节={len(self.chapters)} | 角色={len(g.characters)} "
            f"| 场景={len(g.scenes)} | 事件={len(g.events)} "
            f"| 关系={len(g.relations)} | 警告={len(g.warnings)}"
        )


class StoryForgeWorkflow:
    def __init__(self, model: str, api_key: str, run_consistency_check: bool = True):
        self.llm = LLMClient(model=model, api_key=api_key)
        self.run_consistency_check = run_consistency_check
        self.char_agent = CharacterAgent(self.llm)
        self.scene_agent = SceneAgent(self.llm)
        self.event_agent = EventAgent(self.llm)

    def run(self, novel_text: str, title: str = "", author: str = "") -> WorkflowResult:
        try:
            chapters = parse_chapters(novel_text)
            if not chapters:
                return WorkflowResult(success=False, error_message="无法解析章节结构")

            # Local Knowledge Extraction per chapter
            all_characters = self.char_agent.extract_from_chapters(chapters, self.llm)
            all_scenes = self.scene_agent.parse_from_chapters(chapters, self.llm)
            all_events = self.event_agent.extract_events_from_chapters(chapters, self.llm)

            # Build StoryGraph
            graph = StoryGraph(metadata={
                "title": title,
                "author": author,
                "genre": "thriller",
                "created_at": datetime.now().isoformat(),
                "adapted_by": "StoryForge",
            })

            for c in all_characters:
                role_map = {
                    "protagonist": CharacterRole.PROTAGONIST,
                    "antagonist": CharacterRole.ANTAGONIST,
                }
                graph.characters.append(CharacterNode(
                    id=c.name,
                    name=c.name,
                    role=role_map.get(c.role, CharacterRole.SUPPORTING),
                    description=c.description,
                    first_appearance=c.source.chapter_title if c.source else "",
                ))

            for s in all_scenes:
                graph.scenes.append(SceneNode(
                    id=s.title,
                    title=s.title,
                    location=s.location,
                    time=s.time_of_day,
                    act=1,
                    characters_present=s.characters,
                    summary=s.description,
                ))

            type_map = {
                "conflict": EventType.CONFLICT,
                "revelation": EventType.REVELATION,
                "transition": EventType.TRANSITION,
                "turning_point": EventType.TURNING_POINT,
                "resolution": EventType.RESOLUTION,
            }
            for e in all_events:
                src = e.source or {}
                graph.events.append(EventNode(
                    title=e.title,
                    event_type=type_map.get(e.event_type, EventType.TRANSITION),
                    location=e.location,
                    time_marker=e.time_marker,
                    participants=e.participants,
                    description=e.description,
                    cause=e.cause,
                    consequence=e.consequence,
                ))

            if self.run_consistency_check:
                graph.warnings = self._consistency_check(graph, chapters)

            result = WorkflowResult(success=True, graph=graph, chapters=chapters)
            result.step_results = {
                "characters": all_characters,
                "scenes": all_scenes,
                "events": all_events,
            }
            return result

        except Exception as e:
            return WorkflowResult(success=False, error_message=str(e))

    def _consistency_check(self, graph: StoryGraph, chapters: list) -> list:
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

        # Cross-chapter consistency: detect events spanning multiple chapters
        seen_events = set()
        for evt in graph.events:
            key = (evt.title, evt.location)
            if key in seen_events:
                warnings.append(WarningNode(
                    code=WarningCode.EVENT_CONTRADICTION,
                    message=f"事件「{evt.title}」可能在多个场景中重复出现",
                    severity=WarningSeverity.INFO,
                    scene_ids=[s.id for s in graph.scenes if s.location == evt.location],
                    characters_involved=evt.participants,
                ))
            seen_events.add(key)

        return warnings
