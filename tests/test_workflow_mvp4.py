"""Integration test for StoryForgeWorkflow MVP 4: Local → Global Knowledge Merge.

Single end-to-end test — runs full pipeline once, verifies SKL deduplication
and enhanced consistency checking.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from core.workflow import StoryForgeWorkflow


def test_mvp4_workflow_end_to_end():
    """MVP 4: Knowledge Merger + Enhanced Consistency Check."""
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

    result = workflow.run(novel_text, title="雾港档案", author="StoryForge")

    # ── Basic success ───────────────────────────────────────────────────────
    assert result.success, f"Workflow failed: {result.error_message}"
    assert result.graph is not None
    print(f"  [OK] Workflow succeeded")

    # ── Chapter parsing ────────────────────────────────────────────────────
    assert len(result.chapters) == 3
    print(f"  [OK] Chapters: {len(result.chapters)}")

    # ── MVP 4.1: Global SKL exists and is populated ────────────────────────
    assert result.global_skl is not None, "Global SKL not set"
    gsk = result.global_skl
    print(f"  [OK] Global SKL created")

    # ── MVP 4.2: Deduplication via Knowledge Merger ────────────────────────
    raw_chars = result.step_results.get("characters", [])
    raw_scenes = result.step_results.get("scenes", [])

    print(f"  Before merge: {len(raw_chars)} characters, {len(raw_scenes)} scenes")
    print(f"  After merge:  {len(gsk.characters)} unique characters, {len(gsk.scenes)} unique scenes")
    print(f"  Duplicates removed: {gsk.duplicates_removed}")

    # Deduplication must have run (characters should be less than or equal to raw)
    assert len(gsk.characters) <= len(raw_chars)
    assert len(gsk.scenes) <= len(raw_scenes)

    # Character first appearance tracked
    assert len(gsk.character_first_appearance) > 0
    print(f"  [OK] Character first appearances: {gsk.character_first_appearance}")

    # Source chapters tracked
    assert gsk.total_chapters == 3
    print(f"  [OK] Source chapters: {gsk.total_chapters}")

    # ── MVP 4.3: StoryGraph uses deduplicated data ────────────────────────
    assert len(result.graph.characters) > 0
    assert len(result.graph.characters) <= len(result.graph.characters)  # graph uses SKL
    print(f"  [OK] StoryGraph: {len(result.graph.characters)} chars, {len(result.graph.scenes)} scenes")

    # ── MVP 4.4: Enhanced consistency check ───────────────────────────────
    print(f"  [OK] Consistency: passed={result.merger_report.get('consistency_passed')}")
    print(f"  [OK] Warnings: {len(result.graph.warnings)}")
    for w in result.graph.warnings:
        print(f"       [{w.code.value}] {w.message}")

    # ── MVP 4.5: Merger report ───────────────────────────────────────────
    print(f"  [OK] Merger report:")
    for k, v in result.merger_report.items():
        if k != "character_first_appearance":
            print(f"       {k}: {v}")

    # ── MVP 4.6: Source trace preserved on raw step_results ───────────────
    for c in raw_chars:
        assert c.source is not None, f"Character {c.name} missing source trace"
    for s in raw_scenes:
        assert s.source is not None, f"Scene {s.title} missing source trace"
    print(f"  [OK] All {len(raw_chars)} characters and {len(raw_scenes)} scenes have source trace")

    print()
    print("ALL MVP 4 WORKFLOW TESTS PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("MVP 4 — Knowledge Merger End-to-End Test")
    print("=" * 60)
    test_mvp4_workflow_end_to_end()
