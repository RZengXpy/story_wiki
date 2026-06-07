"""Knowledge Merger — merges local chapter-level knowledge into a global SKL.

Implements the "Local → Global" principle from think.md:
  Chapter → Local Knowledge → Knowledge Merge → Global Knowledge
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from schema.models import Character, Scene, Relation, SourceTrace

# Import rich types from agents for GlobalStoryKnowledge field typing
from agent.location_agent import LocationInfo as _RichLocationInfo
from agent.timeline_agent import TimelineEntry as _RichTimelineEntry

# Use rich types in GSK field annotations (resolved at type-check time)
_location_type = _RichLocationInfo
_timeline_type = _RichTimelineEntry


@dataclass
class LocalKnowledge:
    """Knowledge extracted from a single chapter."""
    chapter_id: str
    chapter_title: str
    chapter_summary: str = ""
    chapter_goal: str = ""
    chapter_conflict: str = ""
    characters: list[Character] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


# Re-export for backward compatibility (code importing from knowledge_merger)
TimelineEntry = _RichTimelineEntry
LocationInfo = _RichLocationInfo


@dataclass
class CharacterArcEntry:
    """A single event in a character's arc."""
    event_title: str
    event_type: str
    description: str
    chapter_title: str


@dataclass
class GlobalStoryKnowledge:
    """Global Story Knowledge Layer — Single Source of Truth."""
    title: str = ""
    author: str = ""

    # Deduplicated, merged character list
    characters: list[Character] = field(default_factory=list)

    # Deduplicated, merged scene list
    scenes: list[Scene] = field(default_factory=list)

    # Character name → first chapter where they appeared
    character_first_appearance: dict[str, str] = field(default_factory=dict)

    # Deduplicated relations
    relations: list[Relation] = field(default_factory=list)

    # Deduplicated events (deduplicated by title)
    events: list[dict] = field(default_factory=list)

    # Aggregated location information
    locations: list[LocationInfo] = field(default_factory=list)

    # Story timeline sorted by time marker
    timeline: list[TimelineEntry] = field(default_factory=list)

    # Per-chapter summaries/goals/conflicts extracted by UnifiedExtractionAgent
    chapter_summaries: list[str] = field(default_factory=list)
    chapter_goals: list[str] = field(default_factory=list)
    chapter_conflicts: list[str] = field(default_factory=list)

    # Global story outline (built from merged chapter summaries/goals/conflicts)
    outline: dict = field(default_factory=dict)

    # Character → list of events they participated in (character arc)
    character_arcs: dict[str, list[CharacterArcEntry]] = field(default_factory=dict)

    # All source chapters for traceability
    source_chapters: list[dict] = field(default_factory=list)

    # Merge metadata
    total_chapters: int = 0
    duplicates_removed: int = 0

    # ── Character helpers ────────────────────────────────────────────────

    def get_character(self, name: str) -> Optional[Character]:
        for c in self.characters:
            if c.name == name:
                return c
        return None

    def merge_characters(self, incoming: list[Character]) -> int:
        """Merge character list, deduplicating by name. Returns count of duplicates removed."""
        removed = 0
        for c in incoming:
            existing = self.get_character(c.name)
            if existing is None:
                self.characters.append(c)
            else:
                for t in c.traits:
                    if t not in existing.traits:
                        existing.traits.append(t)
                if len(c.description) > len(existing.description):
                    existing.description = c.description
                removed += 1
        return removed

    def merge_scenes(self, incoming: list[Scene]) -> int:
        """Merge scene list, deduplicating by title only. Stores variant locations in location_variants."""
        removed = 0
        for s in incoming:
            # Find existing scene with same title
            existing = next(
                (e for e in self.scenes if e.title == s.title), None
            )
            if existing is None:
                # First occurrence — use its location as primary
                self.scenes.append(s)
            else:
                # Same title, different location: record variant
                if s.location and s.location != existing.location:
                    if s.location not in existing.location_variants:
                        existing.location_variants.append(s.location)
                    # Merge characters from the variant scene
                    for ch in s.characters:
                        if ch not in existing.characters:
                            existing.characters.append(ch)
                    # Keep longer description
                    if len(s.description) > len(existing.description):
                        existing.description = s.description
                removed += 1
        return removed

    # ── Relation helpers ─────────────────────────────────────────────────

    def merge_relations(self, incoming: list[Relation]) -> int:
        """Merge relations, deduplicating by (from_char, to_char, relation_type)."""
        removed = 0
        for r in incoming:
            seen = any(
                existing.from_char == r.from_char
                and existing.to_char == r.to_char
                and existing.relation_type == r.relation_type
                for existing in self.relations
            )
            if not seen:
                self.relations.append(r)
            else:
                removed += 1
        return removed

    # ── Relation helpers ─────────────────────────────────────────────────

    def merge_relations(self, incoming: list[Relation]) -> int:
        """Merge relations, deduplicating by (from_char, to_char, relation_type)."""
        removed = 0
        for r in incoming:
            seen = any(
                existing.from_char == r.from_char
                and existing.to_char == r.to_char
                and existing.relation_type == r.relation_type
                for existing in self.relations
            )
            if not seen:
                self.relations.append(r)
            else:
                removed += 1
        return removed

    def merge_events(self, incoming: list) -> int:
        """Merge events, deduplicating by title. Returns count of duplicates removed."""
        removed = 0
        for e in incoming:
            title = getattr(e, "title", "") if hasattr(e, "__dataclass_fields__") else e.get("title", "")
            if not any(
                (getattr(existing, "title", "") if hasattr(existing, "__dataclass_fields__") else existing.get("title", "")) == title
                for existing in self.events
            ):
                self.events.append(e if isinstance(e, dict) else e.__dict__)
            else:
                removed += 1
        return removed

    # ── Location analysis ────────────────────────────────────────────────

    def build_locations(self) -> None:
        """Aggregate scene locations into LocationInfo entries."""
        location_map: dict[str, LocationInfo] = {}
        for s in self.scenes:
            loc = s.location or "未知地点"
            if loc not in location_map:
                location_map[loc] = LocationInfo(name=loc, location_type="mixed", frequency=0, scenes=[])
            location_map[loc].frequency += 1
            location_map[loc].scenes.append(s.title)
            indoor_keywords = ["室", "房", "厅", "内", "间", "楼", "家", "屋", "馆", "吧", "店", "舱", "车", "办公室", "会议室", "教室", "医院"]
            outdoor_keywords = ["外", "街", "路", "城", "港", "山", "海", "河", "湖", "岛", "镇", "村", "公园", "森林", "沙漠"]
            if any(kw in loc for kw in indoor_keywords):
                location_map[loc].location_type = "indoor"
            elif any(kw in loc for kw in outdoor_keywords):
                location_map[loc].location_type = "outdoor"
            else:
                location_map[loc].location_type = "mixed"
        self.locations = sorted(location_map.values(), key=lambda x: x.frequency, reverse=True)

    # ── Timeline building ────────────────────────────────────────────────

    def build_timeline(self, chapter_titles: dict[str, str]) -> None:
        """Build sorted timeline from events using time_marker."""
        time_order = {
            "黎明": 0, "凌晨": 0, "清晨": 1, "早晨": 1, "早上": 1, "上午": 2,
            "中午": 3, "午间": 3, "午后": 3,
            "下午": 4, "傍晚": 5, "黄昏": 5,
            "晚上": 6, "夜里": 7, "深夜": 8, "午夜": 8,
        }
        self.timeline = []
        for e in self.events:
            e_dict = e if isinstance(e, dict) else e.__dict__
            marker = e_dict.get("time_marker", "")
            chapter_title = chapter_titles.get(
                e_dict.get("source", {}).get("chapter_id", "") if isinstance(e_dict.get("source"), dict) else "", ""
            )
            self.timeline.append(TimelineEntry(
                time_marker=marker or "未标注",
                location=e_dict.get("location", ""),
                event_title=e_dict.get("title", ""),
                event_type=e_dict.get("event_type", ""),
                participants=e_dict.get("participants", []),
                chapter_title=chapter_title,
            ))
        self.timeline.sort(key=lambda x: (time_order.get(x.time_marker, 50), x.event_title))

    # ── Character arc building ───────────────────────────────────────────

    def build_character_arcs(self) -> None:
        """Build per-character event arcs."""
        self.character_arcs = defaultdict(list)
        chapter_map = {}
        for e in self.events:
            e_dict = e if isinstance(e, dict) else e.__dict__
            cid = e_dict.get("source", {}).get("chapter_id", "") if isinstance(e_dict.get("source"), dict) else ""
            chapter_map[cid] = e_dict.get("source", {}).get("chapter_title", "") if isinstance(e_dict.get("source"), dict) else ""
        for e in self.events:
            e_dict = e if isinstance(e, dict) else e.__dict__
            cid = e_dict.get("source", {}).get("chapter_id", "") if isinstance(e_dict.get("source"), dict) else ""
            chapter_title = chapter_map.get(cid, "")
            for participant in e_dict.get("participants", []):
                self.character_arcs[participant].append(CharacterArcEntry(
                    event_title=e_dict.get("title", ""),
                    event_type=e_dict.get("event_type", ""),
                    description=e_dict.get("description", ""),
                    chapter_title=chapter_title,
                ))

    # ── Global outline building (Rule Engine) ─────────────────────────────────

    def build_global_outline(self) -> None:
        """Build global story outline from merged per-chapter summaries/goals/conflicts.

        This is a Rule Engine operation: no LLM needed.
        The LLM did its job in UnifiedExtractionAgent (per-chapter summary/goal/conflict).
        The rule engine assembles them into a coherent global outline.
        """
        if not self.chapter_summaries:
            return

        all_text = " ".join(self.chapter_summaries)
        conflicts_text = " ".join(self.chapter_conflicts)
        genre = _infer_genre(all_text, conflicts_text)
        theme = _infer_theme(self.chapter_conflicts)
        main_conflict = _infer_main_conflict(self.chapter_conflicts)
        arc_summary = "\n".join(
            f"第{i+1}章：{s}"
            for i, s in enumerate(self.chapter_summaries)
        )
        act_summaries = _build_acts(self.chapter_summaries)
        key_events = [
            e.get("title", "") if isinstance(e, dict) else ""
            for e in self.events
            if (isinstance(e, dict) and e.get("event_type") in ("turning_point", "revelation"))
        ]
        key_events += self.chapter_conflicts[:3]

        self.outline = {
            "genre": genre,
            "theme": theme,
            "main_conflict": main_conflict,
            "arc_summary": arc_summary,
            "act_summaries": act_summaries,
            "key_plot_points": key_events[:5],
        }

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        def strip_source(obj):
            if hasattr(obj, "__dataclass_fields__"):
                result = {}
                for name, f in obj.__dataclass_fields__.items():
                    val = getattr(obj, name)
                    if isinstance(val, list):
                        result[name] = [strip_source(v) for v in val]
                    elif hasattr(val, "__dataclass_fields__"):
                        result[name] = strip_source(val)
                    else:
                        result[name] = val
                return result
            elif isinstance(obj, dict):
                return {k: strip_source(v) for k, v in obj.items()}
            return obj

        data = strip_source(self)
        return {
            "title": self.title,
            "author": self.author,
            "total_chapters": self.total_chapters,
            "duplicates_removed": self.duplicates_removed,
            "character_first_appearance": self.character_first_appearance,
            "source_chapters": self.source_chapters,
            **data,
        }


