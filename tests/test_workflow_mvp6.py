"""Integration test for StoryForgeWorkflow MVP 6: SKL → Screenplay.

Verifies that run_with_scripts() produces a StoryGraph with screenplay content
in the scripts field, and that to_yaml() includes scripts output.

Also tests the Director Agent → Screenplay Bible pipeline.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from core.workflow import StoryForgeWorkflow


def test_mvp6_workflow_with_scripts():
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

    # ── MVP 6: run_with_scripts ────────────────────────────────────────────
    result = workflow.run_with_scripts(novel_text, title="雾港档案", author="StoryForge")

    assert result.success, f"Workflow failed: {result.error_message}"
    assert result.graph is not None
    print(f"  [OK] run_with_scripts succeeded")

    # ── MVP 6.0: Screenplay Bible generated ─────────────────────────────────
    assert result.screenplay_bible, "No screenplay bible generated"
    bible = result.screenplay_bible
    assert bible.get("genre"), "Bible missing genre"
    assert bible.get("tone"), "Bible missing tone"
    print(f"  [OK] Screenplay Bible: genre={bible.get('genre')}, tone={bible.get('tone')}")
    print(f"       Themes: {bible.get('themes', [])[:2]}")
    print(f"       Characters: {len(bible.get('character_portraits', []))}")

    # ── MVP 6.1: Global Outline from Rule Engine ────────────────────────────
    gsk = result.global_skl
    assert gsk.outline, "No global outline built"
    assert gsk.outline.get("genre"), "Global outline missing genre"
    assert gsk.outline.get("main_conflict"), "Global outline missing main_conflict"
    print(f"  [OK] Global Outline: genre={gsk.outline.get('genre')}")
    print(f"       Chapters summarized: {len(gsk.chapter_summaries)}")
    print(f"       Act summaries: {len(gsk.outline.get('act_summaries', []))}")

    # ── MVP 6.2: SKL is populated ─────────────────────────────────────────
    assert result.global_skl is not None
    print(f"  [OK] SKL: {len(gsk.characters)} chars, {len(gsk.scenes)} scenes")

    # ── MVP 6.3: Scripts generated ─────────────────────────────────────────
    assert result.graph.scripts, "No scripts generated"
    scripts_count = len(result.graph.scripts)
    print(f"  [OK] Scripts: {scripts_count} scene scripts generated")
    assert scripts_count > 0, "At least one scene script should be generated"

    # Each non-empty script has valid content
    total_items = 0
    for scene_id, script_node in result.graph.scripts.items():
        assert scene_id, f"Script node missing id"
        assert script_node.content is not None, f"Script {scene_id} missing content"
        if len(script_node.content) == 0:
            print(f"       {scene_id}: (empty — generation failed)")
            continue
        for item in script_node.content:
            assert item.type in ("action", "dialogue"), f"Invalid script item type: {item.type}"
            assert item.text, "Script item missing text"
            if item.type == "dialogue":
                assert item.character, "Dialogue item missing character"
        total_items += len(script_node.content)
        print(f"       {scene_id}: {len(script_node.content)} items")

    print(f"  [OK] Total screenplay items: {total_items}")

    # ── MVP 6.4: Merger report includes script stats ──────────────────────
    report = result.merger_report
    assert "scripts_generated" in report, "merger_report missing scripts_generated"
    assert "screenplay_items" in report, "merger_report missing screenplay_items"
    assert report["scripts_generated"] >= 1, f"Expected at least 1 non-empty script, got {report['scripts_generated']}"
    assert report["scripts_generated"] <= scripts_count, f"scripts_generated ({report['scripts_generated']}) > total scenes ({scripts_count})"
    failed = report.get("scripts_failed", 0)
    print(f"  [OK] Merger report: {report['scripts_generated']} succeeded, {failed} failed, {report['screenplay_items']} items")

    # ── MVP 6.5: to_yaml includes scripts ─────────────────────────────────
    yaml_output = result.graph.to_yaml()
    assert "scripts:" in yaml_output or "scripts" in yaml_output, "to_yaml() missing scripts section"
    print(f"  [OK] to_yaml() includes scripts (length: {len(yaml_output)} chars)")

    # ── MVP 6.6: summary() includes script count ──────────────────────────
    summary = result.summary()
    assert "剧本场景=" in summary, "summary() missing script count"
    print(f"  [OK] summary(): {summary}")

    print()
    print("ALL MVP 6 WORKFLOW TESTS PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("MVP 6 — SKL to Screenplay End-to-End Test")
    print("=" * 60)
    test_mvp6_workflow_with_scripts()
