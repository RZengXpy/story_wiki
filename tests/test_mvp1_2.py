"""Tests for MVP 1 (Retrieval Filtering) and MVP 2 (TimelineAgent / LocationAgent)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema.models import Character, Scene, Relation, SourceTrace
from core.knowledge_merger import (
    LocalKnowledge,
    GlobalStoryKnowledge,
    KnowledgeMerger,
    merge_chapters_to_skl,
)
from agent.script_agent import filter_relevant_context
from agent.timeline_agent import TimelineAgent, TimelineEntry
from agent.location_agent import LocationAgent, LocationInfo


# ─── MVP 1: Retrieval Filtering ───────────────────────────────────────────────

def test_filter_relevant_context_characters():
    """Only characters appearing in the scene should be included."""
    skl = {
        "characters": [
            {"name": "林川", "description": "图书管理员", "role": "protagonist", "traits": ["细心"]},
            {"name": "陈雨", "description": "记者", "role": "supporting", "traits": ["勇敢"]},
            {"name": "老人", "description": "北辰号大副", "role": "supporting", "traits": ["神秘"]},
        ],
        "events": [],
        "relations": [],
        "outline": {},
    }
    ctx = filter_relevant_context(
        skl, scene_title="图书馆相遇",
        scene_location="雾港图书馆",
        scene_time="下午",
        characters_present=["林川", "陈雨"],
    )
    names = {c["name"] for c in ctx["characters"]}
    assert "林川" in names
    assert "陈雨" in names
    assert "老人" not in names
    print("  PASS: filter_relevant_context_characters")


def test_filter_relevant_context_events_by_character():
    """Events involving scene characters should be included."""
    skl = {
        "characters": [{"name": "林川"}],
        "events": [
            {"title": "图书馆相遇", "event_type": "revelation",
             "location": "雾港图书馆", "participants": ["林川", "陈雨"]},
            {"title": "灯塔探索", "event_type": "conflict",
             "location": "黑礁海岸", "participants": ["林川"]},
            {"title": "神秘失踪", "event_type": "turning_point",
             "location": "废弃灯塔", "participants": ["老人", "徐远"]},
        ],
        "relations": [],
        "outline": {},
    }
    ctx = filter_relevant_context(
        skl, scene_title="图书馆相遇",
        scene_location="雾港图书馆",
        scene_time="下午",
        characters_present=["林川", "陈雨"],
    )
    event_titles = {e["title"] for e in ctx["events"]}
    assert "图书馆相遇" in event_titles
    assert "灯塔探索" in event_titles
    assert "神秘失踪" not in event_titles
    print("  PASS: filter_relevant_context_events_by_character")


def test_filter_relevant_context_events_by_location():
    """Events at the same location should be included even if character differs."""
    skl = {
        "characters": [{"name": "林川"}],
        "events": [
            {"title": "灯塔探索", "event_type": "conflict",
             "location": "废弃灯塔地下室", "participants": ["林川"]},
            {"title": "神秘文件", "event_type": "revelation",
             "location": "灯塔地下室", "participants": ["老人"]},
        ],
        "relations": [],
        "outline": {},
    }
    ctx = filter_relevant_context(
        skl, scene_title="灯塔地下室",
        scene_location="废弃灯塔地下室",
        scene_time="傍晚",
        characters_present=["林川"],
    )
    event_titles = {e["title"] for e in ctx["events"]}
    assert "灯塔探索" in event_titles
    assert "神秘文件" in event_titles
    print("  PASS: filter_relevant_context_events_by_location")


def test_filter_relevant_context_relations():
    """Only relations involving scene characters should be included."""
    skl = {
        "characters": [],
        "events": [],
        "relations": [
            {"from_char": "林川", "to_char": "陈雨", "relation_type": "friend", "description": ""},
            {"from_char": "老人", "to_char": "徐远", "relation_type": "professional", "description": ""},
        ],
        "outline": {},
    }
    ctx = filter_relevant_context(
        skl, scene_title="图书馆相遇",
        scene_location="雾港图书馆",
        scene_time="下午",
        characters_present=["林川", "陈雨"],
    )
    rel_pairs = {(r["from_char"], r["to_char"]) for r in ctx["relations"]}
    assert ("林川", "陈雨") in rel_pairs
    assert ("老人", "徐远") not in rel_pairs
    print("  PASS: filter_relevant_context_relations")


def test_filter_relevant_context_empty_scene():
    """Empty scene with no characters/events/relations should not crash."""
    skl = {
        "characters": [{"name": "林川"}],
        "events": [{"title": "事件A", "participants": ["林川"]}],
        "relations": [{"from_char": "林川", "to_char": "陈雨"}],
        "outline": {"main_conflict": "测试"},
    }
    ctx = filter_relevant_context(
        skl, scene_title="空场景",
        scene_location="",
        scene_time="",
        characters_present=[],
    )
    assert ctx["characters"] == []
    assert ctx["events"] == []
    assert ctx["relations"] == []
    assert ctx["outline"]["main_conflict"] == "测试"
    print("  PASS: filter_relevant_context_empty_scene")


def test_filter_relevant_context_outline_always_included():
    """Outline should always be passed through."""
    skl = {
        "characters": [],
        "events": [],
        "relations": [],
        "outline": {"genre": "thriller", "main_conflict": "北辰号失踪之谜"},
    }
    ctx = filter_relevant_context(
        skl, "scene", "loc", "time", ["林川"],
    )
    assert ctx["outline"]["genre"] == "thriller"
    assert ctx["outline"]["main_conflict"] == "北辰号失踪之谜"
    print("  PASS: filter_relevant_context_outline_always_included")


# ─── MVP 2: TimelineAgent ─────────────────────────────────────────────────────

def test_timeline_agent_build():
    """TimelineAgent builds sorted timeline from events."""
    agent = TimelineAgent()
    events = [
        {"title": "午夜行动", "event_type": "conflict",
         "time_marker": "午夜", "location": "海面", "participants": ["林川"],
         "source": {"chapter_id": "ch_001", "chapter_title": "第一章"}},
        {"title": "清晨出发", "event_type": "transition",
         "time_marker": "清晨", "location": "码头", "participants": ["林川", "陈雨"],
         "source": {"chapter_id": "ch_002", "chapter_title": "第二章"}},
        {"title": "午后搜索", "event_type": "revelation",
         "time_marker": "下午", "location": "灯塔", "participants": ["林川"],
         "source": {"chapter_id": "ch_003", "chapter_title": "第三章"}},
    ]
    chapter_titles = {"ch_001": "第一章", "ch_002": "第二章", "ch_003": "第三章"}
    timeline = agent.build_timeline(events, chapter_titles)

    assert len(timeline) == 3
    assert timeline[0].time_marker == "清晨"      # 清晨 = 1
    assert timeline[1].time_marker == "下午"      # 下午 = 4
    assert timeline[2].time_marker == "午夜"     # 午夜 = 8
    assert timeline[0].event_title == "清晨出发"
    assert timeline[1].event_title == "午后搜索"
    assert timeline[2].event_title == "午夜行动"
    print("  PASS: timeline_agent_build")


def test_timeline_agent_analyze_no_llm():
    """TimelineAgent.analyze() falls back to rule-based when no LLM is available."""
    agent = TimelineAgent()
    events = [
        {"title": "事件A", "event_type": "transition",
         "time_marker": "中午", "location": "图书馆", "participants": [],
         "source": {"chapter_id": "ch_001", "chapter_title": "第一章"}},
    ]
    chapter_titles = {"ch_001": "第一章"}
    result = agent.analyze(events, chapter_titles)

    assert len(result.entries) == 1
    assert result.causal_chains == []
    assert result.inciting_incident == ""
    print("  PASS: timeline_agent_analyze_no_llm")


# ─── MVP 2: LocationAgent ─────────────────────────────────────────────────────

def test_location_agent_build():
    """LocationAgent aggregates and classifies locations."""
    agent = LocationAgent()
    scenes = [
        Scene(title="图书馆相遇", location="雾港镇图书馆", time_of_day="afternoon", description=""),
        Scene(title="借阅记录", location="图书馆阅览室", time_of_day="afternoon", description=""),
        Scene(title="灯塔探索", location="黑礁海岸灯塔", time_of_day="evening", description=""),
        Scene(title="码头等待", location="雾港码头", time_of_day="morning", description=""),
    ]
    locations = agent.build_locations(scenes)

    assert len(locations) == 4
    loc_map = {l.name: l for l in locations}

    # Check frequency
    assert loc_map["雾港镇图书馆"].frequency == 1
    assert loc_map["黑礁海岸灯塔"].frequency == 1

    # Check type classification
    assert loc_map["雾港镇图书馆"].location_type == "indoor"
    assert loc_map["图书馆阅览室"].location_type == "indoor"
    assert loc_map["雾港码头"].location_type == "outdoor"
    print("  PASS: location_agent_build")


def test_location_agent_classify_keywords():
    """Location type classification uses keyword matching."""
    agent = LocationAgent()
    assert agent._classify_type("地下室") == "indoor"
    assert agent._classify_type("医院") == "indoor"
    assert agent._classify_type("灯塔外") == "outdoor"
    assert agent._classify_type("海岸") == "outdoor"
    assert agent._classify_type("码头") == "outdoor"
    assert agent._classify_type("神秘地点") == "mixed"
    print("  PASS: location_agent_classify_keywords")


def test_location_agent_analyze_no_llm():
    """LocationAgent.analyze_locations() falls back when no LLM is available."""
    agent = LocationAgent()
    scenes = [
        Scene(title="S1", location="图书馆", time_of_day="day", description=""),
        Scene(title="S2", location="图书馆", time_of_day="night", description=""),
        Scene(title="S3", location="灯塔", time_of_day="day", description=""),
    ]
    result = agent.analyze_locations(scenes)

    assert len(result.locations) == 2
    loc_map = {l.name: l for l in result.locations}
    assert loc_map["图书馆"].frequency == 2
    assert loc_map["灯塔"].frequency == 1
    # Recurring locations: only 图书馆 appears > 1 time
    assert "图书馆" in result.recurring_locations
    print("  PASS: location_agent_analyze_no_llm")


# ─── MVP 2: Integration — merge_chapters_to_skl with Agents ──────────────────

def test_merge_chapters_to_skl_with_agents():
    """merge_chapters_to_skl accepts timeline_agent and location_agent params."""
    from core.chapter_parser import Chapter

    from agent.event_agent import Event

    chapters = [
        Chapter(id="ch_001", number=1, title="第一章", content="内容1",
                start_char=0, end_char=100),
        Chapter(id="ch_002", number=2, title="第二章", content="内容2",
                start_char=101, end_char=200),
    ]
    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    src2 = SourceTrace(chapter_id="ch_002", chapter_title="第二章")
    characters = [
        Character(name="林川", description="图书管理员", role="protagonist", source=src1),
        Character(name="陈雨", description="记者", role="supporting", source=src2),
    ]
    scenes = [
        Scene(title="图书馆相遇", location="雾港镇图书馆", time_of_day="afternoon",
              description="", source=src1),
        Scene(title="灯塔探索", location="黑礁海岸", time_of_day="evening",
              description="", source=src2),
    ]
    relations = [
        Relation(from_char="林川", to_char="陈雨", relation_type="friend",
                 description="", source=src1),
    ]
    events = [
        Event(
            title="相遇", event_type="revelation", location="图书馆",
            time_marker="下午", participants=["林川"],
            source={"chapter_id": "ch_001", "chapter_title": "第一章"},
        ),
    ]

    timeline_agent = TimelineAgent()
    location_agent = LocationAgent()

    gsk = merge_chapters_to_skl(
        title="雾港档案", author="StoryForge",
        chapters=chapters,
        all_characters=characters,
        all_scenes=scenes,
        all_relations=relations,
        all_events=events,
        outline={"genre": "thriller"},
        timeline_agent=timeline_agent,
        location_agent=location_agent,
    )

    assert len(gsk.characters) == 2
    assert len(gsk.scenes) == 2
    assert len(gsk.timeline) == 1
    assert len(gsk.locations) == 2
    loc_map = {l.name: l for l in gsk.locations}
    assert loc_map["雾港镇图书馆"].location_type == "indoor"
    assert loc_map["黑礁海岸"].location_type == "outdoor"
    print("  PASS: merge_chapters_to_skl_with_agents")


def test_merge_chapters_to_skl_backward_compat():
    """merge_chapters_to_skl works without agents (backward compatible)."""
    from core.chapter_parser import Chapter

    chapters = [
        Chapter(id="ch_001", number=1, title="第一章", content="内容",
                start_char=0, end_char=100),
    ]
    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    characters = [
        Character(name="林川", description="图书管理员", role="protagonist", source=src1),
    ]
    scenes = [
        Scene(title="图书馆", location="雾港镇图书馆", time_of_day="day",
              description="", source=src1),
    ]

    gsk = merge_chapters_to_skl(
        title="雾港档案", author="StoryForge",
        chapters=chapters,
        all_characters=characters,
        all_scenes=scenes,
        all_relations=[],
        all_events=[],
        outline={},
        # no agents
    )

    assert len(gsk.characters) == 1
    assert len(gsk.scenes) == 1
    assert len(gsk.timeline) == 0
    print("  PASS: merge_chapters_to_skl_backward_compat")


# ─── MVP 2: TimelineEntry dataclass compatibility ──────────────────────────────

def test_timeline_entry_dataclass():
    """TimelineEntry has all required fields."""
    entry = TimelineEntry(
        time_marker="下午",
        location="图书馆",
        event_title="相遇",
        event_type="revelation",
        participants=["林川"],
        chapter_title="第一章",
        causal_predecessors=["序章"],
        causal_successors=["离别"],
    )
    assert entry.time_marker == "下午"
    assert entry.causal_predecessors == ["序章"]
    assert entry.causal_successors == ["离别"]
    print("  PASS: timeline_entry_dataclass")


def test_location_info_dataclass():
    """LocationInfo has all required fields."""
    loc = LocationInfo(
        name="雾港镇图书馆",
        location_type="indoor",
        frequency=3,
        scenes=["S1", "S2", "S3"],
        narrative_significance="故事的核心地点",
        emotional_atmosphere="神秘、压抑",
    )
    assert loc.frequency == 3
    assert loc.narrative_significance == "故事的核心地点"
    assert loc.emotional_atmosphere == "神秘、压抑"
    print("  PASS: location_info_dataclass")


# ─── Run all ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("MVP 1 & 2 Tests — Retrieval + TimelineAgent + LocationAgent")
    print("=" * 60)
    print("\n── MVP 1: Retrieval Filtering ──")
    test_filter_relevant_context_characters()
    test_filter_relevant_context_events_by_character()
    test_filter_relevant_context_events_by_location()
    test_filter_relevant_context_relations()
    test_filter_relevant_context_empty_scene()
    test_filter_relevant_context_outline_always_included()

    print("\n── MVP 2: TimelineAgent ──")
    test_timeline_agent_build()
    test_timeline_agent_analyze_no_llm()
    test_timeline_entry_dataclass()

    print("\n── MVP 2: LocationAgent ──")
    test_location_agent_build()
    test_location_agent_classify_keywords()
    test_location_agent_analyze_no_llm()
    test_location_info_dataclass()

    print("\n── MVP 2: Integration ──")
    test_merge_chapters_to_skl_with_agents()
    test_merge_chapters_to_skl_backward_compat()

    print()
    print("ALL MVP 1 & 2 TESTS PASSED")