class KnowledgeMerger:
    """Merges Local Knowledge from each chapter into a Global SKL."""

    def __init__(self, title: str = "", author: str = ""):
        self.gsk = GlobalStoryKnowledge(title=title, author=author)

    def merge_local(self, local: LocalKnowledge) -> GlobalStoryKnowledge:
        """Merge one chapter's local knowledge into the global SKL."""
        self.gsk.source_chapters.append({
            "chapter_id": local.chapter_id,
            "chapter_title": local.chapter_title,
        })

        chars_removed = self.gsk.merge_characters(local.characters)
        scenes_removed = self.gsk.merge_scenes(local.scenes)
        rels_removed = self.gsk.merge_relations(local.relations)
        events_removed = self.gsk.merge_events(local.events)

        self.gsk.duplicates_removed += chars_removed + scenes_removed + rels_removed + events_removed

        # Track first appearance
        for c in local.characters:
            name = c.name
            if name not in self.gsk.character_first_appearance:
                src = c.source
                self.gsk.character_first_appearance[name] = (
                    src.chapter_title if src else local.chapter_title
                )

        # Per-chapter narrative metadata
        if local.chapter_summary:
            self.gsk.chapter_summaries.append(local.chapter_summary)
        if local.chapter_goal:
            self.gsk.chapter_goals.append(local.chapter_goal)
        if local.chapter_conflict:
            self.gsk.chapter_conflicts.append(local.chapter_conflict)

        self.gsk.total_chapters = len(self.gsk.source_chapters)
        return self.gsk

    def merge_all(self, locals_list: list[LocalKnowledge]) -> GlobalStoryKnowledge:
        """Merge multiple chapters' local knowledge in order, then build derived fields."""
        for local in locals_list:
            self.merge_local(local)
        # Build derived fields after all chapters merged
        self.gsk.build_locations()
        chapter_titles = {ch["chapter_id"]: ch["chapter_title"] for ch in self.gsk.source_chapters}
        self.gsk.build_timeline(chapter_titles)
        self.gsk.build_character_arcs()
        self.gsk.build_global_outline()
        return self.gsk

    def get_global(self) -> GlobalStoryKnowledge:
        return self.gsk


