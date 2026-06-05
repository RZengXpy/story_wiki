"""Integration test for StoryForgeWorkflow (MVP 3 chapter-based processing).

Single end-to-end test — runs full pipeline once, checks all MVP 3 guarantees.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from core.workflow import StoryForgeWorkflow
from core.chapter_parser import parse_chapters


def test_mvp3_workflow_end_to_end():
    """MVP 3: Chapter-based processing with source trace."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("SKIP: OPENAI_API_KEY not set")
        return

    novel_path = Path(__file__).parent.parent / "text.md"
    novel_text = novel_path.read_text(encoding="utf-8")

    workflow = StoryForgeWorkflow(
        model="deepseek-v4-flash",
        api_key=api_key,
        run_consistency_check=True,
    )

    # Single full pipeline run
    result = workflow.run(novel_text, title="雾港档案", author="StoryForge")

    # --- Assertions ---
    assert result.success, f"Workflow failed: {result.error_message}"
    assert result.graph is not None

    # 1. Chapter parsing
    assert len(result.chapters) == 3, f"Expected 3 chapters, got {len(result.chapters)}"
    print(f"  [OK] Chapters: {len(result.chapters)}")
    for ch in result.chapters:
        print(f"       {ch.id}: {ch.title} ({len(ch.content)} chars)")

    # 2. Character extraction with source trace
    assert len(result.graph.characters) > 0, "No characters extracted"
    print(f"  [OK] Characters: {len(result.graph.characters)}")
    for c in result.graph.characters:
        print(f"       - {c.name} ({c.role.value}) | first: {c.first_appearance}")

    # 3. Scene parsing
    assert len(result.graph.scenes) > 0, "No scenes extracted"
    print(f"  [OK] Scenes: {len(result.graph.scenes)}")

    # 4. Event extraction with source trace
    raw_events = result.step_results.get("events", [])
    assert len(raw_events) > 0, "No events extracted"
    print(f"  [OK] Events: {len(raw_events)}")
    for e in raw_events:
        print(f"       - {e.title} ({e.event_type}) | src={e.source}")

    # 5. Every event has a source trace (MVP 3 guarantee)
    for e in raw_events:
        assert e.source.get("chapter_id") is not None, \
            f"Event '{e.title}' missing chapter_id in source"
        assert e.source.get("chapter_title") is not None, \
            f"Event '{e.title}' missing chapter_title in source"
    print(f"  [OK] All {len(raw_events)} events have source trace")

    # 6. Events span multiple chapters
    chapter_ids = {e.source["chapter_id"] for e in raw_events}
    print(f"  [OK] Events span {len(chapter_ids)} chapter(s): {chapter_ids}")

    # 7. Consistency check ran
    print(f"  [OK] Consistency: {len(result.graph.warnings)} warning(s)")
    for w in result.graph.warnings:
        print(f"       [{w.code.value}] {w.message}")

    # 8. Result summary
    print(f"  [OK] Summary: {result.summary()}")

    print()
    print("ALL MVP 3 WORKFLOW TESTS PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("MVP 3 — StoryForgeWorkflow End-to-End Test")
    print("=" * 60)
    test_mvp3_workflow_end_to_end()
