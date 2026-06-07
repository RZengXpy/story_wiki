"""StoryForgeWorkflow — chapter-based orchestration with SKL building."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.llm_client import LLMClient
from core.chapter_parser import parse_chapters
from core.story_graph import (
    StoryGraph,
    CharacterNode,
    RelationNode,
    EventNode,
    SceneNode,
    CharacterRole,
    EventType,
)
from core.knowledge_merger import (
    merge_chapters_to_skl,
)
from core.consistency_checker import ConsistencyChecker
from core.knowledge_governance import KnowledgeGovernor, govern_skl
from core.progress import ProgressTracker, Phase
from agent.unified_extraction_agent import UnifiedExtractionAgent, extract_all_chapters
from agent.director_agent import DirectorAgent
from agent.script_agent import ScriptAgent
from agent import CharacterAgent, SceneAgent, EventAgent, RelationAgent, OutlineAgent


@dataclass
class WorkflowResult:
    success: bool
    graph: Optional[StoryGraph] = None
    error_message: str = ""
    step_results: dict = field(default_factory=dict)
    chapters: list = field(default_factory=list)
    global_skl: Optional[object] = field(default=None)  # GlobalStoryKnowledge
    merger_report: dict = field(default_factory=dict)
    screenplay_bible: dict = field(default_factory=dict)
    governance_report: Optional[object] = field(default=None)

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

        # Agents
        self.unified_agent = UnifiedExtractionAgent(self.llm)
        self.char_agent = CharacterAgent(self.llm)
        self.scene_agent = SceneAgent(self.llm)
        self.event_agent = EventAgent(self.llm)
        self.relation_agent = RelationAgent(self.llm)
        self.outline_agent = OutlineAgent(self.llm)
        self.director_agent = DirectorAgent(self.llm)
        self.script_agent = ScriptAgent(self.llm)

    def run(self, novel_text: str, title: str = "", author: str = "",
            tracker: Optional[ProgressTracker] = None) -> WorkflowResult:
        """Run SKL build pipeline (without screenplay generation)."""
        try:
            if tracker:
                tracker.set_total(0, 0)

            chapters = parse_chapters(novel_text)
            if not chapters:
                return WorkflowResult(success=False, error_message="无法解析章节结构")

            if tracker:
                tracker.set_phase(Phase.PARSING_CHAPTERS)
                tracker.set_total(len(chapters), 0)

            # ── MVP 3/5: Unified Knowledge Extraction per chapter ─────────────────
            if tracker:
                tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)

            unified_result = extract_all_chapters(chapters, self.llm, tracker=tracker)

            # ── MVP 5.6: Outline Generation ───────────────────────────────────
            outline = {}
            try:
                if tracker:
                    tracker.set_phase(Phase.MERGING_KNOWLEDGE)
                story_outline = self.outline_agent.generate_outline(novel_text)
                outline = {
                    "genre": story_outline.genre,
                    "theme": story_outline.theme,
                    "main_conflict": story_outline.main_conflict,
                    "arc_summary": story_outline.arc_summary,
                    "act_summaries": [
                        {"act_number": a.act_number, "title": a.title, "summary": a.summary,
                         "key_scenes": a.key_scenes}
                        for a in story_outline.act_summaries
                    ],
                    "key_plot_points": story_outline.key_plot_points,
                }
            except Exception:
                pass  # outline generation is non-critical

            # ── MVP 4 + MVP 5: Local → Global Knowledge Merge ───────────────────
            gsk = merge_chapters_to_skl(
                title=title,
                author=author,
                chapters=chapters,
                all_characters=unified_result.characters,
                all_scenes=unified_result.scenes,
                all_relations=unified_result.relations,
                all_events=unified_result.events,
                outline=outline,
            )

            # Attach per-chapter summaries/goals/conflicts to SKL for UI display
            gsk.chapter_summaries = unified_result.chapter_summary.split("\n") if unified_result.chapter_summary else []
            gsk.chapter_goals = unified_result.chapter_goal.split("\n") if unified_result.chapter_goal else []
            gsk.chapter_conflicts = unified_result.chapter_conflict.split("\n") if unified_result.chapter_conflict else []

            merger_report = {
                "total_chapters": gsk.total_chapters,
                "unique_characters": len(gsk.characters),
                "unique_scenes": len(gsk.scenes),
                "unique_relations": len(gsk.relations),
                "unique_events": len(gsk.events),
                "duplicates_removed": gsk.duplicates_removed,
                "character_first_appearance": gsk.character_first_appearance,
                "locations_count": len(gsk.locations),
                "timeline_count": len(gsk.timeline),
                "character_arcs_count": len(gsk.character_arcs),
                "outline_generated": bool(gsk.outline),
            }

            # ── Build StoryGraph (deduplicated via SKL) ─────────────────────
            graph = StoryGraph(metadata={
                "title": title,
                "author": author,
                "genre": outline.get("genre", "thriller"),
                "created_at": datetime.now().isoformat(),
                "adapted_by": "StoryForge",
                **merger_report,
            })

            for c in gsk.characters:
                role_map = {
                    "protagonist": CharacterRole.PROTAGONIST,
                    "antagonist": CharacterRole.ANTAGONIST,
                }
                graph.characters.append(CharacterNode(
                    id=c.name,
                    name=c.name,
                    role=role_map.get(c.role, CharacterRole.SUPPORTING),
                    description=c.description,
                    first_appearance=gsk.character_first_appearance.get(c.name, ""),
                ))

            # Relations from SKL
            for r in gsk.relations:
                graph.relations.append(RelationNode(
                    from_char=r.from_char,
                    to_char=r.to_char,
                    relation_type=r.relation_type,
                    description=r.description,
                ))

            # Scenes from SKL
            for s in gsk.scenes:
                graph.scenes.append(SceneNode(
                    id=s.title,
                    title=s.title,
                    location=s.location,
                    time=s.time_of_day,
                    act=1,
                    characters_present=s.characters,
                    summary=s.description,
                ))

            # Events from raw extraction (already deduped in SKL)
            type_map = {
                "conflict": EventType.CONFLICT,
                "revelation": EventType.REVELATION,
                "transition": EventType.TRANSITION,
                "turning_point": EventType.TURNING_POINT,
                "resolution": EventType.RESOLUTION,
            }
            for e in gsk.events:
                src = e.get("source", {}) if isinstance(e.get("source"), dict) else {}
                graph.events.append(EventNode(
                    title=e.get("title", ""),
                    event_type=type_map.get(e.get("event_type", ""), EventType.TRANSITION),
                    location=e.get("location", ""),
                    time_marker=e.get("time_marker", ""),
                    participants=e.get("participants", []),
                    description=e.get("description", ""),
                    cause=e.get("cause", ""),
                    consequence=e.get("consequence", ""),
                ))

            # ── Knowledge Governance ─────────────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.GOVERNANCE)
            governance_report = govern_skl(gsk, auto_resolve=True, graph=graph, llm=self.llm)

            # ── MVP 4: Enhanced Consistency Check ─────────────────────────────
            if self.run_consistency_check:
                if tracker:
                    tracker.set_phase(Phase.CHECKING_CONSISTENCY)
                checker = ConsistencyChecker(graph)
                report = checker.check_all()
                graph.warnings = report.warnings
                merger_report["consistency_passed"] = report.passed
                merger_report["consistency_info"] = report.info

            if tracker:
                tracker.set_phase(Phase.BUILDING_GRAPH)

            result = WorkflowResult(
                success=True, graph=graph, chapters=chapters,
                global_skl=gsk, merger_report=merger_report,
                governance_report=governance_report,
            )
            result.step_results = {
                "characters": unified_result.characters,
                "scenes": unified_result.scenes,
                "events": unified_result.events,
                "relations": unified_result.relations,
            }
            return result

        except Exception as e:
            return WorkflowResult(success=False, error_message=str(e))

    def run_with_scripts(self, novel_text: str, title: str = "", author: str = "",
                         tracker: Optional[ProgressTracker] = None) -> WorkflowResult:
        """Run full pipeline including screenplay generation."""
        # First run the SKL build
        result = self.run(novel_text, title, author, tracker=tracker)
        if not result.success:
            return result

        graph = result.graph
        gsk = result.global_skl

        try:
            if tracker:
                tracker.set_phase(Phase.GOVERNANCE)

            # Re-govern after graph is built (graph was built in run())
            governance_report = govern_skl(gsk, auto_resolve=True, graph=graph, llm=self.llm)
            result.governance_report = governance_report

            # ── Director Agent: Create Screenplay Bible ───────────────────────
            if tracker:
                tracker.set_phase(Phase.GENERATING_SCRIPTS)
                tracker.set_total(len(graph.scenes), len(graph.scenes))

            bible = self.director_agent.create_bible(gsk)
            result.screenplay_bible = bible.to_dict()

            # ── Script Agent: Write all scenes in parallel ────────────────────
            if graph.scenes:
                skl_context = {
                    "characters": [
                        {"name": c.name, "description": c.description,
                         "traits": getattr(c, "traits", []),
                         "role": getattr(c, "role", "supporting")}
                        for c in gsk.characters
                    ],
                    "events": [
                        e if isinstance(e, dict) else e.__dict__
                        for e in gsk.events
                    ],
                    "relations": [
                        {"from_char": r.from_char, "to_char": r.to_char,
                         "relation_type": r.relation_type, "description": r.description}
                        for r in gsk.relations
                    ],
                    "outline": gsk.outline or {},
                }

                scene_dicts = [
                    {
                        "id": s.id,
                        "title": s.title,
                        "location": s.location,
                        "time": s.time,
                        "characters_present": s.characters_present,
                        "summary": s.summary,
                    }
                    for s in graph.scenes
                ]

                import asyncio
                scripts = asyncio.run(
                    self.script_agent.write_all_scenes_async(
                        scenes=scene_dicts,
                        skl_context=skl_context,
                        tracker=tracker,
                        bible=bible,
                    )
                )
                graph.scripts = scripts

        except Exception as e:
            # Non-critical: screenplay generation failed but SKL is still valid
            pass

        return result