def merge_chapters_to_skl(
    title: str,
    author: str,
    chapters: list,
    all_characters: list[Character],
    all_scenes: list[Scene],
    all_relations: list[Relation],
    all_events: list,
    chapter_summaries: list = None,
    chapter_goals: list = None,
    chapter_conflicts: list = None,
    timeline_agent=None,
    location_agent=None,
) -> GlobalStoryKnowledge:
    """One-shot merge from chapter-based extraction results.

    Global outline is built internally by GlobalStoryKnowledge.build_global_outline()
    from per-chapter summaries/goals/conflicts (Rule Engine — no LLM needed here).
    """
    from core.chapter_parser import Chapter

    chapter_summaries = chapter_summaries or []
    chapter_goals = chapter_goals or []
    chapter_conflicts = chapter_conflicts or []

    chapter_map: dict[str, list[Character]] = defaultdict(list)
    chapter_scenes: dict[str, list[Scene]] = defaultdict(list)
    chapter_relations: dict[str, list[Relation]] = defaultdict(list)
    chapter_events: dict[str, list[dict]] = defaultdict(list)

    for c in all_characters:
        if c.source:
            chapter_map[c.source.chapter_id].append(c)
        else:
            chapter_map["unknown"].append(c)

    for s in all_scenes:
        if s.source:
            chapter_scenes[s.source.chapter_id].append(s)
        else:
            chapter_scenes["unknown"].append(s)

    for r in all_relations:
        if r.source:
            chapter_relations[r.source.chapter_id].append(r)
        else:
            chapter_relations["unknown"].append(r)

    for e in all_events:
        e_dict = e if isinstance(e, dict) else e.__dict__
        src = e_dict.get("source", {}) if isinstance(e_dict, dict) else {}
        cid = src.get("chapter_id", "unknown") if isinstance(src, dict) else "unknown"
        chapter_events[cid].append(e_dict)

    all_chapter_ids = {getattr(ch, "id", f"ch_{i+1:03d}"): getattr(ch, "title", "未知")
                       for i, ch in enumerate(chapters)}
    for cid in chapter_map:
        if cid not in all_chapter_ids:
            all_chapter_ids[cid] = cid

    merger = KnowledgeMerger(title=title, author=author)
    locals_list = []
    for i, ch in enumerate(chapters):
        cid = getattr(ch, "id", f"ch_{i+1:03d}")
        ctitle = getattr(ch, "title", all_chapter_ids.get(cid, "未知"))
        locals_list.append(LocalKnowledge(
            chapter_id=cid,
            chapter_title=ctitle,
            chapter_summary=chapter_summaries[i] if i < len(chapter_summaries) else "",
            chapter_goal=chapter_goals[i] if i < len(chapter_goals) else "",
            chapter_conflict=chapter_conflicts[i] if i < len(chapter_conflicts) else "",
            characters=chapter_map.get(cid, []),
            scenes=chapter_scenes.get(cid, []),
            relations=chapter_relations.get(cid, []),
            events=chapter_events.get(cid, []),
        ))

    # Handle items without source (fallback to chapter 1)
    if chapter_map.get("unknown") and locals_list:
        locals_list[0].characters.extend(chapter_map["unknown"])
    if chapter_scenes.get("unknown") and locals_list:
        locals_list[0].scenes.extend(chapter_scenes["unknown"])
    if chapter_relations.get("unknown") and locals_list:
        locals_list[0].relations.extend(chapter_relations["unknown"])
    if chapter_events.get("unknown") and locals_list:
        locals_list[0].events.extend(chapter_events["unknown"])

    result = merger.merge_all(locals_list)
    # outline is now built by build_global_outline() inside merge_all()

    # ── Rich agents for locations & timeline ───────────────────────────────────
    if location_agent is not None:
        result.locations = location_agent.build_locations(result.scenes)
    if timeline_agent is not None:
        chapter_titles = {ch["chapter_id"]: ch["chapter_title"] for ch in result.source_chapters}
        result.timeline = timeline_agent.build_timeline(result.events, chapter_titles)

    return result


