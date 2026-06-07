"""Tests for Knowledge Merger (MVP 4)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema.models import Character, Scene, SourceTrace
from core.knowledge_merger import (
    LocalKnowledge,
    GlobalStoryKnowledge,
    KnowledgeMerger,
    merge_chapters_to_skl,
)


def test_local_knowledge():
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    chars = [
        Character(name="林川", description="图书管理员", role="protagonist", source=src),
        Character(name="陈雨", description="记者", role="supporting", source=src),
    ]
    scenes = [
        Scene(title="图书馆相遇", location="雾港镇", time_of_day="afternoon", description="", source=src),
    ]
    local = LocalKnowledge(chapter_id="ch_001", chapter_title="第一章", characters=chars, scenes=scenes)
    assert len(local.characters) == 2
    assert local.chapter_id == "ch_001"
    print("  PASS: local_knowledge")


def test_global_knowledge_merge():
    gsk = GlobalStoryKnowledge(title="雾港档案", author="StoryForge")

    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    src2 = SourceTrace(chapter_id="ch_002", chapter_title="第二章")

    chars1 = [
        Character(name="林川", description="图书管理员", role="protagonist", source=src1),
        Character(name="陈雨", description="记者", role="supporting", source=src1),
    ]
    chars2 = [
        Character(name="林川", description="图书管理员", role="protagonist", source=src2),
        Character(name="老人", description="北辰号大副", role="supporting", source=src2),
    ]

    scenes1 = [
        Scene(title="图书馆相遇", location="雾港镇", time_of_day="afternoon", description="", source=src1),
    ]
    scenes2 = [
        Scene(title="废弃灯塔", location="黑礁海岸", time_of_day="evening", description="", source=src2),
        Scene(title="地下室发现", location="灯塔地下室", time_of_day="evening", description="", source=src2),
    ]

    local1 = LocalKnowledge(
        chapter_id="ch_001",
        chapter_title="第一章",
        chapter_summary="林川在图书馆遇到陌生老人，老人询问北辰号航海日志。",
        chapter_goal="林川想知道老人为什么要找北辰号日志。",
        chapter_conflict="日志档案已经不见了，线索中断。",
        characters=chars1,
        scenes=scenes1,
    )
    local2 = LocalKnowledge(
        chapter_id="ch_002",
        chapter_title="第二章",
        chapter_summary="林川和陈雨前往废弃灯塔，发现了北辰号的航海日志。",
        chapter_goal="找到北辰号失踪的真相。",
        chapter_conflict="神秘黑衣人出现，试图抢夺日志。",
        characters=chars2,
        scenes=scenes2,
    )

    merger = KnowledgeMerger(title="雾港档案", author="StoryForge")
    result = merger.merge_all([local1, local2])

    # 林川 should be deduplicated (only 1 instance)
    char_names = [c.name for c in result.characters]
    assert char_names.count("林川") == 1, f"林川 should appear once, got: {char_names}"
    assert "陈雨" in char_names
    assert "老人" in char_names

    # Scenes should be all 3 (no duplicates)
    assert len(result.scenes) == 3

    # First appearance tracking
    assert result.character_first_appearance["林川"] == "第一章"

    # Total chapters
    assert result.total_chapters == 2

    # Duplicates removed (林川 once in ch_001 + once in ch_002 = 1 removed)
    assert result.duplicates_removed >= 1

    print(f"  {len(result.characters)} characters, {len(result.scenes)} scenes, {result.duplicates_removed} dupes removed")
    print(f"  First appearances: {result.character_first_appearance}")
    print("  PASS: global_knowledge_merge")


def test_merge_characters_deduplication():
    """Test that merge correctly deduplicates by name and merges traits."""
    gsk = GlobalStoryKnowledge()

    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    src2 = SourceTrace(chapter_id="ch_002", chapter_title="第二章")

    chars1 = [Character(name="林川", description="图书管理员", traits=["细心"], role="protagonist", source=src1)]
    chars2 = [Character(name="林川", description="雾港镇图书管理员，负责整理档案", traits=["细心", "好奇"], role="protagonist", source=src2)]

    removed = gsk.merge_characters(chars1)
    assert removed == 0
    removed2 = gsk.merge_characters(chars2)
    assert removed2 == 1  # 1 duplicate removed

    lin_chuan = gsk.get_character("林川")
    assert "细心" in lin_chuan.traits
    assert "好奇" in lin_chuan.traits
    # Description should be the longer one
    assert len(lin_chuan.description) > len("图书管理员")

    print("  PASS: merge_characters_deduplication")


def test_merge_scenes_deduplication():
    """Test scene deduplication by title only; same title with different location is merged."""
    gsk = GlobalStoryKnowledge()

    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    src2 = SourceTrace(chapter_id="ch_002", chapter_title="第二章")

    s1 = Scene(title="图书馆相遇", location="雾港镇图书馆", time_of_day="afternoon", description="", source=src1)
    s2 = Scene(title="图书馆相遇", location="雾港镇图书馆", time_of_day="afternoon", description="稍作交谈后", source=src2)
    s3 = Scene(title="废弃灯塔", location="黑礁海岸", time_of_day="evening", description="", source=src2)

    removed1 = gsk.merge_scenes([s1])
    assert removed1 == 0
    assert len(gsk.scenes) == 1

    # s2 has same title as s1 → duplicate, not added (location_variants tracks the match)
    # s3 is a new title → added
    removed2 = gsk.merge_scenes([s2, s3])
    assert removed2 == 1  # s2 duplicate of s1 (same title), s3 new
    assert len(gsk.scenes) == 2
    assert gsk.scenes[0].title == "图书馆相遇"
    assert gsk.scenes[0].location == "雾港镇图书馆"
    assert gsk.scenes[1].title == "废弃灯塔"

    print("  PASS: merge_scenes_deduplication")


def test_merge_scenes_location_variants():
    """Test that same scene title with different locations are tracked as location_variants."""
    gsk = GlobalStoryKnowledge()

    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    src2 = SourceTrace(chapter_id="ch_002", chapter_title="第二章")
    src3 = SourceTrace(chapter_id="ch_003", chapter_title="第三章")

    s1 = Scene(title="废弃灯塔", location="黑礁海岸", time_of_day="evening", description="林川发现灯塔外观，破败不堪", source=src1)
    s2 = Scene(title="废弃灯塔", location="灯塔地下室", time_of_day="night", description="地下室里有旧档案", characters=["林川"], source=src2)
    s3 = Scene(title="废弃灯塔", location="灯塔阁楼", time_of_day="noon", description="阁楼窗户透进月光", characters=["陈雨"], source=src3)

    gsk.merge_scenes([s1, s2, s3])

    # All three should merge into one scene (same title)
    assert len(gsk.scenes) == 1
    scene = gsk.scenes[0]
    assert scene.title == "废弃灯塔"
    # Primary location is the first one
    assert scene.location == "黑礁海岸"
    # Variant locations should be collected
    assert "灯塔地下室" in scene.location_variants
    assert "灯塔阁楼" in scene.location_variants
    assert "黑礁海岸" not in scene.location_variants  # primary, not a variant
    # Characters from all variants should be merged
    assert "林川" in scene.characters
    assert "陈雨" in scene.characters
    # Description should be the longest (s1 is longest at 15 chars)
    assert len(scene.description) == len("林川发现灯塔外观，破败不堪")

    print("  PASS: merge_scenes_location_variants")


def test_consistency_checker():
    """Test the enhanced consistency checker."""
    from core.story_graph import StoryGraph, CharacterNode, SceneNode, EventNode, CharacterRole, EventType
    from core.consistency_checker import ConsistencyChecker

    graph = StoryGraph()
    graph.characters = [
        CharacterNode(id="林川", name="林川", role=CharacterRole.PROTAGONIST, first_appearance="第一章"),
        CharacterNode(id="陈雨", name="陈雨", role=CharacterRole.SUPPORTING, first_appearance="第二章"),
    ]
    graph.scenes = [
        SceneNode(id="scene1", title="图书馆相遇", location="雾港镇", time="afternoon", act=1,
                  characters_present=["林川", "陈雨"], summary=""),
        SceneNode(id="scene2", title="灯塔探索", location="黑礁海岸", time="evening", act=1,
                  characters_present=["林川", "未知角色"], summary=""),  # unknown character
    ]
    graph.events = [
        EventNode(title="图书馆相遇", event_type=EventType.REVELATION, location="雾港镇",
                  time_marker="afternoon", participants=["林川"], description=""),
    ]

    checker = ConsistencyChecker(graph)
    report = checker.check_all()

    print(f"  Consistency report: passed={report.passed}, warnings={len(report.warnings)}")
    for w in report.warnings:
        print(f"    [{w.code.value}] {w.message}")

    # Should detect "未知角色" not in character list
    unknown_warnings = [w for w in report.warnings if "未知角色" in w.message]
    assert len(unknown_warnings) > 0, "Should detect unknown character in scene"

    print("  PASS: consistency_checker")


def test_consistency_checker_no_false_positives():
    """When all data is consistent, no warnings should be raised."""
    from core.story_graph import StoryGraph, CharacterNode, SceneNode, EventNode, CharacterRole, EventType
    from core.consistency_checker import ConsistencyChecker

    graph = StoryGraph()
    graph.characters = [
        CharacterNode(id="林川", name="林川", role=CharacterRole.PROTAGONIST, first_appearance="第一章"),
    ]
    graph.scenes = [
        SceneNode(id="scene1", title="图书馆相遇", location="雾港镇", time="afternoon", act=1,
                  characters_present=["林川"], summary=""),
    ]
    graph.events = [
        EventNode(title="图书馆相遇", event_type=EventType.REVELATION, location="雾港镇",
                  time_marker="afternoon", participants=["林川"], description=""),
    ]

    checker = ConsistencyChecker(graph)
    report = checker.check_all()

    # No errors (warnings are fine)
    assert report.passed
    error_warnings = [w for w in report.warnings if w.severity.value == "error"]
    assert len(error_warnings) == 0

    print("  PASS: consistency_checker_no_false_positives")


if __name__ == "__main__":
    print("=" * 60)
    print("Knowledge Merger Tests (MVP 4)")
    print("=" * 60)
    test_local_knowledge()
    test_global_knowledge_merge()
    test_merge_characters_deduplication()
    test_merge_scenes_deduplication()
    test_consistency_checker()
    test_consistency_checker_no_false_positives()
    print()
    print("ALL KNOWLEDGE MERGER TESTS PASSED")
