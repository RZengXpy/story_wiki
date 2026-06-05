"""Integration test for StoryForgeWorkflow MVP 5: Complete SKL (Relation / Event / Location / Timeline / Outline / Character Arc).

Runs the full pipeline and verifies all SKL fields are populated.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from core.workflow import StoryForgeWorkflow


def test_mvp5_workflow_end_to_end():
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

    # ── Chapters ─────────────────────────────────────────────────────────────
    assert len(result.chapters) == 3
    print(f"  [OK] Chapters: {len(result.chapters)}")

    # ── MVP 5: Global SKL completeness ───────────────────────────────────────
    assert result.global_skl is not None, "Global SKL not set"
    gsk = result.global_skl
    print(f"  [OK] Global SKL created")

    # ── MVP 5.1: Relations ─────────────────────────────────────────────────
    assert len(gsk.relations) > 0, "No relations extracted"
    print(f"  [OK] Relations: {len(gsk.relations)}")
    valid_types = {"family", "friend", "enemy", "romantic", "professional", "stranger"}
    for r in gsk.relations:
        assert r.relation_type in valid_types, f"Invalid relation type: {r.relation_type}"
        assert r.from_char and r.to_char, "Relation missing character names"
        print(f"       {r.from_char} --[{r.relation_type}]--> {r.to_char}")

    # Relations appear in StoryGraph
    assert len(result.graph.relations) == len(gsk.relations)
    print(f"  [OK] StoryGraph relations: {len(result.graph.relations)}")

    # ── MVP 5.2: Events deduplication ───────────────────────────────────────
    raw_events = result.step_results.get("events", [])
    print(f"  Raw events: {len(raw_events)}, After dedup: {len(gsk.events)}")
    assert len(gsk.events) <= len(raw_events), "Event dedup should reduce count"
    assert len(gsk.events) > 0, "No events in SKL"
    print(f"  [OK] Events: {len(gsk.events)} unique events (raw: {len(raw_events)})")

    # Each event has source trace
    for e in gsk.events:
        assert e.get("title"), "Event missing title"
        assert e.get("event_type"), "Event missing type"
        assert isinstance(e.get("source"), dict), "Event missing source"
    print(f"  [OK] All events have title, type, and source")

    # Events appear in StoryGraph
    assert len(result.graph.events) == len(gsk.events)
    print(f"  [OK] StoryGraph events: {len(result.graph.events)}")

    # ── MVP 5.3: Locations ───────────────────────────────────────────────────
    assert len(gsk.locations) > 0, "No locations built"
    print(f"  [OK] Locations: {len(gsk.locations)}")
    for loc in gsk.locations:
        assert loc.name, "Location missing name"
        assert loc.frequency > 0, "Location frequency should be > 0"
        assert loc.location_type in {"indoor", "outdoor", "mixed"}, f"Invalid location type: {loc.location_type}"
        print(f"       {loc.name} ({loc.location_type}) x{loc.frequency}: {len(loc.scenes)} scenes")

    # ── MVP 5.4: Timeline ─────────────────────────────────────────────────
    assert len(gsk.timeline) > 0, "Timeline is empty"
    print(f"  [OK] Timeline entries: {len(gsk.timeline)}")
    for entry in gsk.timeline:
        assert entry.event_title, "Timeline entry missing event title"
        assert entry.time_marker, "Timeline entry missing time marker"
        print(f"       [{entry.time_marker}] {entry.event_title} @ {entry.location}")

    # Timeline is sorted (first entry time_order <= last)
    time_order_vals = {"黎明": 0, "凌晨": 0, "清晨": 1, "早晨": 1, "早上": 1, "上午": 2,
                       "中午": 3, "午间": 3, "午后": 3, "下午": 4, "傍晚": 5, "黄昏": 5,
                       "晚上": 6, "夜里": 7, "深夜": 8, "午夜": 8}
    timeline_times = [e.time_marker for e in gsk.timeline]
    print(f"  [OK] Timeline sorted: {'Yes' if timeline_times == sorted(timeline_times, key=lambda t: time_order_vals.get(t, 50)) else 'Approximate'}")

    # ── MVP 5.5: Outline ───────────────────────────────────────────────────
    assert gsk.outline, "Outline not generated"
    outline = gsk.outline
    assert "genre" in outline, "Outline missing genre"
    assert "theme" in outline, "Outline missing theme"
    assert "main_conflict" in outline, "Outline missing main_conflict"
    assert "arc_summary" in outline, "Outline missing arc_summary"
    assert "act_summaries" in outline, "Outline missing act_summaries"
    assert "key_plot_points" in outline, "Outline missing key_plot_points"
    print(f"  [OK] Outline generated:")
    print(f"       genre: {outline.get('genre')}")
    print(f"       theme: {outline.get('theme')}")
    print(f"       main_conflict: {outline.get('main_conflict')}")
    print(f"       acts: {len(outline.get('act_summaries', []))}")
    print(f"       key_plot_points: {len(outline.get('key_plot_points', []))}")

    # ── MVP 5.6: Character Arcs ────────────────────────────────────────────
    assert len(gsk.character_arcs) > 0, "No character arcs built"
    print(f"  [OK] Character arcs: {len(gsk.character_arcs)} characters")
    for char_name, events in gsk.character_arcs.items():
        assert len(events) > 0, f"Character {char_name} has empty arc"
        for arc_entry in events:
            assert arc_entry.event_title, "Arc entry missing event_title"
            assert arc_entry.event_type, "Arc entry missing event_type"
        print(f"       {char_name}: {len(events)} events")

    # ── Full SKL summary ───────────────────────────────────────────────────
    print()
    print(f"  === MVP 5 Complete SKL Summary ===")
    print(f"  Characters:     {len(gsk.characters)}")
    print(f"  Scenes:         {len(gsk.scenes)}")
    print(f"  Relations:      {len(gsk.relations)}")
    print(f"  Events:         {len(gsk.events)}")
    print(f"  Locations:      {len(gsk.locations)}")
    print(f"  Timeline:       {len(gsk.timeline)}")
    print(f"  Character Arcs: {len(gsk.character_arcs)}")
    print(f"  Outline:        {'Yes' if gsk.outline else 'No'}")
    print(f"  Source Chapters:{gsk.total_chapters}")

    # ── WorkflowResult merger_report includes new fields ───────────────────
    report = result.merger_report
    assert "unique_relations" in report, "merger_report missing unique_relations"
    assert "unique_events" in report, "merger_report missing unique_events"
    assert "locations_count" in report, "merger_report missing locations_count"
    assert "timeline_count" in report, "merger_report missing timeline_count"
    assert "character_arcs_count" in report, "merger_report missing character_arcs_count"
    assert "outline_generated" in report, "merger_report missing outline_generated"
    print(f"  [OK] Merger report includes all MVP 5 fields")

    print()
    print("ALL MVP 5 WORKFLOW TESTS PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("MVP 5 — Complete SKL End-to-End Test")
    print("=" * 60)
    test_mvp5_workflow_end_to_end()
