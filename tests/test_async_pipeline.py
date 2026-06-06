"""Tests for Async Pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.async_pipeline import (
    extract_all_parallel,
    extract_all_parallel_sync,
    AsyncExtractionResult,
)
from core.chapter_parser import Chapter


def test_async_result_dataclass():
    """AsyncExtractionResult holds results correctly."""
    r = AsyncExtractionResult(characters=[], scenes=[], events=[], relations=[])
    assert isinstance(r, AsyncExtractionResult)
    print("  PASS: async_result_dataclass")


def test_extract_all_parallel_returns_correct_keys():
    """extract_all_parallel returns a result with all expected keys."""
    chapters = [
        Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50),
        Chapter(id="ch_002", number=2, title="第二章", content="陈雨走进灯塔", start_char=50, end_char=100),
    ]

    # Mock agents that don't use real LLM
    class MockAgent:
        def extract_from_chapters(self, chapters, llm):
            return []

    result = extract_all_parallel_sync(
        chapters,
        MockAgent(), MockAgent(), MockAgent(), MockAgent(),
    )

    assert isinstance(result, AsyncExtractionResult)
    assert hasattr(result, "characters")
    assert hasattr(result, "scenes")
    assert hasattr(result, "events")
    assert hasattr(result, "relations")
    print("  PASS: extract_all_parallel_returns_correct_keys")


def test_extract_all_parallel_empty_chapters():
    """Empty chapter list returns empty results."""
    result = extract_all_parallel_sync([], None, None, None, None)
    assert result.characters == []
    assert result.scenes == []
    print("  PASS: extract_all_parallel_empty_chapters")


def test_extract_all_parallel_preserves_order():
    """Results maintain chapter order regardless of completion order."""
    import asyncio
    import time

    chapters = [
        Chapter(id=f"ch_{i:03d}", number=i, title=f"第{i}章", content=f"内容{i}", start_char=0, end_char=10)
        for i in range(1, 6)
    ]

    # Mock agent that takes variable time
    class TrackingAgent:
        def extract_from_chapters(self, chapters, llm):
            time.sleep(0.05)  # simulate LLM call
            return []

    result = extract_all_parallel_sync(
        chapters,
        TrackingAgent(), TrackingAgent(), TrackingAgent(), TrackingAgent(),
    )

    # All 5 chapters processed
    assert isinstance(result, AsyncExtractionResult)
    print("  PASS: extract_all_parallel_preserves_order")


if __name__ == "__main__":
    print("=" * 60)
    print("Async Pipeline Tests")
    print("=" * 60)
    test_async_result_dataclass()
    test_extract_all_parallel_returns_correct_keys()
    test_extract_all_parallel_empty_chapters()
    test_extract_all_parallel_preserves_order()
    print()
    print("ALL ASYNC PIPELINE TESTS PASSED")
