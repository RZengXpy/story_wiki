"""StoryForgeWorkflow — think.md-compliant pipeline implementation.

Architecture follows the 10 principles from think.md, specifically:

  Principle III (Unified Knowledge Extraction):
    Chapter → [ONE LLM call per chapter] → Local Knowledge
    NOT: Chapter → Agent1, Agent2, Agent3, Agent4 each reading the same chapter

  Principle V (Local → Global):
    Local Knowledge → Knowledge Merger → Global SKL
    NOT: Entire Novel → Single Prompt

Pipeline stages (per think.md Standard Workflow):
  1. Chapter Parser     → Chapter[]
  2. Knowledge Extraction (UnifiedExtractionAgent) → Local Knowledge per chapter
  3. Knowledge Merge    → GlobalStoryKnowledge (SKL)
  4. Knowledge Governance (CharacterAgent, EventAgent, RelationAgent governance)
  5. Consistency Check   → validated SKL
  6. Story Graph        → structured graph representation
  7. Knowledge Retrieval → scene-relevant context (for screenplay generation)
  8. Scene Planner      → scene ordering
  9. Script Generator   → screenplay per scene
  10. YAML Export       → structured output

Multi-agent pattern:
  - Extraction: 1 agent (UnifiedExtractionAgent) — 1 LLM call per chapter
  - Governance: 5 agents operate on SKL (deduplication, causal chains, etc.)
  - Generation: 1 agent (ScriptAgent) — filtered retrieval before generation
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

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
from core.progress import ProgressTracker, Phase

if TYPE_CHECKING:
    from core.storage import StoryStorage

# Extraction agent
from agent.unified_extraction_agent import UnifiedExtractionAgent

# Governance agents (per think.md Principle IV)
from agent import (
    CharacterAgent,
    SceneAgent,
    EventAgent,
    RelationAgent,
    OutlineAgent,
    ScriptAgent,
    LocationAgent,
    TimelineAgent,
)

if TYPE_CHECKING:
    from schema.models import SourceTrace


@dataclass
class WorkflowResult:
    success: bool
    graph: Optional[StoryGraph] = None
    error_message: str = ""
    step_results: dict = field(default_factory=dict)
    chapters: list = field(default_factory=list)
    global_skl: Optional[object] = field(default=None)
    merger_report: dict = field(default_factory=dict)
    governance_report: Optional[GovernanceReport] = field(default=None)
    governance_audit: list = field(default_factory=list)
    novel_text: str = ""  # raw input, preserved for storage

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
    """think.md-compliant workflow orchestrator.

    The core difference from the previous implementation:
    - Uses UnifiedExtractionAgent (1 LLM call per chapter) instead of 4 separate agents
    - Agents provide governance methods that operate on the SKL (not extraction)
    - Supports both sequential and parallel extraction modes
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        run_consistency_check: bool = True,
        use_parallel_extraction: bool = False,
        storage: Optional["StoryStorage"] = None,
    ):
        self.llm = LLMClient(model=model, api_key=api_key)
        self.run_consistency_check = run_consistency_check
        self.use_parallel_extraction = use_parallel_extraction
        self.storage = storage

        # Extraction agent (single-pass per chapter)
        self.extraction_agent = UnifiedExtractionAgent(self.llm)

        # Governance agents (operate on SKL, not raw text)
        self.char_agent = CharacterAgent(self.llm)
        self.scene_agent = SceneAgent(self.llm)
        self.event_agent = EventAgent(self.llm)
        self.relation_agent = RelationAgent(self.llm)
        self.outline_agent = OutlineAgent(self.llm)
        self.location_agent = LocationAgent(self.llm)
        self.timeline_agent = TimelineAgent(self.llm)

    def run(
        self,
        novel_text: str,
        title: str = "",
        author: str = "",
        tracker: Optional[ProgressTracker] = None,
        _store: bool = True,
    ) -> WorkflowResult:
        """Build SKL from novel text following think.md pipeline.

        Pipeline:
          Chapter Parser → Unified Extraction (Local Knowledge)
                         → Local → Global Merge (Global SKL)
                         → Agent Governance (SKL quality)
                         → Consistency Check
                         → Story Graph
        """
        try:
            # ── Stage 1: Chapter Parsing ──────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.PARSING_CHAPTERS)

            chapters = parse_chapters(novel_text)
            if not chapters:
                return WorkflowResult(success=False, error_message="无法解析章节结构")

            n_chapters = len(chapters)
            if tracker:
                tracker.set_total(n_chapters=n_chapters)
                tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)

            # ── Stage 2: Unified Knowledge Extraction ──────────────────────
            # ONE LLM call per chapter, extracting all knowledge types at once.
            # This implements think.md Principle III.
            all_chars = []
            all_scenes = []
            all_events = []
            all_relations = []

            for idx, ch in enumerate(chapters):
                ch_id = getattr(ch, "id", f"ch_{idx+1:03d}")
                ch_title = getattr(ch, "title", "")
                ch_content = getattr(ch, "content", "")

                if tracker:
                    tracker.on_chapter_start(idx, ch_title)

                result = self.extraction_agent.extract(ch_content, ch_id, ch_title)

                all_chars.extend(result.characters)
                all_scenes.extend(result.scenes)
                all_events.extend(result.events)
                all_relations.extend(result.relations)

                if tracker:
                    # Report as 1 LLM call (unified extraction) instead of 4
                    tracker.on_agent_done("知识抽取", idx, ch_title)
                    tracker.on_chapter_done(idx + 1, ch_title)

            if tracker:
                tracker.on_outline_done()

            # ── Stage 3: Outline Generation ────────────────────────────────
            outline = {}
            try:
                if tracker:
                    tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)
                story_outline = self.outline_agent.generate_outline(novel_text)
                outline = {
                    "genre": story_outline.genre,
                    "theme": story_outline.theme,
                    "main_conflict": story_outline.main_conflict,
                    "arc_summary": story_outline.arc_summary,
                    "act_summaries": [
                        {
                            "act_number": a.act_number,
                            "title": a.title,
                            "summary": a.summary,
                            "key_scenes": a.key_scenes,
                        }
                        for a in story_outline.act_summaries
                    ],
                    "key_plot_points": story_outline.key_plot_points,
                }
                if tracker:
                    tracker.on_outline_done()
            except Exception:
                pass

            # ── Stage 4: Local → Global Knowledge Merge ───────────────────
            if tracker:
                tracker.set_phase(Phase.MERGING_KNOWLEDGE)

            gsk = merge_chapters_to_skl(
                title=title,
                author=author,
                chapters=chapters,
                all_characters=all_chars,
                all_scenes=all_scenes,
                all_relations=all_relations,
                all_events=all_events,
                outline=outline,
                timeline_agent=self.timeline_agent,
                location_agent=self.location_agent,
            )

            if tracker:
                tracker.on_merge_done()

            # ── Stage 5: Agent Governance (think.md Principle IV) ──────────
            # Agents operate on the SKL, not the raw text.
            # This replaces the previous pattern of agents reading chapters directly.
            if tracker:
                tracker.set_phase(Phase.GOVERNANCE)

            governance_audit: list[dict] = []

            # Character governance: deduplicate + assign roles
            char_dedup_audit = self.char_agent.deduplicate(gsk)
            governance_audit.extend([
                {"agent": "CharacterAgent", **a} for a in char_dedup_audit
            ])
            char_alias_audit = self.char_agent.merge_aliases(gsk)
            governance_audit.extend([
                {"agent": "CharacterAgent", **a} for a in char_alias_audit
            ])
            char_role_audit = self.char_agent.assign_roles(gsk)
            governance_audit.extend([
                {"agent": "CharacterAgent", **a} for a in char_role_audit
            ])

            # Event governance: deduplicate + causal chains
            event_merge_audit = self.event_agent.merge_events(gsk)
            governance_audit.extend([
                {"agent": "EventAgent", **a} for a in event_merge_audit
            ])
            causal_chains = self.event_agent.build_causal_chains(gsk)

            # Relation governance (handled in knowledge_governance.py)
            # GovernanceReport will handle relation deduplication and normalization

            # ── Stage 6: Knowledge Governance (formal audit) ───────────────
            governance_report = govern_skl(gsk, auto_resolve=True)

            # ── Stage 7: Build StoryGraph ────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.BUILDING_GRAPH)

            graph = StoryGraph(metadata={
                "title": title,
                "author": author,
                "genre": outline.get("genre", "thriller"),
                "created_at": datetime.now().isoformat(),
                "adapted_by": "StoryForge",
                **self._build_merger_report(gsk),
            })

            # Characters
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

            # Relations
            for r in gsk.relations:
                graph.relations.append(RelationNode(
                    from_char=r.from_char,
                    to_char=r.to_char,
                    relation_type=r.relation_type,
                    description=r.description,
                ))

            # Scenes
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

            # Events
            type_map = {
                "conflict": EventType.CONFLICT,
                "revelation": EventType.REVELATION,
                "transition": EventType.TRANSITION,
                "turning_point": EventType.TURNING_POINT,
                "resolution": EventType.RESOLUTION,
            }
            for e in gsk.events:
                e_dict = e if isinstance(e, dict) else {}
                src = e_dict.get("source", {}) if isinstance(e_dict.get("source"), dict) else {}
                graph.events.append(EventNode(
                    title=e_dict.get("title", ""),
                    event_type=type_map.get(e_dict.get("event_type", ""), EventType.TRANSITION),
                    location=e_dict.get("location", ""),
                    time_marker=e_dict.get("time_marker", ""),
                    participants=e_dict.get("participants", []),
                    description=e_dict.get("description", ""),
                    cause=e_dict.get("cause", ""),
                    consequence=e_dict.get("consequence", ""),
                ))

            # ── Stage 8: Consistency Check ────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.CHECKING_CONSISTENCY)
            if self.run_consistency_check:
                checker = ConsistencyChecker(graph)
                report = checker.check_all()
                graph.warnings = report.warnings
                merger_report = self._build_merger_report(gsk)
                merger_report["consistency_passed"] = report.passed
                merger_report["consistency_info"] = report.info
            else:
                merger_report = self._build_merger_report(gsk)

            merger_report["governance_passed"] = governance_report.validation.passed
            merger_report["governance_issues"] = len(governance_report.validation.issues)
            merger_report["governance_conflicts"] = len(governance_report.conflicts)
            merger_report["governance_auto_corrections"] = len(governance_report.auto_corrections)
            merger_report["agent_governance_actions"] = len(governance_audit)

            result = WorkflowResult(
                success=True,
                graph=graph,
                chapters=chapters,
                novel_text=novel_text,
            )
            result.step_results = {
                "characters": all_chars,
                "scenes": all_scenes,
                "events": all_events,
                "relations": all_relations,
                "causal_chains": causal_chains,
            }
            result.global_skl = gsk
            result.merger_report = merger_report
            result.governance_report = governance_report
            result.governance_audit = governance_audit

            if tracker:
                tracker.set_phase(Phase.DONE)

            # ── Auto-save to storage if configured ──────────────────────
            if _store and self.storage is not None:
                try:
                    self.storage.save_result(result, novel_text)
                except Exception:
                    pass

            return result

        except Exception as e:
            if tracker:
                tracker.on_error(str(e))
            return WorkflowResult(success=False, error_message=str(e))

    def run_with_scripts(
        self,
        novel_text: str,
        title: str = "",
        author: str = "",
        tracker: Optional[ProgressTracker] = None,
        _store: bool = True,
    ) -> WorkflowResult:
        """Full pipeline: SKL building + screenplay generation.

        Follows think.md Principle VIII (Retrieval Before Generation):
          Relevant Knowledge → Script Generator → Screenplay
        """
        result = self.run(novel_text, title, author, tracker=tracker, _store=False)
        if not result.success:
            return result

        n_scenes = len(result.graph.scenes)

        if tracker and n_scenes > 0:
            llm_done, _ = tracker.get_llm_progress()
            tracker.set_total(
                n_chapters=len(result.chapters),
                n_scenes=n_scenes,
            )
            tracker._llm_done = llm_done
            tracker.set_phase(Phase.GENERATING_SCRIPTS)

        # ── Stage 9: Script Generation ──────────────────────────────────
        # Implements "Retrieval Before Generation" (Principle VIII)
        script_agent = ScriptAgent(self.llm)

        # Build SKL context (filtered per scene)
        skl_context = {
            "characters": [
                {
                    "name": c.name,
                    "description": c.description,
                    "traits": c.traits,
                    "role": c.role,
                }
                for c in result.global_skl.characters
            ],
            "events": result.global_skl.events,
            "relations": [
                {
                    "from_char": r.from_char,
                    "to_char": r.to_char,
                    "relation_type": r.relation_type,
                    "description": r.description,
                }
                for r in result.global_skl.relations
            ],
            "outline": result.global_skl.outline,
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
            for s in result.graph.scenes
        ]

        try:
            scripts = script_agent.write_all_scenes(scene_dicts, skl_context, tracker=tracker)
            result.graph.scripts = scripts
            result.merger_report["scripts_generated"] = len(scripts)
            result.merger_report["screenplay_items"] = sum(
                len(s.content) for s in scripts.values()
            )
        except Exception:
            result.merger_report["scripts_generated"] = 0

        if tracker:
            tracker.set_phase(Phase.DONE)

        # ── Auto-save to storage if configured ──────────────────────
        if _store and self.storage is not None:
            try:
                self.storage.save_result(result, novel_text)
            except Exception:
                pass

        return result

    def run_parallel(
        self,
        novel_text: str,
        title: str = "",
        author: str = "",
        tracker: Optional[ProgressTracker] = None,
    ) -> WorkflowResult:
        """Parallel version of run() using async pipeline.

        Uses asyncio to extract knowledge from all chapters concurrently,
        while each chapter still uses a SINGLE unified LLM call.
        This gives the parallelism benefit (O(1) wall-clock time for extraction)
        without the cost of multiple agents re-reading the same chapter.
        """
        try:
            from core.async_pipeline import extract_all_parallel_unified

            if tracker:
                tracker.set_phase(Phase.PARSING_CHAPTERS)

            chapters = parse_chapters(novel_text)
            if not chapters:
                return WorkflowResult(success=False, error_message="无法解析章节结构")

            n_chapters = len(chapters)
            if tracker:
                tracker.set_total(n_chapters=n_chapters)
                tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)

            # ── Parallel extraction (1 unified call per chapter) ───────────
            unified_result = extract_all_parallel_unified(
                chapters,
                self.extraction_agent,
                tracker=tracker,
            )

            all_chars = unified_result.characters
            all_scenes = unified_result.scenes
            all_events = unified_result.events
            all_relations = unified_result.relations

            # ── Outline ──────────────────────────────────────────────────
            outline = {}
            try:
                if tracker:
                    tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)
                story_outline = self.outline_agent.generate_outline(novel_text)
                outline = {
                    "genre": story_outline.genre,
                    "theme": story_outline.theme,
                    "main_conflict": story_outline.main_conflict,
                    "arc_summary": story_outline.arc_summary,
                    "act_summaries": [
                        {
                            "act_number": a.act_number,
                            "title": a.title,
                            "summary": a.summary,
                            "key_scenes": a.key_scenes,
                        }
                        for a in story_outline.act_summaries
                    ],
                    "key_plot_points": story_outline.key_plot_points,
                }
                if tracker:
                    tracker.on_outline_done()
            except Exception:
                pass

            # ── Local → Global Merge ────────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.MERGING_KNOWLEDGE)

            gsk = merge_chapters_to_skl(
                title=title,
                author=author,
                chapters=chapters,
                all_characters=all_chars,
                all_scenes=all_scenes,
                all_relations=all_relations,
                all_events=all_events,
                outline=outline,
                timeline_agent=self.timeline_agent,
                location_agent=self.location_agent,
            )

            if tracker:
                tracker.on_merge_done()

            # ── Governance ───────────────────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.GOVERNANCE)

            governance_audit: list[dict] = []
            char_dedup_audit = self.char_agent.deduplicate(gsk)
            governance_audit.extend([{"agent": "CharacterAgent", **a} for a in char_dedup_audit])
            char_alias_audit = self.char_agent.merge_aliases(gsk)
            governance_audit.extend([{"agent": "CharacterAgent", **a} for a in char_alias_audit])
            char_role_audit = self.char_agent.assign_roles(gsk)
            governance_audit.extend([{"agent": "CharacterAgent", **a} for a in char_role_audit])

            event_merge_audit = self.event_agent.merge_events(gsk)
            governance_audit.extend([{"agent": "EventAgent", **a} for a in event_merge_audit])
            causal_chains = self.event_agent.build_causal_chains(gsk)

            governance_report = govern_skl(gsk, auto_resolve=True)

            # ── Build StoryGraph ─────────────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.BUILDING_GRAPH)

            graph = StoryGraph(metadata={
                "title": title,
                "author": author,
                "genre": outline.get("genre", "thriller"),
                "created_at": datetime.now().isoformat(),
                "adapted_by": "StoryForge",
                **self._build_merger_report(gsk),
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

            for r in gsk.relations:
                graph.relations.append(RelationNode(
                    from_char=r.from_char,
                    to_char=r.to_char,
                    relation_type=r.relation_type,
                    description=r.description,
                ))

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

            type_map = {
                "conflict": EventType.CONFLICT,
                "revelation": EventType.REVELATION,
                "transition": EventType.TRANSITION,
                "turning_point": EventType.TURNING_POINT,
                "resolution": EventType.RESOLUTION,
            }
            for e in gsk.events:
                e_dict = e if isinstance(e, dict) else {}
                graph.events.append(EventNode(
                    title=e_dict.get("title", ""),
                    event_type=type_map.get(e_dict.get("event_type", ""), EventType.TRANSITION),
                    location=e_dict.get("location", ""),
                    time_marker=e_dict.get("time_marker", ""),
                    participants=e_dict.get("participants", []),
                    description=e_dict.get("description", ""),
                    cause=e_dict.get("cause", ""),
                    consequence=e_dict.get("consequence", ""),
                ))

            # ── Consistency Check ─────────────────────────────────────────
            if tracker:
                tracker.set_phase(Phase.CHECKING_CONSISTENCY)
            if self.run_consistency_check:
                checker = ConsistencyChecker(graph)
                report = checker.check_all()
                graph.warnings = report.warnings
                merger_report = self._build_merger_report(gsk)
                merger_report["consistency_passed"] = report.passed
                merger_report["consistency_info"] = report.info
            else:
                merger_report = self._build_merger_report(gsk)

            merger_report["governance_passed"] = governance_report.validation.passed
            merger_report["governance_issues"] = len(governance_report.validation.issues)
            merger_report["governance_conflicts"] = len(governance_report.conflicts)
            merger_report["governance_auto_corrections"] = len(governance_report.auto_corrections)
            merger_report["agent_governance_actions"] = len(governance_audit)

            result = WorkflowResult(
                success=True,
                graph=graph,
                chapters=chapters,
                novel_text=novel_text,
            )
            result.step_results = {
                "characters": all_chars,
                "scenes": all_scenes,
                "events": all_events,
                "relations": all_relations,
                "causal_chains": causal_chains,
            }
            result.global_skl = gsk
            result.merger_report = merger_report
            result.governance_report = governance_report
            result.governance_audit = governance_audit

            if tracker:
                tracker.set_phase(Phase.DONE)

            if self.storage is not None:
                try:
                    self.storage.save_result(result, novel_text)
                except Exception:
                    pass

            return result

        except Exception as e:
            if tracker:
                tracker.on_error(str(e))
            return WorkflowResult(success=False, error_message=str(e))

    def _build_merger_report(self, gsk) -> dict:
        return {
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

    def _make_source_trace(self, ch) -> "SourceTrace":
        """Build a SourceTrace from a chapter object."""
        from schema.models import SourceTrace
        return SourceTrace(
            chapter_id=getattr(ch, "id", ""),
            chapter_title=getattr(ch, "title", ""),
            char_range=(getattr(ch, "start_char", 0), getattr(ch, "end_char", 0)),
        )
