"""Unit tests for Chapter Parser."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.chapter_parser import parse_chapters, get_chapter_by_id


SAMPLE_NOVEL = """《雾港档案》

第一章：失踪的航海日志

秋雨已经连续下了三天。海风裹挟着咸湿的雾气穿过雾港镇的街道。

下午四点，一位陌生老人推开图书馆大门。

老人穿着深灰色风衣。

“不要寻找灯塔下面的秘密。”纸条上写着。

第二章：废弃灯塔

第二天下午。林川将纸条的事情告诉了好友陈雨。

两人决定前往海边废弃灯塔。

地下室的尽头隐藏着一扇铁门。

第三章：迷雾岛

10月17日午夜。按照日志中的记录，林川和陈雨租下一艘渔船，前往地图标记的位置。

海面浓雾弥漫。
"""


def test_parse_three_chapters():
    chapters = parse_chapters(SAMPLE_NOVEL)
    assert len(chapters) == 3, f"Expected 3 chapters, got {len(chapters)}"
    assert chapters[0].id == "ch_001"
    assert chapters[1].id == "ch_002"
    assert chapters[2].id == "ch_003"
    print("  PASS: parse_three_chapters")


def test_chapter_titles():
    chapters = parse_chapters(SAMPLE_NOVEL)
    assert "失踪的航海日志" in chapters[0].title
    assert "废弃灯塔" in chapters[1].title
    assert "迷雾岛" in chapters[2].title
    print("  PASS: chapter_titles")


def test_chapter_content_not_empty():
    chapters = parse_chapters(SAMPLE_NOVEL)
    for ch in chapters:
        assert len(ch.content) > 0, f"Chapter {ch.id} has empty content"
        assert ch.start_char < ch.end_char, f"Chapter {ch.id} has invalid range"
    print("  PASS: chapter_content_not_empty")


def test_chapters_sequential():
    chapters = parse_chapters(SAMPLE_NOVEL)
    for i in range(len(chapters) - 1):
        assert chapters[i].end_char <= chapters[i + 1].start_char, \
            f"Chapter {i} and {i+1} ranges overlap"
    print("  PASS: chapters_sequential")


def test_get_chapter_by_id():
    chapters = parse_chapters(SAMPLE_NOVEL)
    ch = get_chapter_by_id(chapters, "ch_002")
    assert ch is not None
    assert ch.title == chapters[1].title
    ch_missing = get_chapter_by_id(chapters, "ch_999")
    assert ch_missing is None
    print("  PASS: get_chapter_by_id")


def test_no_chapters_fallback():
    text = "这是一段没有章节标题的小说文本。"
    chapters = parse_chapters(text)
    assert len(chapters) == 1
    assert chapters[0].id == "ch_001"
    assert chapters[0].title == "全文"
    print("  PASS: no_chapters_fallback")


def test_real_novel_text():
    novel_path = Path(__file__).parent.parent / "text.md"
    text = novel_path.read_text(encoding="utf-8")
    chapters = parse_chapters(text)
    assert len(chapters) == 3
    assert chapters[0].id == "ch_001"
    print("  PASS: real_novel_text")


if __name__ == "__main__":
    print("=" * 60)
    print("Chapter Parser Tests")
    print("=" * 60)
    test_parse_three_chapters()
    test_chapter_titles()
    test_chapter_content_not_empty()
    test_chapters_sequential()
    test_get_chapter_by_id()
    test_no_chapters_fallback()
    test_real_novel_text()
    print()
    print("ALL CHAPTER PARSER TESTS PASSED")
