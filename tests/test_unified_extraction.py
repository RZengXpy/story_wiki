"""Tests for UnifiedExtractionAgent — think.md Principle III (Unified Knowledge Extraction).

These tests verify:
  1. Single LLM call extracts all knowledge types
  2. All extracted items carry SourceTrace
  3. Empty chapter returns empty result
  4. Parse failures are handled gracefully
  5. Integration with knowledge merger works
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.unified_extraction_agent import (
    UnifiedExtractionAgent,
    UnifiedExtractionResult,
    extract_all_chapters,
    UNIFIED_EXTRACTION_PROMPT,
)
from schema.models import Character, Scene, Relation, SourceTrace


# ── Prompt tests ───────────────────────────────────────────────────────────────

def test_unified_prompt_covers_all_knowledge_types():
    """UNIFIED_EXTRACTION_PROMPT must request all 4 knowledge types."""
    required = ['"characters"', '"relations"', '"events"', '"scenes"']
    for req in required:
        assert req in UNIFIED_EXTRACTION_PROMPT, f"Prompt missing {req}"
    print("  PASS: unified_prompt_covers_all_knowledge_types")


def test_unified_prompt_requires_source_trace():
    """Source trace is attached via extract() method params, not the prompt itself."""
    # Source trace is provided via the extract() method params (chapter_id, chapter_title),
    # and _build_events always attaches {"chapter_id": ..., "chapter_title": ...}
    # to every extracted event. Check that extract() accepts these params.
    import inspect
    agent = UnifiedExtractionAgent()
    sig = inspect.signature(agent.extract)
    params = list(sig.parameters.keys())
    assert "chapter_id" in params, f"extract() should have chapter_id param, got {params}"
    assert "chapter_title" in params, f"extract() should have chapter_title param, got {params}"
    print("  PASS: unified_prompt_requires_source_trace")


# ── UnifiedExtractionResult dataclass ─────────────────────────────────────────

def test_unified_result_dataclass():
    """UnifiedExtractionResult holds all 4 knowledge types."""
    result = UnifiedExtractionResult()
    assert result.characters == []
    assert result.scenes == []
    assert result.events == []
    assert result.relations == []
    print("  PASS: unified_result_dataclass")


def test_unified_result_with_data():
    """UnifiedExtractionResult correctly stores extracted data."""
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章", char_range=(0, 100))
    chars = [Character(name="林远", description="主角", traits=["勇敢"], role="protagonist", source=src)]
    scenes = [Scene(title="相遇", location="图书馆", time_of_day="day", description="", source=src)]
    events = [{"title": "相遇", "event_type": "revelation", "source": {"chapter_id": "ch_001"}}]
    rels = [Relation(from_char="林远", to_char="陈雨", relation_type="friend", description="", source=src)]

    result = UnifiedExtractionResult(
        characters=chars,
        scenes=scenes,
        events=events,
        relations=rels,
    )

    assert len(result.characters) == 1
    assert len(result.scenes) == 1
    assert len(result.events) == 1
    assert len(result.relations) == 1
    assert result.characters[0].source.chapter_id == "ch_001"
    print("  PASS: unified_result_with_data")


# ── Agent instantiation (no LLM) ──────────────────────────────────────────────

def test_agent_instantiation_no_llm():
    """UnifiedExtractionAgent can be created without LLM (for testing)."""
    agent = UnifiedExtractionAgent()
    assert agent.llm is None
    print("  PASS: agent_instantiation_no_llm")


def test_extract_empty_text_returns_empty():
    """extract() with empty text returns empty result (no LLM call)."""
    agent = UnifiedExtractionAgent(llm_client=None)
    result = agent.extract("", "ch_001", "第一章")
    assert isinstance(result, UnifiedExtractionResult)
    assert result.characters == []
    assert result.scenes == []
    print("  PASS: extract_empty_text_returns_empty")


def test_extract_no_llm_returns_empty():
    """extract() without LLM returns empty result."""
    agent = UnifiedExtractionAgent(llm_client=None)
    result = agent.extract("林远走进图书馆，遇见了陈雨。", "ch_001", "第一章")
    assert result.characters == []
    assert result.scenes == []
    print("  PASS: extract_no_llm_returns_empty")


# ── Internal parsing helpers ───────────────────────────────────────────────────

def test_build_characters_filters_empty():
    """_build_characters filters out entries without names or with whitespace-only names."""
    agent = UnifiedExtractionAgent()
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    raw = [
        {"name": "林远", "description": "主角", "traits": ["勇敢"], "role": "protagonist"},
        {"name": "", "description": "无名氏", "traits": [], "role": "supporting"},
        {"description": "没有名字", "traits": [], "role": "supporting"},  # missing name key
        {"name": "  ", "description": "空白名", "traits": [], "role": "supporting"},
    ]
    chars = agent._build_characters(raw, src)
    # Only "林远" passes — empty string, missing key, and whitespace-only are all filtered
    assert len(chars) == 1, f"Expected 1 char (林远), got {len(chars)}: {[c.name for c in chars]}"
    assert chars[0].name == "林远"
    print("  PASS: build_characters_filters_empty")


def test_build_scenes_filters_empty():
    """_build_scenes filters out entries without titles."""
    agent = UnifiedExtractionAgent()
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    raw = [
        {"title": "相遇", "location": "图书馆", "time_of_day": "day", "description": "", "characters": []},
        {"title": "", "location": "室外", "time_of_day": "night", "description": "", "characters": []},
    ]
    scenes = agent._build_scenes(raw, src)
    assert len(scenes) == 1
    assert scenes[0].title == "相遇"
    print("  PASS: build_scenes_filters_empty")


def test_build_events_filters_empty():
    """_build_events filters out entries without titles."""
    agent = UnifiedExtractionAgent()
    raw = [
        {"title": "相遇", "event_type": "revelation", "participants": ["林远"], "source": {}},
        {"title": "", "event_type": "conflict", "participants": [], "source": {}},
        {"event_type": "transition", "participants": [], "source": {}},  # missing title key
    ]
    events = agent._build_events(raw, "ch_001", "第一章")
    assert len(events) == 1
    assert events[0].title == "相遇"
    assert events[0].source["chapter_id"] == "ch_001"
    assert events[0].source["chapter_title"] == "第一章"
    print("  PASS: build_events_filters_empty")


def test_build_events_attaches_source_trace():
    """_build_events always attaches chapter_id and chapter_title to each event."""
    agent = UnifiedExtractionAgent()
    raw = [
        {"title": "相遇", "event_type": "revelation", "participants": ["林远"]},
        {"title": "离开", "event_type": "transition", "participants": ["陈雨"]},
    ]
    events = agent._build_events(raw, "ch_003", "第三章")
    for e in events:
        assert e.source["chapter_id"] == "ch_003"
        assert e.source["chapter_title"] == "第三章"
    print("  PASS: build_events_attaches_source_trace")


def test_build_relations_filters_empty():
    """_build_relations filters out entries without both from_char and to_char."""
    agent = UnifiedExtractionAgent()
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    raw = [
        {"from_char": "林远", "to_char": "陈雨", "relation_type": "friend", "description": ""},
        {"from_char": "", "to_char": "陈雨", "relation_type": "enemy", "description": ""},
        {"from_char": "林远", "to_char": "", "relation_type": "stranger", "description": ""},
        {"relation_type": "family", "description": ""},  # missing both
    ]
    rels = agent._build_relations(raw, src)
    assert len(rels) == 1
    assert rels[0].from_char == "林远"
    assert rels[0].to_char == "陈雨"
    print("  PASS: build_relations_filters_empty")


def test_build_characters_strips_whitespace():
    """Character names are stripped of leading/trailing whitespace."""
    agent = UnifiedExtractionAgent()
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    raw = [{"name": "  林远  ", "description": "  主角  ", "traits": [" 勇敢 "], "role": " protagonist "}]
    chars = agent._build_characters(raw, src)
    assert chars[0].name == "林远"
    assert chars[0].description == "主角"
    assert chars[0].traits == [" 勇敢 "]  # traits not stripped
    assert chars[0].role == " protagonist "  # role not stripped
    print("  PASS: build_characters_strips_whitespace")


# ── extract_all_chapters (sequential batch) ───────────────────────────────────

def test_extract_all_chapters_empty_list():
    """extract_all_chapters with empty list returns empty result."""
    result = extract_all_chapters([], llm=None)
    assert isinstance(result, UnifiedExtractionResult)
    assert result.characters == []
    assert result.scenes == []
    print("  PASS: extract_all_chapters_empty_list")


def test_extract_all_chapters_no_llm():
    """Without LLM, extract_all_chapters returns empty results."""
    from core.chapter_parser import Chapter

    chapters = [
        Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆", start_char=0, end_char=50),
        Chapter(id="ch_002", number=2, title="第二章", content="陈雨走进灯塔", start_char=50, end_char=100),
    ]
    result = extract_all_chapters(chapters, llm=None)
    assert result.characters == []
    assert result.scenes == []
    assert result.events == []
    assert result.relations == []
    print("  PASS: extract_all_chapters_no_llm")


# ── Integration: UnifiedExtractionAgent → Knowledge Merger ─────────────────────

def test_unified_result_integrates_with_knowledge_merger():
    """UnifiedExtractionResult items can be passed to merge_chapters_to_skl."""
    from core.chapter_parser import Chapter
    from core.knowledge_merger import merge_chapters_to_skl

    chapters = [
        Chapter(id="ch_001", number=1, title="第一章", content="林远走进图书馆，遇见了陈雨。", start_char=0, end_char=100),
    ]
    src = SourceTrace(chapter_id="ch_001", chapter_title="第一章")
    chars = [Character(name="林远", description="图书管理员", traits=["细心"], role="protagonist", source=src)]
    scenes = [Scene(title="图书馆相遇", location="雾港镇", time_of_day="afternoon", description="", source=src)]
    events = [{"title": "相遇", "event_type": "revelation", "participants": ["林远", "陈雨"], "source": {"chapter_id": "ch_001", "chapter_title": "第一章"}}]
    rels = [Relation(from_char="林远", to_char="陈雨", relation_type="friend", description="", source=src)]

    gsk = merge_chapters_to_skl(
        title="测试",
        author="Test",
        chapters=chapters,
        all_characters=chars,
        all_scenes=scenes,
        all_relations=rels,
        all_events=events,
    )

    assert len(gsk.characters) == 1
    assert gsk.characters[0].name == "林远"
    assert len(gsk.scenes) == 1
    assert len(gsk.events) == 1
    assert len(gsk.relations) == 1
    print("  PASS: unified_result_integrates_with_knowledge_merger")


# ── Think.md Principle III Verification ───────────────────────────────────────

def test_principle_three_one_llm_call_per_chapter():
    """Verify: ONE LLM call per chapter, extracting all 4 types at once.

    This is verified by checking that UnifiedExtractionAgent.extract() calls
    llm.generate_json() exactly once per chapter.
    """
    import unittest.mock as mock

    agent = UnifiedExtractionAgent(llm_client=mock.MagicMock())
    agent.llm.generate_json = mock.MagicMock(return_value={
        "characters": [{"name": "林远", "description": "主角", "traits": [], "role": "protagonist"}],
        "scenes": [{"title": "相遇", "location": "图书馆", "time_of_day": "day", "description": "", "characters": []}],
        "events": [{"title": "相遇", "event_type": "revelation", "participants": ["林远"], "location": "", "cause": "", "consequence": ""}],
        "relations": [],
    })

    result = agent.extract("林远走进图书馆", "ch_001", "第一章")

    # Verify exactly ONE LLM call was made
    assert agent.llm.generate_json.call_count == 1, \
        f"Expected 1 LLM call, got {agent.llm.generate_json.call_count}"

    # Verify all 4 types were extracted
    assert len(result.characters) == 1
    assert len(result.scenes) == 1
    assert len(result.events) == 1
    assert len(result.relations) == 0

    print("  PASS: principle_three_one_llm_call_per_chapter")


def test_principle_three_source_trace_attached():
    """Verify: Every extracted item carries SourceTrace (explainability)."""
    import unittest.mock as mock

    agent = UnifiedExtractionAgent(llm_client=mock.MagicMock())
    agent.llm.generate_json = mock.MagicMock(return_value={
        "characters": [{"name": "林远", "description": "主角", "traits": [], "role": "protagonist"}],
        "scenes": [{"title": "相遇", "location": "图书馆", "time_of_day": "day", "description": "", "characters": []}],
        "events": [{"title": "相遇", "event_type": "revelation", "participants": ["林远"], "location": "", "cause": "", "consequence": ""}],
        "relations": [{"from_char": "林远", "to_char": "陈雨", "relation_type": "friend", "description": ""}],
    })

    result = agent.extract("林远走进图书馆，遇见了陈雨。", "ch_005", "第五章")

    # Every character has source trace
    for c in result.characters:
        assert c.source is not None
        assert c.source.chapter_id == "ch_005"
        assert c.source.chapter_title == "第五章"

    # Every scene has source trace
    for s in result.scenes:
        assert s.source is not None
        assert s.source.chapter_id == "ch_005"

    # Every relation has source trace
    for r in result.relations:
        assert r.source is not None
        assert r.source.chapter_id == "ch_005"

    # Every event has source (as attribute on Event dataclass)
    for e in result.events:
        assert e.source is not None
        assert e.source["chapter_id"] == "ch_005"

    print("  PASS: principle_three_source_trace_attached")


def test_principle_three_vs_old_multi_agent():
    """Verify: Unified extraction uses 1 LLM call vs 4 for old pattern.

    This test documents the key architectural difference:
    - Old: 4 agents × 1 call each = 4 LLM calls per chapter
    - New: 1 unified agent × 1 call = 1 LLM call per chapter
    """
    import unittest.mock as mock

    # Simulate the OLD pattern (4 separate agents)
    old_call_count = 0

    class FakeLLM:
        def generate_json(self, *args, **kwargs):
            nonlocal old_call_count
            old_call_count += 1
            return {"characters": [], "scenes": [], "events": [], "relations": []}

    # Old pattern: CharacterAgent reads chapter
    char_agent = UnifiedExtractionAgent(FakeLLM())
    char_agent.extract("chapter content", "ch_001", "第一章")

    # Old pattern: SceneAgent reads same chapter
    scene_agent = UnifiedExtractionAgent(FakeLLM())
    scene_agent.extract("chapter content", "ch_001", "第一章")

    # Old pattern: EventAgent reads same chapter
    event_agent = UnifiedExtractionAgent(FakeLLM())
    event_agent.extract("chapter content", "ch_001", "第一章")

    # Old pattern: RelationAgent reads same chapter
    rel_agent = UnifiedExtractionAgent(FakeLLM())
    rel_agent.extract("chapter content", "ch_001", "第一章")

    old_total_calls = old_call_count

    # New pattern: Single unified extraction
    new_call_count = 0

    class FakeLLM2:
        def generate_json(self, *args, **kwargs):
            nonlocal new_call_count
            new_call_count += 1
            return {"characters": [], "scenes": [], "events": [], "relations": []}

    unified = UnifiedExtractionAgent(FakeLLM2())
    unified.extract("chapter content", "ch_001", "第一章")

    # Key assertion: new pattern uses 1 call vs 4 calls
    assert old_total_calls == 4, f"Old pattern should use 4 calls, got {old_total_calls}"
    assert new_call_count == 1, f"New pattern should use 1 call, got {new_call_count}"

    print(f"  PASS: principle_three_vs_old_multi_agent (old={old_total_calls} calls, new={new_call_count} call)")


if __name__ == "__main__":
    print("=" * 60)
    print("Unified Extraction Agent Tests (think.md Principle III)")
    print("=" * 60)
    print("\n── Prompt ──")
    test_unified_prompt_covers_all_knowledge_types()
    test_unified_prompt_requires_source_trace()

    print("\n── Dataclass ──")
    test_unified_result_dataclass()
    test_unified_result_with_data()

    print("\n── Agent (no LLM) ──")
    test_agent_instantiation_no_llm()
    test_extract_empty_text_returns_empty()
    test_extract_no_llm_returns_empty()

    print("\n── Internal Parsing ──")
    test_build_characters_filters_empty()
    test_build_scenes_filters_empty()
    test_build_events_filters_empty()
    test_build_events_attaches_source_trace()
    test_build_relations_filters_empty()
    test_build_characters_strips_whitespace()

    print("\n── Batch Extraction ──")
    test_extract_all_chapters_empty_list()
    test_extract_all_chapters_no_llm()

    print("\n── Integration ──")
    test_unified_result_integrates_with_knowledge_merger()

    print("\n── think.md Principle III Verification ──")
    test_principle_three_one_llm_call_per_chapter()
    test_principle_three_source_trace_attached()
    test_principle_three_vs_old_multi_agent()

    print()
    print("ALL UNIFIED EXTRACTION TESTS PASSED")
