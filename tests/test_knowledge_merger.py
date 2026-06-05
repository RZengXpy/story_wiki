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

    local1 = LocalKnowledge("ch_001", "第一章", chars1, scenes1)
    local2 = LocalKnowledge("ch_002", "第二章", chars2, scenes2)

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
    """Test scene deduplication by (title, location)."""
    gsk = GlobalStoryKnowledge()

    src1 = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    src2 = SourceTrace(chapter_id="ch_002", chapter_title="第二章")

    s1 = Scene(title="图书馆相遇", location="雾港镇图书馆", time_of_day="afternoon", description="", source=src1)
    s2 = Scene(title="图书馆相遇", location="雾港镇图书馆", time_of_day="afternoon", description="稍作交谈后", source=src2)
    s3 = Scene(title="废弃灯塔", location="黑礁海岸", time_of_day="evening", description="", source=src2)

    removed1 = gsk.merge_scenes([s1])
    assert removed1 == 0
    assert len(gsk.scenes) == 1

    removed2 = gsk.merge_scenes([s2, s3])
    assert removed2 == 1  # s2 is duplicate of s1, s3 is new
    assert len(gsk.scenes) == 2

    print("  PASS: merge_scenes_deduplication")


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
