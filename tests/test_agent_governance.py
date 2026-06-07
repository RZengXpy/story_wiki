"""Tests for Agent Governance Methods — think.md Principle IV.

These tests verify that agents have governance methods that operate on
the GlobalStoryKnowledge (SKL), not on raw text.

Per think.md Principle IV:
  CharacterAgent: deduplicate, merge_aliases, identify_protagonist, assign_roles
  EventAgent: merge_events, build_causal_chains, identify_key_events
  RelationAgent: (handled in knowledge_governance.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema.models import Character, Scene, Relation, SourceTrace
from core.knowledge_merger import GlobalStoryKnowledge
from agent.character_agent import CharacterAgent
from agent.event_agent import EventAgent


def make_gsk(**kwargs):
    """Create a minimal GlobalStoryKnowledge for testing."""
    gsk = GlobalStoryKnowledge(title="测试", author="Test")
    for k, v in kwargs.items():
        setattr(gsk, k, v)
    return gsk


# ── CharacterAgent Governance ──────────────────────────────────────────────────

def test_char_agent_deduplicate():
    """CharacterAgent.deduplicate() removes characters with the same name."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="protagonist"),
            Character(name="林远", description="图书管理员（补充描述）", traits=["细心"], role="protagonist"),
            Character(name="陈雨", description="记者", traits=[], role="supporting"),
        ]
    )
    agent = CharacterAgent()
    audit = agent.deduplicate(gsk)

    names = [c.name for c in gsk.characters]
    assert names.count("林远") == 1, f"Should have 1 林远, got {names.count('林远')}: {names}"
    assert "林远" in names
    assert "陈雨" in names
    assert len(gsk.characters) == 2

    # Audit should record the deduplication
    assert len(audit) == 1
    assert audit[0]["action"] == "deduplicate"
    assert audit[0]["name"] == "林远"
    print("  PASS: char_agent_deduplicate")


def test_char_agent_deduplicate_merges_traits():
    """Deduplication should merge traits from both copies."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=["细心"], role="protagonist"),
            Character(name="林远", description="图书管理员（更长描述）", traits=["细心", "勇敢"], role="protagonist"),
        ]
    )
    agent = CharacterAgent()
    agent.deduplicate(gsk)

    lin = next(c for c in gsk.characters if c.name == "林远")
    assert "细心" in lin.traits
    assert "勇敢" in lin.traits
    assert len(lin.traits) == 2
    # Description should be the longer one
    assert "更长" in lin.description
    print("  PASS: char_agent_deduplicate_merges_traits")


def test_char_agent_merge_aliases_exact():
    """CharacterAgent.merge_aliases() merges exact same names."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="protagonist"),
            Character(name="林远", description="图书管理员", traits=["细心"], role="supporting"),
        ]
    )
    agent = CharacterAgent()
    audit = agent.merge_aliases(gsk)

    names = [c.name for c in gsk.characters]
    assert names.count("林远") == 1
    # Traits should be merged
    lin = next(c for c in gsk.characters if c.name == "林远")
    assert "细心" in lin.traits
    print("  PASS: char_agent_merge_aliases_exact")


def test_char_agent_merge_aliases_contains():
    """CharacterAgent.merge_aliases() merges names that contain each other."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="protagonist"),
            Character(name="林远（真名）", description="图书管理员", traits=[], role="supporting"),
            Character(name="林川", description="另一位", traits=[], role="supporting"),
        ]
    )
    agent = CharacterAgent()
    audit = agent.merge_aliases(gsk)

    names = [c.name for c in gsk.characters]
    # "林远" and "林远（真名）" should be merged (one contains the other)
    assert names.count("林远") + names.count("林远（真名）") == 1
    # 林川 should remain
    assert "林川" in names
    print("  PASS: char_agent_merge_aliases_contains")


def test_char_agent_merge_aliases_no_false_merge():
    """Different characters with different names should NOT be merged."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="protagonist"),
            Character(name="陈雨", description="记者", traits=[], role="supporting"),
            Character(name="王五", description="警官", traits=[], role="supporting"),
        ]
    )
    agent = CharacterAgent()
    audit = agent.merge_aliases(gsk)

    assert len(gsk.characters) == 3
    assert len(audit) == 0
    print("  PASS: char_agent_merge_aliases_no_false_merge")


