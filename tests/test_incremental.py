"""Tests for Incremental Update Module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.incremental import ChapterCache, _hash_content, ChapterHash
from core.chapter_parser import Chapter


def test_hash_content_deterministic():
    """Same content always produces same hash."""
    h1 = _hash_content("林远走进图书馆，遇见了陈雨")
    h2 = _hash_content("林远走进图书馆，遇见了陈雨")
    assert h1 == h2
    print("  PASS: hash_content_deterministic")


def test_hash_content_differs():
    """Different content produces different hash."""
    h1 = _hash_content("林远走进图书馆")
    h2 = _hash_content("陈雨走进灯塔")
    assert h1 != h2
    print("  PASS: hash_content_differs")


def test_hash_content_truncated_efficiency():
    """Hash uses only head+tail, not full content."""
    # A very long string — hash should be fast (512+512 chars max)
    long_str = "林" * 10000
    h = _hash_content(long_str)
    assert len(h) == 16  # truncated SHA-256
    print("  PASS: hash_content_truncated_efficiency")


def test_chapter_cache_update_and_retrieve():
    """Cache stores and retrieves per-chapter results."""
    cache = ChapterCache()

    ch = Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50)
    chars = [{"name": "林远", "role": "protagonist"}]
    scenes = [{"title": "图书馆", "location": "雾港镇"}]
    events = [{"title": "相遇", "event_type": "revelation"}]
    rels = [{"from_char": "林远", "to_char": "陈雨", "relation_type": "friend"}]

    cache.update(ch, chars, scenes, events, rels)

    assert cache.has_cached("ch_001")
    assert cache.content_hash("ch_001") is not None
    assert cache.characters["ch_001"] == chars
    assert cache.scenes["ch_001"] == scenes
    print("  PASS: cache_update_and_retrieve")


def test_chapter_cache_changed_detection():
    """get_changed_chapters returns chapters with different content or not in cache."""
    cache = ChapterCache()

    ch1 = Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50)
    ch2 = Chapter(id="ch_002", number=2, title="第二章", content="陈雨走进灯塔", start_char=50, end_char=100)

    cache.update(ch1, [], [], [], [])
    # ch1 unchanged, ch2 not in cache
    changed = cache.get_changed_chapters([ch1, ch2])
    assert len(changed) == 1
    assert getattr(changed[0], "id", "") == "ch_002"

    # ch1 content changed
    ch1_modified = Chapter(id="ch_001", number=1, title="第一章", content="林远走进了地下室", start_char=0, end_char=60)
    changed2 = cache.get_changed_chapters([ch1_modified, ch2])
    # Both changed: ch1 content changed, ch2 not in cache
    assert len(changed2) == 2
    ids2 = {getattr(c, "id", "") for c in changed2}
    assert "ch_001" in ids2
    assert "ch_002" in ids2
    print("  PASS: cache_changed_detection")


def test_chapter_cache_invalidate():
    """invalidate() removes a chapter from cache."""
    cache = ChapterCache()
    ch = Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50)
    cache.update(ch, [], [], [], [])
    assert cache.has_cached("ch_001")

    cache.invalidate("ch_001")
    assert not cache.has_cached("ch_001")
    assert cache.content_hash("ch_001") is None
    print("  PASS: cache_invalidate")


def test_chapter_cache_clear():
    """clear() removes all cached data."""
    cache = ChapterCache()
    ch1 = Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50)
    ch2 = Chapter(id="ch_002", number=2, title="第二章", content="陈雨走进灯塔", start_char=50, end_char=100)
    cache.update(ch1, [], [], [], [])
    cache.update(ch2, [], [], [], [])

    cache.clear()
    assert not cache.has_cached("ch_001")
    assert not cache.has_cached("ch_002")
    assert len(cache.chapter_hashes) == 0
    print("  PASS: cache_clear")


def test_chapter_cache_summary():
    """summary() returns a readable dict."""
    cache = ChapterCache()
    ch = Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50)
    cache.update(ch, [], [], [], [])

    summary = cache.summary()
    assert summary["cached_chapters"] == 1
    assert summary["version"] == "1"
    assert len(summary["chapter_hashes"]) == 1
    print("  PASS: cache_summary")


def test_fully_cached_returns_early():
    """When all chapters are cached, no LLM calls needed."""
    cache = ChapterCache()
    ch1 = Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50)
    ch2 = Chapter(id="ch_002", number=2, title="第二章", content="陈雨走进灯塔", start_char=50, end_char=100)
    cache.update(ch1, [], [], [], [])
    cache.update(ch2, [], [], [], [])

    changed = cache.get_changed_chapters([ch1, ch2])
    assert len(changed) == 0
    print("  PASS: fully_cached_returns_early")


if __name__ == "__main__":
    print("=" * 60)
    print("Incremental Update Tests")
    print("=" * 60)
    test_hash_content_deterministic()
    test_hash_content_differs()
    test_hash_content_truncated_efficiency()
    test_chapter_cache_update_and_retrieve()
    test_chapter_cache_changed_detection()
    test_chapter_cache_invalidate()
    test_chapter_cache_clear()
    test_chapter_cache_summary()
    test_fully_cached_returns_early()
    print()
    print("ALL INCREMENTAL TESTS PASSED")
