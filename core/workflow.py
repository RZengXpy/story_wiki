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
    LocalKnowledge,
    KnowledgeMerger,
    merge_chapters_to_skl,
)
from core.consistency_checker import ConsistencyChecker
from core.knowledge_governance import govern_skl, GovernanceReport
from agent import CharacterAgent, SceneAgent, ScriptAgent, EventAgent, RelationAgent, OutlineAgent


@dataclass
class WorkflowResult:
    success: bool
    graph: Optional[StoryGraph] = None
    error_message: str = ""
    step_results: dict = field(default_factory=dict)
    chapters: list = field(default_factory=list)
    global_skl: Optional[object] = field(default=None)  # GlobalStoryKnowledge
    merger_report: dict = field(default_factory=dict)
    governance_report: Optional[GovernanceReport] = field(default=None)

    def summary(self) -> str:
        if not self.success:
            return f"[失败] {self.error_message}"
        g = self.graph
        scripts_count = len(g.scripts) if g.scripts else 0
        return (
            f"[成功] 章节={len(self.chapters)} | 角色={len(g.characters)} "
            f"| 场景={len(g.scenes)} | 事件={len(g.events)} "
            f"| 关系={len(g.relations)} | 剧本场景={scripts_count} | 警告={len(g.warnings)}"
        )


class StoryForgeWorkflow:
    def __init__(self, model: str, api_key: str, run_consistency_check: bool = True):
        self.llm = LLMClient(model=model, api_key=api_key)
        self.run_consistency_check = run_consistency_check
        self.char_agent = CharacterAgent(self.llm)
        self.scene_agent = SceneAgent(self.llm)
        self.event_agent = EventAgent(self.llm)
        self.relation_agent = RelationAgent(self.llm)
        self.outline_agent = OutlineAgent(self.llm)

    def run(self, novel_text: str, title: str = "", author: str = "") -> WorkflowResult:
        try:
            chapters = parse_chapters(novel_text)
            if not chapters:
                return WorkflowResult(success=False, error_message="无法解析章节结构")

            # ── MVP 3: Local Knowledge Extraction per chapter ──────────────────
            all_characters = self.char_agent.extract_from_chapters(chapters, self.llm)
            all_scenes = self.scene_agent.parse_from_chapters(chapters, self.llm)
            all_events = self.event_agent.extract_events_from_chapters(chapters, self.llm)

            # ── MVP 5.1: Relation Extraction ───────────────────────────────────
            all_relations = self.relation_agent.extract_from_chapters(chapters, self.llm)

            # ── MVP 5.6: Outline Generation ───────────────────────────────────
            outline = {}
            try:
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
                all_characters=all_characters,
                all_scenes=all_scenes,
                all_relations=all_relations,
                all_events=all_events,
                outline=outline,
            )

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

            # ── MVP 7: Knowledge Governance (before building graph) ────────────────
            governance_report = govern_skl(gsk, auto_resolve=True)

            # ── Build StoryGraph metadata ──────────────────────────────────────
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

            # ── MVP 4: Enhanced Consistency Check ─────────────────────────────
            if self.run_consistency_check:
                checker = ConsistencyChecker(graph)
                report = checker.check_all()
                graph.warnings = report.warnings
                merger_report["consistency_passed"] = report.passed
                merger_report["consistency_info"] = report.info

            merger_report["governance_passed"] = governance_report.validation.passed
            merger_report["governance_issues"] = len(governance_report.validation.issues)
            merger_report["governance_conflicts"] = len(governance_report.conflicts)
            merger_report["governance_auto_corrections"] = len(governance_report.auto_corrections)

            result = WorkflowResult(success=True, graph=graph, chapters=chapters)
            result.step_results = {
                "characters": all_characters,
                "scenes": all_scenes,
                "events": all_events,
                "relations": all_relations,
            }
            result.global_skl = gsk
            result.merger_report = merger_report
            result.governance_report = governance_report
            return result

        except Exception as e:
            return WorkflowResult(success=False, error_message=str(e))

    def run_with_scripts(
        self,
        novel_text: str,
        title: str = "",
        author: str = "",
    ) -> WorkflowResult:
        """Full pipeline: SKL building + screenplay generation."""
        result = self.run(novel_text, title, author)
        if not result.success:
            return result

        # ── MVP 6: SKL → Screenplay ───────────────────────────────────────────
        script_agent = ScriptAgent(self.llm)

        # Build SKL context for scene-level generation
        skl_context = {
            "characters": [
                {"name": c.name, "description": c.description, "traits": c.traits, "role": c.role}
                for c in result.global_skl.characters
            ],
            "events": result.global_skl.events,
            "relations": [
                {"from_char": r.from_char, "to_char": r.to_char,
                 "relation_type": r.relation_type, "description": r.description}
                for r in result.global_skl.relations
            ],
            "outline": result.global_skl.outline,
        }

        # Convert SceneNode → dict for write_all_scenes
        scene_dicts = [
            {
                "id": s.id,
                "title": s.title,
                "location": s.location,
                "time": s.time,
                "characters_present": s.characters_present,
                "summary": s.summary,
            }
            for s in result.graph.scenes
        ]

        try:
            scripts = script_agent.write_all_scenes(scene_dicts, skl_context)
            result.graph.scripts = scripts
            result.merger_report["scripts_generated"] = len(scripts)
            result.merger_report["screenplay_items"] = sum(
                len(s.content) for s in scripts.values()
            )
        except Exception:
            result.merger_report["scripts_generated"] = 0

        return result