def test_char_agent_identify_protagonist_explicit():
    """Explicitly labeled protagonist is returned directly."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="protagonist"),
            Character(name="陈雨", description="记者", traits=[], role="supporting"),
        ]
    )
    agent = CharacterAgent()
    protagonist = agent.identify_protagonist(gsk)
    assert protagonist is not None
    assert protagonist.name == "林远"
    print("  PASS: char_agent_identify_protagonist_explicit")


def test_char_agent_identify_protagonist_by_events():
    """Without explicit label, protagonist is identified by event participation."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="supporting"),
            Character(name="陈雨", description="记者", traits=[], role="supporting"),
        ],
        events=[
            {"title": "相遇", "event_type": "revelation", "participants": ["林远", "陈雨"]},
            {"title": "探索", "event_type": "conflict", "participants": ["林远"]},
            {"title": "失踪", "event_type": "turning_point", "participants": ["陈雨"]},
        ],
        character_first_appearance={"林远": "第一章", "陈雨": "第一章"},
    )
    agent = CharacterAgent()
    protagonist = agent.identify_protagonist(gsk)
    assert protagonist is not None
    # 林远 has 2 event participations vs 陈雨's 2
    # Should be one of them
    assert protagonist.name in ("林远", "陈雨")
    print("  PASS: char_agent_identify_protagonist_by_events")


def test_char_agent_assign_roles():
    """CharacterAgent.assign_roles() assigns protagonist/antagonist/supporting based on events."""
    gsk = make_gsk(
        characters=[
            Character(name="林远", description="图书管理员", traits=[], role="supporting"),
            Character(name="反派", description="坏人", traits=[], role="supporting"),
            Character(name="配角", description="次要角色", traits=[], role="supporting"),
        ],
        events=[
            # 林远 participates in 3 events (most)
            {"title": "E1", "event_type": "revelation", "participants": ["林远"]},
            {"title": "E2", "event_type": "transition", "participants": ["林远"]},
            {"title": "E3", "event_type": "turning_point", "participants": ["林远"]},
            # 反派 participates in 2 conflict events
            {"title": "E4", "event_type": "conflict", "participants": ["反派", "林远"]},
            {"title": "E5", "event_type": "conflict", "participants": ["反派"]},
            # 配角 participates in 1 event
            {"title": "E6", "event_type": "transition", "participants": ["配角"]},
        ],
    )
    agent = CharacterAgent()
    audit = agent.assign_roles(gsk)

    roles = {c.name: c.role for c in gsk.characters}
    assert roles["林远"] == "protagonist"
    assert roles["反派"] == "antagonist"
    assert roles["配角"] == "supporting"

    # Audit should record the changes
    assert len(audit) >= 2  # at least protagonist and antagonist
    print("  PASS: char_agent_assign_roles")


# ── EventAgent Governance ──────────────────────────────────────────────────────

def test_event_agent_merge_events():
    """EventAgent.merge_events() deduplicates events by title."""
    gsk = make_gsk(
        events=[
            {"title": "相遇", "event_type": "revelation", "participants": ["林远"]},
            {"title": "相遇", "event_type": "revelation", "participants": ["陈雨"]},  # duplicate
            {"title": "探索", "event_type": "conflict", "participants": ["林远"]},
        ]
    )
    agent = EventAgent()
    audit = agent.merge_events(gsk)

    titles = [e.get("title", "") if isinstance(e, dict) else getattr(e, "title", "") for e in gsk.events]
    assert titles.count("相遇") == 1
    assert "探索" in titles
    assert len(gsk.events) == 2
    print("  PASS: event_agent_merge_events")