# ── Module-level helper functions for Global Outline (Rule Engine) ──────────────

def _infer_genre(summaries_text: str, conflicts_text: str) -> str:
    genre_signals = {
        "thriller": ["调查", "秘密", "失踪", "神秘", "阴谋", "真相", "线索"],
        "horror": ["恐怖", "惊悚", "黑暗", "危险", "恐惧", "诅咒", "鬼"],
        "romance": ["爱情", "恋人", "心动", "告白", "感情", "亲密"],
        "fantasy": ["魔法", "异世界", "超自然", "奇幻", "妖怪", "仙侠"],
        "sci-fi": ["科技", "飞船", "外星", "未来", "机器人", "太空"],
    }
    text = summaries_text + " " + conflicts_text
    for genre, keywords in genre_signals.items():
        if sum(1 for kw in keywords if kw in text) >= 2:
            return genre
    return "general"


def _infer_theme(conflicts: list[str]) -> str:
    conflict_text = " ".join(conflicts) if conflicts else ""
    if "真相" in conflict_text or "秘密" in conflict_text:
        return "真相与掩盖 — 追寻被隐藏的事实"
    if "威胁" in conflict_text or "危险" in conflict_text:
        return "生存与抉择 — 面对危险时的道德困境"
    if "追寻" in conflict_text or "目标" in conflict_text:
        return "追寻与成长 — 角色追寻目标的成长之路"
    return "悬念与冲突 — 故事的核心张力"


def _infer_main_conflict(conflicts: list[str]) -> str:
    if not conflicts:
        return "待分析"
    return max(conflicts, key=len)


def _build_acts(chapter_summaries: list[str]) -> list[dict]:
    if not chapter_summaries:
        return []
    n = len(chapter_summaries)
    if n == 1:
        return [{"act_number": 1, "title": "开端与结局", "summary": chapter_summaries[0], "key_scenes": []}]
    if n == 2:
        return [
            {"act_number": 1, "title": "开端", "summary": chapter_summaries[0], "key_scenes": []},
            {"act_number": 2, "title": "发展与结局", "summary": "\n".join(chapter_summaries[1:]), "key_scenes": []},
        ]
    cut1 = max(1, n // 3)
    cut2 = max(cut1 + 1, 2 * n // 3)
    return [
        {"act_number": 1, "title": "开端", "summary": "\n".join(chapter_summaries[:cut1]), "key_scenes": []},
        {"act_number": 2, "title": "发展", "summary": "\n".join(chapter_summaries[cut1:cut2]), "key_scenes": []},
        {"act_number": 3, "title": "高潮与结局", "summary": "\n".join(chapter_summaries[cut2:]), "key_scenes": []},
    ]
