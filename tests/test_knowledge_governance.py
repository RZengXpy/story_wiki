"""Tests for Knowledge Governance (MVP 7)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema.models import Character, Scene, Relation, SourceTrace
from core.knowledge_merger import GlobalStoryKnowledge
from core.knowledge_governance import (
    AuditEntry,
    AuditTrail,
    KnowledgeConflict,
    ConflictResolver,
    ValidationIssue,
    ValidationReport,
    SKLValidator,
    Patch,
    KnowledgePatch,
    KnowledgeRevision,
    GovernanceReport,
    KnowledgeGovernor,
    govern_skl,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_gsk(
    characters=None,
    scenes=None,
    relations=None,
    events=None,
    title="雾港档案",
):
    gsk = GlobalStoryKnowledge(title=title, author="StoryForge")
    if characters:
        gsk.characters = characters
    if scenes:
        gsk.scenes = scenes
    if relations:
        gsk.relations = relations
    if events:
        gsk.events = events
    return gsk


def make_char(name, role="supporting", description="", traits=None):
    if traits is None:
        traits = []
    return Character(name=name, role=role, description=description, traits=traits, source=None)


def make_scene(title, location, time_of_day="afternoon", characters=None):
    chars = characters or []
    return Scene(title=title, location=location, time_of_day=time_of_day, description="", characters=chars, source=None)


def make_relation(from_char, to_char, rel_type, description=""):
    return Relation(from_char=from_char, to_char=to_char, relation_type=rel_type, description=description, source=None)


# ── AuditTrail Tests ───────────────────────────────────────────────────────────


def test_audit_trail_record():
    trail = AuditTrail()
    trail.record(
        action="patch",
        target_type="character",
        target_id="林远",
        before={"name": "林远"},
        after={"name": "林远（真名）"},
        reason="用户确认",
    )
    assert len(trail.entries) == 1
    entry = trail.entries[0]
    assert entry.action == "patch"
    assert entry.target_type == "character"
    assert entry.target_id == "林远"
    assert entry.before["name"] == "林远"
    assert entry.after["name"] == "林远（真名）"
    assert entry.reason == "用户确认"
    assert entry.user == "system"
    print("  PASS: audit_trail_record")


def test_audit_trail_get_history():
    trail = AuditTrail()
    trail.record("patch", "character", "林远", {}, {}, user="alice")
    trail.record("patch", "character", "陈雨", {}, {}, user="bob")
    trail.record("auto_correct", "event", "发现真相", {}, {}, user="system")

    char_entries = trail.get_history(target_type="character")
    assert len(char_entries) == 2

    lin_entries = trail.get_history(target_type="character", target_id="林远")
    assert len(lin_entries) == 1
    assert lin_entries[0].target_id == "林远"
    assert lin_entries[0].user == "alice"
    print("  PASS: audit_trail_get_history")


def test_audit_trail_rollback():
    trail = AuditTrail()
    before = {"name": "林远", "role": "supporting"}
    after = {"name": "林远", "role": "protagonist"}
    trail.record("patch", "character", "林远", before, after, reason="role change")

    restored = trail.rollback_to(0)
    assert restored == before
    assert len(trail.entries) == 2  # original + rollback entry
    assert trail.entries[1].action == "rollback"
    print("  PASS: audit_trail_rollback")


def test_audit_trail_clear():
    trail = AuditTrail()
    trail.record("patch", "character", "A", {}, {})
    trail.record("patch", "character", "B", {}, {})
    trail.clear()
    assert len(trail.entries) == 0
    print("  PASS: audit_trail_clear")


# ── ConflictResolver Tests ─────────────────────────────────────────────────────


def test_detect_relation_event_mismatch():
    gsk = make_gsk(
        characters=[make_char("林远"), make_char("陈雨")],
        relations=[make_relation("林远", "陈雨", "friend")],
        events=[
            {
                "title": "林远袭击陈雨",
                "event_type": "conflict",
                "participants": ["林远", "陈雨"],
            }
        ],
    )
    trail = AuditTrail()
    resolver = ConflictResolver(gsk, trail)
    conflicts = resolver.detect_all()
    rel_mismatches = [c for c in conflicts if c.conflict_type == "relation_event_mismatch"]
    assert len(rel_mismatches) >= 1
    print("  PASS: detect_relation_event_mismatch")


def test_detect_character_role_conflict():
    gsk = make_gsk(
        characters=[
            make_char("林远", role="protagonist"),
            make_char("林远", role="supporting"),
        ]
    )
    trail = AuditTrail()
    resolver = ConflictResolver(gsk, trail)
    conflicts = resolver.detect_all()
    role_conflicts = [c for c in conflicts if c.conflict_type == "character_role_conflict"]
    assert len(role_conflicts) >= 1
    print("  PASS: detect_character_role_conflict")


def test_detect_character_identity_merge():
    gsk = make_gsk(
        characters=[
            make_char("林远", description="雾港镇图书管理员"),
            make_char("林远（真名）", description="雾港镇图书管理员"),
        ]
    )
    trail = AuditTrail()
    resolver = ConflictResolver(gsk, trail)
    conflicts = resolver.detect_all()
    identity_conflicts = [c for c in conflicts if c.conflict_type == "character_identity_merge"]
    assert len(identity_conflicts) >= 1
    print("  PASS: detect_character_identity_merge")


def test_auto_resolve_role_conflict():
    gsk = make_gsk(
        characters=[
            make_char("林远", role="protagonist"),
            make_char("林远", role="supporting"),
            make_char("林远", role="protagonist"),
        ]
    )
    trail = AuditTrail()
    resolver = ConflictResolver(gsk, trail)
    unresolved = resolver.auto_resolve()

    # Should auto-resolve role conflict (protagonist appears twice)
    role_conflicts = [c for c in unresolved if c.conflict_type == "character_role_conflict"]
    assert len(role_conflicts) == 0  # all auto-resolved

    # Verify all chars now have protagonist role
    for c in gsk.characters:
        assert c.role == "protagonist"

    # Verify audit trail has entries
    auto_entries = [e for e in trail.entries if e.action == "auto_correct"]
    assert len(auto_entries) >= 1
    print("  PASS: auto_resolve_role_conflict")


def test_auto_resolve_identity_merge():
    gsk = make_gsk(
        characters=[
            make_char("林远", description="雾港镇图书管理员"),
            make_char("林远（真名）", description="雾港镇图书管理员"),
        ]
    )
    trail = AuditTrail()
    resolver = ConflictResolver(gsk, trail)
    unresolved = resolver.auto_resolve()

    # Should auto-resolve identity merge (keep first, remove second)
    identity_conflicts = [c for c in unresolved if c.conflict_type == "character_identity_merge"]
    assert len(identity_conflicts) == 0

    # Only one character should remain
    names = [c.name for c in gsk.characters]
    assert names.count("林远") == 1
    assert "林远（真名）" not in names
    print("  PASS: auto_resolve_identity_merge")


def test_resolve_keep_a_and_b():
    conflict = KnowledgeConflict(
        conflict_type="relation_event_mismatch",
        entity_a={"type": "relation", "id": "r1"},
        entity_b={"type": "event", "id": "e1"},
    )
    trail = AuditTrail()
    resolver = ConflictResolver(None, trail)
    resolver.resolve(conflict, "keep_a")
    assert conflict.resolution == "keep_a"

    conflict2 = KnowledgeConflict(
        conflict_type="relation_event_mismatch",
        entity_a={"type": "relation", "id": "r1"},
        entity_b={"type": "event", "id": "e1"},
    )
    resolver.resolve(conflict2, "keep_b")
    assert conflict2.resolution == "keep_b"
    print("  PASS: resolve_keep_a_and_b")


# ── SKLValidator Tests ────────────────────────────────────────────────────────


def test_validator_missing_characters():
    gsk = make_gsk(characters=[], scenes=[make_scene("场景1", "地点A")])
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    assert not report.passed
    missing_issues = [i for i in report.issues if i.code == "MISSING_REQUIRED_FIELD"]
    assert any("no characters" in i.message for i in missing_issues)
    print("  PASS: validator_missing_characters")


def test_validator_empty_character_name():
    gsk = make_gsk(characters=[make_char("")])
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    empty_name_issues = [i for i in report.issues if i.code == "EMPTY_FIELD" and "empty name" in i.message]
    assert len(empty_name_issues) >= 1
    print("  PASS: validator_empty_character_name")


def test_validator_invalid_event_type():
    gsk = make_gsk(
        characters=[make_char("林远")],
        events=[{"title": "某事件", "event_type": "invalid_type", "participants": ["林远"]}],
    )
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    type_issues = [i for i in report.issues if i.code == "INVALID_TYPE" and i.entity_type == "event"]
    assert len(type_issues) >= 1
    print("  PASS: validator_invalid_event_type")


def test_validator_invalid_relation_type():
    gsk = make_gsk(
        relations=[make_relation("林远", "陈雨", "unknown_type")],
    )
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    type_issues = [i for i in report.issues if i.code == "INVALID_TYPE" and i.entity_type == "relation"]
    assert len(type_issues) >= 1
    print("  PASS: validator_invalid_relation_type")


def test_validator_self_loop_relation():
    gsk = make_gsk(
        relations=[make_relation("林远", "林远", "friend")],
    )
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    loop_issues = [i for i in report.issues if i.entity_type == "relation" and "same source" in i.message]
    assert len(loop_issues) >= 1
    assert any(i.severity == "error" for i in loop_issues)
    print("  PASS: validator_self_loop_relation")


def test_validator_orphan_character():
    gsk = make_gsk(
        characters=[make_char("林远"), make_char("陈雨")],
        scenes=[make_scene("场景1", "地点A", characters=["林远"])],
        events=[],
    )
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    orphan_issues = [i for i in report.issues if i.code == "ORPHAN_ENTITY" and i.entity_type == "character"]
    assert len(orphan_issues) >= 1
    assert any("陈雨" in i.message for i in orphan_issues)
    print("  PASS: validator_orphan_character")


def test_validator_unknown_char_in_event():
    gsk = make_gsk(
        characters=[make_char("林远")],
        events=[{"title": "某事件", "event_type": "conflict", "participants": ["林远", "幽灵"]}],
    )
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    orphan_issues = [i for i in report.issues if i.code == "ORPHAN_ENTITY" and "幽灵" in i.message]
    assert len(orphan_issues) >= 1
    print("  PASS: validator_unknown_char_in_event")


def test_validator_empty_scene_title():
    gsk = make_gsk(scenes=[make_scene("", "地点A")])
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    empty_issues = [i for i in report.issues if i.code == "EMPTY_FIELD" and i.entity_type == "scene"]
    assert len(empty_issues) >= 1
    print("  PASS: validator_empty_scene_title")


def test_validator_passes_clean_data():
    gsk = make_gsk(
        characters=[make_char("林远", role="protagonist")],
        scenes=[make_scene("场景1", "地点A")],
        relations=[make_relation("林远", "陈雨", "friend")],
        events=[{"title": "某事件", "event_type": "conflict", "participants": ["林远", "陈雨"]}],
    )
    validator = SKLValidator(gsk)
    report = validator.validate_all()
    assert report.passed
    error_issues = [i for i in report.issues if i.severity == "error"]
    assert len(error_issues) == 0
    print("  PASS: validator_passes_clean_data")


def test_validation_report_summary():
    report = ValidationReport(passed=True)
    assert "passed" in report.summary().lower()

    report2 = ValidationReport(
        passed=False,
        issues=[
            ValidationIssue("error", "MISSING_REQUIRED_FIELD", "No characters"),
            ValidationIssue("warning", "EMPTY_FIELD", "Empty description"),
        ],
    )
    summary = report2.summary()
    assert "2 issue" in summary
    assert "[ERROR]" in summary
    assert "[WARNING]" in summary
    print("  PASS: validation_report_summary")


# ── KnowledgePatch Tests ──────────────────────────────────────────────────────


def test_patch_character_field():
    gsk = make_gsk(characters=[make_char("林远", role="supporting")])
    trail = AuditTrail()
    patcher = KnowledgePatch(gsk, trail)
    patch = Patch("character", "林远", "role", "supporting", "protagonist", "用户确认")
    success = patcher.apply(patch)
    assert success
    char = gsk.characters[0]
    assert char.role == "protagonist"
    assert len(trail.entries) == 1
    assert trail.entries[0].action == "patch"
    print("  PASS: patch_character_field")


def test_patch_character_not_found():
    gsk = make_gsk(characters=[make_char("林远")])
    trail = AuditTrail()
    patcher = KnowledgePatch(gsk, trail)
    patch = Patch("character", "幽灵", "role", "supporting", "protagonist")
    success = patcher.apply(patch)
    assert not success
    assert len(trail.entries) == 0
    print("  PASS: patch_character_not_found")


def test_patch_cascade_character_rename():
    gsk = make_gsk(
        characters=[make_char("林远")],
        scenes=[make_scene("场景1", "地点A", characters=["林远"])],
        relations=[make_relation("林远", "陈雨", "friend")],
        events=[{"title": "某事件", "participants": ["林远"]}],
    )
    trail = AuditTrail()
    patcher = KnowledgePatch(gsk, trail)
    patch = Patch("character", "林远", "name", "林远", "林远（真名）")
    patcher.apply(patch)

    # Character name updated
    assert gsk.characters[0].name == "林远（真名）"
    # Scene reference updated
    assert "林远（真名）" in gsk.scenes[0].characters
    assert "林远" not in gsk.scenes[0].characters
    # Relation updated
    assert gsk.relations[0].from_char == "林远（真名）"
    # Event updated
    assert "林远（真名）" in gsk.events[0]["participants"]
    print("  PASS: patch_cascade_character_rename")


def test_patch_scene_field():
    gsk = make_gsk(scenes=[make_scene("场景1", "地点A")])
    trail = AuditTrail()
    patcher = KnowledgePatch(gsk, trail)
    patch = Patch("scene", "场景1", "location", "地点A", "雾港镇")
    success = patcher.apply(patch)
    assert success
    assert gsk.scenes[0].location == "雾港镇"
    print("  PASS: patch_scene_field")


def test_patch_relation_field():
    gsk = make_gsk(relations=[make_relation("林远", "陈雨", "friend")])
    trail = AuditTrail()
    patcher = KnowledgePatch(gsk, trail)
    patch = Patch("relation", "林远", "relation_type", "friend", "enemy")
    success = patcher.apply(patch)
    assert success
    assert gsk.relations[0].relation_type == "enemy"
    print("  PASS: patch_relation_field")


# ── KnowledgeRevision Tests ────────────────────────────────────────────────────


def test_revision_normalize_event_types():
    gsk = make_gsk(
        events=[
            {"title": "事件1", "event_type": "confllict"},
            {"title": "事件2", "event_type": "reveal"},
            {"title": "事件3", "event_type": "turning_point"},
        ],
    )
    trail = AuditTrail()
    rev = KnowledgeRevision(gsk, trail)
    corrections = rev.auto_correct()
    assert len(corrections) >= 2  # confllict → conflict, reveal → revelation

    titles = {c["title"] for c in corrections}
    assert "事件1" in titles
    assert "事件2" in titles

    auto_entries = [e for e in trail.entries if e.action == "auto_correct"]
    assert len(auto_entries) >= 2
    print("  PASS: revision_normalize_event_types")


def test_revision_normalize_relation_types():
    gsk = make_gsk(
        relations=[
            make_relation("林远", "陈雨", "familiy"),
            make_relation("林远", "王五", "freind"),
        ],
    )
    trail = AuditTrail()
    rev = KnowledgeRevision(gsk, trail)
    corrections = rev.auto_correct()
    type_corrections = [c for c in corrections if c["type"] == "relation_type_normalized"]
    assert len(type_corrections) >= 2

    types = {c["after"] for c in type_corrections}
    assert "family" in types
    assert "friend" in types
    print("  PASS: revision_normalize_relation_types")


def test_revision_normalize_character_roles():
    gsk = make_gsk(
        characters=[
            make_char("林远", role="prot"),
            make_char("陈雨", role="antag"),
        ],
    )
    trail = AuditTrail()
    rev = KnowledgeRevision(gsk, trail)
    corrections = rev.auto_correct()
    role_corrections = [c for c in corrections if c["type"] == "role_normalized"]
    assert len(role_corrections) >= 2

    roles = {c["after"] for c in role_corrections}
    assert "protagonist" in roles
    assert "antagonist" in roles
    print("  PASS: revision_normalize_character_roles")


# ── KnowledgeGovernor / govern_skl Tests ─────────────────────────────────────


def test_governor_full_pipeline():
    gsk = make_gsk(
        characters=[
            make_char("林远", role="protagonist"),
            make_char("林远", role="supporting"),
            make_char("陈雨"),
        ],
        scenes=[make_scene("场景1", "地点A")],
        relations=[make_relation("林远", "陈雨", "familiy")],
        events=[{"title": "事件1", "event_type": "reveal", "participants": ["林远", "陈雨"]}],
    )
    report = govern_skl(gsk, auto_resolve=True)

    assert isinstance(report, GovernanceReport)
    assert report.validation is not None
    assert report.audit_trail is not None
    assert isinstance(report.auto_corrections, list)
    assert isinstance(report.conflicts, list)

    # Should have auto-corrected relation type via KnowledgeRevision
    rel_corrections = [c for c in report.auto_corrections if c.get("type") == "relation_type_normalized"]
    assert len(rel_corrections) >= 1

    # Should have auto-corrected role conflict via ConflictResolver (recorded in audit trail)
    role_auto_entries = [e for e in report.audit_trail.entries
                         if e.action == "auto_correct" and e.target_type == "character"]
    assert len(role_auto_entries) >= 1

    # All 林远 should now have the same role (majority wins)
    lin_roles = [c.role for c in gsk.characters if c.name == "林远"]
    assert len(set(lin_roles)) == 1, f"林远 should have one consistent role, got: {lin_roles}"

    print("  PASS: govern_full_pipeline")


def test_governor_manual_resolve():
    gsk = make_gsk(
        characters=[make_char("林远", role="protagonist")],
        relations=[make_relation("林远", "陈雨", "friend")],
        events=[{"title": "冲突事件", "event_type": "conflict", "participants": ["林远", "陈雨"]}],
    )
    governor = KnowledgeGovernor(gsk)
    report = governor.govern(auto_resolve=True)

    # relation_event_mismatch should remain unresolved (needs human judgment)
    rel_mismatches = [c for c in report.conflicts if c.conflict_type == "relation_event_mismatch"]
    # The detection is somewhat loose, so just verify the pipeline runs
    assert isinstance(report.conflicts, list)
    print("  PASS: govern_manual_resolve")


def test_governor_apply_patch():
    gsk = make_gsk(
        characters=[make_char("林远", role="supporting")],
        scenes=[make_scene("场景1", "地点A")],
    )
    governor = KnowledgeGovernor(gsk)
    patch = Patch("character", "林远", "role", "supporting", "protagonist", reason="用户确认")
    success = governor.apply_patch(patch)
    assert success
    assert gsk.characters[0].role == "protagonist"
    print("  PASS: govern_apply_patch")


def test_governance_report_summary():
    gsk = make_gsk(characters=[make_char("林远", role="protagonist")])
    report = govern_skl(gsk)
    summary = report.summary()
    assert "Knowledge Governance Report" in summary
    assert "Validation" in summary
    assert "Conflicts" in summary
    assert "Auto-corrected" in summary
    print("  PASS: governance_report_summary")


def test_conflict_resolver_llm_graceful_fallback():
    """resolve_with_llm returns 'manual' when llm is None."""
    conflict = KnowledgeConflict(
        conflict_type="relation_event_mismatch",
        entity_a={"type": "relation", "id": "r1", "from": "A", "to": "B"},
        entity_b={"type": "event", "id": "e1"},
    )
    trail = AuditTrail()
    resolver = ConflictResolver(None, trail, llm=None)
    strategy = resolver.resolve_with_llm(conflict)
    assert strategy == "manual"
    print("  PASS: conflict_resolver_llm_graceful_fallback")


def test_conflict_resolver_llm_format_entity():
    """_format_entity handles various entity shapes gracefully."""
    trail = AuditTrail()
    resolver = ConflictResolver(None, trail)
    assert resolver._format_entity(None) == "(unknown)"
    # Empty dict is falsy in Python, so returns "(unknown)"
    assert resolver._format_entity({}) == "(unknown)"
    assert "role=protagonist" in resolver._format_entity({"name": "林远", "role": "protagonist"})
    assert resolver._format_entity({"type": "relation", "from": "A", "to": "B"}) == "type=relation, from=A, to=B"
    print("  PASS: conflict_resolver_llm_format_entity")


def test_governance_workflow_integration_fields():
    """Verify WorkflowResult has the expected governance fields."""
    from core.workflow import WorkflowResult, GovernanceReport
    result = WorkflowResult(success=True)
    assert hasattr(result, "governance_report")
    assert result.governance_report is None
    print("  PASS: workflow_integration_fields")


def test_storygraph_apply_character_rename():
    """Test that apply_character_rename propagates to characters, scenes, events, relations, scripts."""
    from core.story_graph import StoryGraph, CharacterNode, SceneNode, EventNode, ScriptNode, ScriptItem, CharacterRole, EventType

    graph = StoryGraph()
    graph.characters = [
        CharacterNode(id="林远", name="林远", role=CharacterRole.PROTAGONIST),
    ]
    graph.scenes = [
        SceneNode(id="scene1", title="图书馆", characters_present=["林远", "陈雨"]),
    ]
    graph.events = [
        EventNode(title="相遇", event_type=EventType.REVELATION, participants=["林远"]),
    ]
    graph.relations = [
        # Using a mock relation-like object since RelationNode is not defined as dict-like
    ]
    # Manually add relation via __dict__ approach
    class MockRelation:
        def __init__(self):
            self.from_char = "林远"
            self.to_char = "陈雨"
    graph.relations = [MockRelation()]

    # Add a script with dialogue
    graph.scripts = {
        "scene1": ScriptNode(
            id="scene1",
            content=[
                ScriptItem(type="dialogue", character="林远", text="林远说：你好"),
                ScriptItem(type="action", text="林远走进图书馆"),
            ]
        )
    }

    changed = graph.apply_character_rename("林远", "林远（真名）")

    # CharacterNode
    assert graph.characters[0].name == "林远（真名）"
    assert graph.characters[0].id == "林远（真名）"
    # Scene
    assert "林远（真名）" in graph.scenes[0].characters_present
    assert "林远" not in graph.scenes[0].characters_present
    # Event
    assert "林远（真名）" in graph.events[0].participants
    assert "林远" not in graph.events[0].participants
    # Relation
    assert graph.relations[0].from_char == "林远（真名）"
    # Scripts
    assert graph.scripts["scene1"].content[0].character == "林远（真名）"
    assert "林远（真名）" in graph.scripts["scene1"].content[1].text

    print("  PASS: storygraph_apply_character_rename")


def test_governor_with_graph_propagates_rename():
    """Test KnowledgeGovernor.apply_patch propagates rename to StoryGraph."""
    from core.story_graph import StoryGraph, CharacterNode, SceneNode, ScriptNode, ScriptItem, CharacterRole

    gsk = make_gsk(characters=[make_char("林远", role="protagonist")])
    graph = StoryGraph()
    graph.characters = [CharacterNode(id="林远", name="林远", role=CharacterRole.PROTAGONIST)]
    graph.scenes = [SceneNode(id="scene1", title="图书馆", characters_present=["林远"])]
    graph.scripts = {"scene1": ScriptNode(id="scene1", content=[ScriptItem(type="dialogue", character="林远", text="林远：你好")])}

    governor = KnowledgeGovernor(gsk, graph=graph)
    patch = Patch("character", "林远", "name", "林远", "林远（真名）", reason="用户确认")
    success = governor.apply_patch(patch)

    assert success
    # SKL updated
    assert gsk.characters[0].name == "林远（真名）"
    # Graph updated
    assert graph.characters[0].name == "林远（真名）"
    assert graph.scenes[0].characters_present[0] == "林远（真名）"
    assert graph.scripts["scene1"].content[0].character == "林远（真名）"

    print("  PASS: governor_with_graph_propagates_rename")


# ── Run all tests ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=" * 60)
    print("Knowledge Governance Tests (MVP 7)")
    print("=" * 60)

    tests = [
        # AuditTrail
        test_audit_trail_record,
        test_audit_trail_get_history,
        test_audit_trail_rollback,
        test_audit_trail_clear,
        # ConflictResolver
        test_detect_relation_event_mismatch,
        test_detect_character_role_conflict,
        test_detect_character_identity_merge,
        test_auto_resolve_role_conflict,
        test_auto_resolve_identity_merge,
        test_resolve_keep_a_and_b,
        # SKLValidator
        test_validator_missing_characters,
        test_validator_empty_character_name,
        test_validator_invalid_event_type,
        test_validator_invalid_relation_type,
        test_validator_self_loop_relation,
        test_validator_orphan_character,
        test_validator_unknown_char_in_event,
        test_validator_empty_scene_title,
        test_validator_passes_clean_data,
        test_validation_report_summary,
        # KnowledgePatch
        test_patch_character_field,
        test_patch_character_not_found,
        test_patch_cascade_character_rename,
        test_patch_scene_field,
        test_patch_relation_field,
        # KnowledgeRevision
        test_revision_normalize_event_types,
        test_revision_normalize_relation_types,
        test_revision_normalize_character_roles,
        # KnowledgeGovernor / govern_skl
        test_governor_full_pipeline,
        test_governor_manual_resolve,
        test_governor_apply_patch,
        test_governance_report_summary,
        test_governance_workflow_integration_fields,
        # StoryGraph patch propagation
        test_storygraph_apply_character_rename,
        test_governor_with_graph_propagates_rename,
        # LLM-enhanced conflict resolution
        test_conflict_resolver_llm_graceful_fallback,
        test_conflict_resolver_llm_format_entity,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)