def test_event_agent_merge_events_merges_participants():
    """Event deduplication should merge participant lists."""
    gsk = make_gsk(
        events=[
            {"title": "相遇", "event_type": "revelation", "participants": ["林远"]},
            {"title": "相遇", "event_type": "revelation", "participants": ["陈雨"]},
        ]
    )
    agent = EventAgent()
    agent.merge_events(gsk)

    assert len(gsk.events) == 1
    remaining = gsk.events[0]
    e_dict = remaining if isinstance(remaining, dict) else {}
    participants = e_dict.get("participants", [])
    assert "林远" in participants
    assert "陈雨" in participants
    print("  PASS: event_agent_merge_events_merges_participants")


def test_event_agent_build_causal_chains():
    """EventAgent.build_causal_chains() extracts cause→effect relationships.

    Each event's cause field creates a "cause → title" chain.
    Each event's consequence field creates a "title → consequence" chain.
    Chains are deduplicated by (cause_event, effect_event) pair.
    """
    gsk = make_gsk(
        events=[
            {
                "title": "发现日志",
                "event_type": "revelation",
                "cause": "老人指引",
                "consequence": "前往灯塔",
                "participants": ["林远"],
            },
            {
                "title": "灯塔探索",
                "event_type": "conflict",
                "cause": "发现日志",   # causes to existing event "发现日志"
                "consequence": "遭遇危险",
                "participants": ["林远", "陈雨"],
            },
        ]
    )
    agent = EventAgent()
    chains = agent.build_causal_chains(gsk)

    # Should have 4 chains:
    # 1. 老人指引 → 发现日志  (from Event1 cause)
    # 2. 发现日志 → 前往灯塔  (from Event1 consequence)
    # 3. 发现日志 → 灯塔探索  (from Event2 cause)
    # 4. 灯塔探索 → 遭遇危险  (from Event2 consequence)
    # (no duplicates — each (cause, effect) pair is unique)
    assert len(chains) == 4, f"Expected 4 chains, got {len(chains)}: {chains}"

    # Deduplication: if two events share the same cause AND same effect,
    # only one chain should exist
    cause_to_effect = [(c["cause_event"], c["effect_event"]) for c in chains]
    assert len(cause_to_effect) == len(set(cause_to_effect)), "Chains should be unique"

    # All chains should have valid directions
    for c in chains:
        assert c["direction"] in ("cause_to_effect", "effect_to_consequence")
        assert c["causal_link"]

    # Find chains involving "发现日志"
    find_log = [c for c in chains
                 if c["cause_event"] == "发现日志" or c["effect_event"] == "发现日志"]
    assert len(find_log) == 3, f"Expected 3 chains for '发现日志', got {len(find_log)}"
    # 1. 老人指引 → 发现日志  (cause_to_effect, 发现日志 is effect)
    # 2. 发现日志 → 前往灯塔  (effect_to_consequence, 发现日志 is cause)
    # 3. 发现日志 → 灯塔探索  (cause_to_effect, 发现日志 is cause)
    directions = {c["direction"] for c in find_log}
    assert "cause_to_effect" in directions
    assert "effect_to_consequence" in directions
    print("  PASS: event_agent_build_causal_chains")


def test_event_agent_identify_key_events():
    """EventAgent.identify_key_events() finds inciting incident, climax, resolution."""
    gsk = make_gsk(
        events=[
            {"title": "序章", "event_type": "transition", "participants": []},
            {"title": "触发事件", "event_type": "turning_point", "participants": ["林远", "陈雨"]},
            {"title": "真相揭露", "event_type": "revelation", "participants": ["林远"]},
            {"title": "高潮对决", "event_type": "turning_point", "participants": ["林远", "反派"]},
            {"title": "结局", "event_type": "resolution", "participants": ["林远"]},
        ]
    )
    agent = EventAgent()
    key = agent.identify_key_events(gsk)

    assert key["inciting_incident"] == "触发事件", f"Expected '触发事件', got {key['inciting_incident']}"
    # Climax should be turning_point with most participants
    assert key["climax"] in ("触发事件", "高潮对决"), f"Unexpected climax: {key['climax']}"
    assert key["resolution"] == "结局"
    print("  PASS: event_agent_identify_key_events")


def test_event_agent_identify_key_events_empty():
    """Empty event list returns empty key events."""
    gsk = make_gsk(events=[])
    agent = EventAgent()
    key = agent.identify_key_events(gsk)
    assert key["inciting_incident"] is None
    assert key["climax"] is None
    assert key["resolution"] is None
    print("  PASS: event_agent_identify_key_events_empty")


def test_event_agent_filter_key_events():
    """filter_key_events() returns only events with threshold+ participants."""
    gsk = make_gsk(
        events=[
            {"title": "单人事件", "event_type": "revelation", "participants": ["林远"]},
            {"title": "双人事件", "event_type": "revelation", "participants": ["林远", "陈雨"]},
            {"title": "三人事件", "event_type": "conflict", "participants": ["林远", "陈雨", "王五"]},
        ]
    )
    agent = EventAgent()
    filtered = agent.filter_key_events(gsk, threshold=2)
    titles = [e.get("title") for e in filtered]
    assert "双人事件" in titles
    assert "三人事件" in titles
    assert "单人事件" not in titles
    print("  PASS: event_agent_filter_key_events")


# ── Director Agent ──────────────────────────────────────────────────────────────

def test_director_agent_no_llm():
    """DirectorAgent with no LLM returns empty bible."""
    from agent.director_agent import DirectorAgent, ScreenplayBible
    agent = DirectorAgent()
    bible = agent.create_bible(None)
    assert isinstance(bible, ScreenplayBible)
    assert bible.genre == ""
    print("  PASS: director_agent_no_llm")


def test_screenplay_bible_dataclass():
    """ScreenplayBible holds all required fields."""
    from agent.director_agent import ScreenplayBible
    bible = ScreenplayBible(
        genre="thriller",
        tone="suspenseful",
        themes=["truth", "mystery"],
        character_portraits=[{"name": "林远", "psychology": "cautious"}],
    )
    assert bible.genre == "thriller"
    assert "truth" in bible.themes
    assert len(bible.character_portraits) == 1
    d = bible.to_dict()
    assert d["genre"] == "thriller"
    assert d["tone"] == "suspenseful"
    print("  PASS: screenplay_bible_dataclass")


def test_build_skl_summary():
    """_build_skl_summary produces readable text from GSK."""
    from agent.director_agent import _build_skl_summary
    from core.knowledge_merger import GlobalStoryKnowledge
    from schema.models import Character

    gsk = GlobalStoryKnowledge(title="测试")
    gsk.characters = [Character(name="林远", description="图书管理员", traits=["细心"], role="protagonist")]
    gsk.outline = {"genre": "thriller", "theme": "真相", "main_conflict": "寻找日志"}

    text = _build_skl_summary(gsk)
    assert "测试" in text
    assert "林远" in text
    assert "thriller" in text
    assert "图书管理员" in text
    print("  PASS: build_skl_summary")


if __name__ == "__main__":
    print("=" * 60)
    print("Agent Governance Tests (think.md Principle IV)")
    print("=" * 60)

    print("\n── CharacterAgent Governance ──")
    test_char_agent_deduplicate()
    test_char_agent_deduplicate_merges_traits()
    test_char_agent_merge_aliases_exact()
    test_char_agent_merge_aliases_contains()
    test_char_agent_merge_aliases_no_false_merge()
    test_char_agent_identify_protagonist_explicit()
    test_char_agent_identify_protagonist_by_events()
    test_char_agent_assign_roles()

    print("\n── EventAgent Governance ──")
    test_event_agent_merge_events()
    test_event_agent_merge_events_merges_participants()
    test_event_agent_build_causal_chains()
    test_event_agent_identify_key_events()
    test_event_agent_identify_key_events_empty()
    test_event_agent_filter_key_events()

    print("\n── Director Agent ──")
    test_director_agent_no_llm()
    test_screenplay_bible_dataclass()
    test_build_skl_summary()

    print()
    print("ALL AGENT GOVERNANCE TESTS PASSED")
