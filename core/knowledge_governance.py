"""Knowledge Governance — ensures SKL quality through conflict resolution, validation, patching, and audit.

Implements the "Explainable" and "Consistency By Design" principles.
Runs after SKL is built (Local → Global merge) and before screenplay generation.

Architectural position in pipeline:
  SKL 构建（Local → Global）
        │
        ▼
  ┌─────────────────┐
  │  知识治理层        │  ← MVP 7
  │  · 冲突仲裁       │
  │  · 一致性校验     │
  │  · 知识修正       │
  │  · 变更回写       │
  └─────────────────┘
        │
        ▼
    StoryGraph（高质量）
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import copy


# ── Audit Trail ────────────────────────────────────────────────────────────────


@dataclass
class AuditEntry:
    """A single change record in the audit trail."""
    timestamp: str
    action: str          # "patch" | "auto_correct" | "reject" | "resolve_conflict"
    target_type: str     # "character" | "scene" | "event" | "relation" | "skl"
    target_id: str       # identifier of the affected entity
    before: Optional[dict]
    after: Optional[dict]
    reason: str = ""
    user: str = "system"


@dataclass
class AuditTrail:
    """Records all mutations to the SKL, supporting rollback."""
    entries: list[AuditEntry] = field(default_factory=list)

    def record(
        self,
        action: str,
        target_type: str,
        target_id: str,
        before: Optional[dict],
        after: Optional[dict],
        reason: str = "",
        user: str = "system",
    ) -> None:
        self.entries.append(AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=copy.deepcopy(before),
            after=copy.deepcopy(after),
            reason=reason,
            user=user,
        ))

    def get_history(self, target_type: str = "", target_id: str = "") -> list[AuditEntry]:
        """Retrieve audit entries, optionally filtered."""
        results = self.entries
        if target_type:
            results = [e for e in results if e.target_type == target_type]
        if target_id:
            results = [e for e in results if e.target_id == target_id]
        return results

    def rollback_to(self, index: int) -> Optional[dict]:
        """Roll back to the state before a given audit entry index. Returns the restored data."""
        if 0 <= index < len(self.entries):
            entry = self.entries[index]
            self.record(
                action="rollback",
                target_type=entry.target_type,
                target_id=entry.target_id,
                before=entry.after,
                after=entry.before,
                reason=f"Rollback to index {index}",
            )
            return copy.deepcopy(entry.before)
        return None

    def clear(self) -> None:
        self.entries.clear()


# ── Conflict ───────────────────────────────────────────────────────────────────


@dataclass
class KnowledgeConflict:
    """A detected knowledge conflict between two pieces of information."""
    conflict_type: str    # "relation_event_mismatch" | "character_role_conflict"
                          # | "character_identity_merge" | "scene_location_conflict"
    entity_a: dict       # first conflicting piece of knowledge
    entity_b: dict       # second conflicting piece
    resolution: str = ""  # "keep_a" | "keep_b" | "merge" | "manual" | ""
    resolved_value: Any = None


class ConflictResolver:
    """Detects and resolves conflicts between knowledge extracted by different agents."""

    def __init__(self, gsk, audit_trail: AuditTrail, llm=None):
        self.gsk = gsk
        self.audit_trail = audit_trail
        self.llm = llm

    def detect_all(self) -> list[KnowledgeConflict]:
        """Run all conflict detection rules."""
        conflicts = []
        conflicts.extend(self._detect_relation_event_mismatches())
        conflicts.extend(self._detect_character_role_conflicts())
        conflicts.extend(self._detect_character_identity_conflicts())
        return conflicts

    def resolve(self, conflict: KnowledgeConflict, strategy: str) -> None:
        """Apply a resolution strategy to a conflict.

        Strategies:
        - "keep_a": keep entity_a, discard entity_b
        - "keep_b": keep entity_b, discard entity_a
        - "merge": merge the two entities (for character identity conflicts)
        - "manual": leave unresolved for human review
        """
        conflict.resolution = strategy
        if strategy == "keep_a":
            self._apply_keep_a(conflict)
        elif strategy == "keep_b":
            self._apply_keep_b(conflict)
        elif strategy == "merge":
            self._apply_merge(conflict)
        # "manual" does nothing — conflict remains in unresolved list

    def resolve_with_llm(self, conflict: KnowledgeConflict) -> str:
        """Use LLM to resolve a conflict when rules are insufficient.

        This method uses the LLM to analyze the context of a conflict and
        determine the most appropriate resolution strategy.

        Returns:
            Resolution strategy: "keep_a" | "keep_b" | "merge" | "manual"
        """
        if self.llm is None:
            return "manual"

        system_prompt = (
            "You are a story consistency expert. Analyze the following conflict "
            "between two pieces of extracted knowledge and determine the best resolution. "
            "Reply with ONLY ONE of these strategies: keep_a, keep_b, merge, manual"
        )
        user_prompt = self._build_llm_prompt(conflict)
        try:
            response = self.llm.generate(system_prompt, user_prompt, temperature=0.3)
            strategy = response.strip().lower()
            if strategy not in ("keep_a", "keep_b", "merge", "manual"):
                return "manual"
            return strategy
        except Exception:
            return "manual"

    def _build_llm_prompt(self, conflict: KnowledgeConflict) -> str:
        """Build a detailed prompt describing the conflict for the LLM."""
        lines = [
            f"Conflict Type: {conflict.conflict_type}",
            "",
            f"Entity A: {self._format_entity(conflict.entity_a)}",
            f"Entity B: {self._format_entity(conflict.entity_b)}",
            "",
            "Story Context:",
        ]
        if self.gsk is not None:
            lines.extend([
                f"  Characters: {[c.name for c in self.gsk.characters]}",
                f"  Total scenes: {len(self.gsk.scenes)}",
                f"  Total events: {len(self.gsk.events)}",
            ])
        else:
            lines.append("  (no story context available)")
        return "\n".join(lines)

    def _format_entity(self, entity: dict) -> str:
        """Format a conflict entity for LLM prompt readability."""
        if not entity:
            return "(unknown)"
        parts = [f"{k}={v}" for k, v in entity.items() if v]
        return ", ".join(parts) if parts else "(empty)"

    def auto_resolve(self) -> list[KnowledgeConflict]:
        """Attempt automatic resolution of all detected conflicts.

        Returns list of conflicts that could not be auto-resolved.
        """
        unresolved = []
        for conflict in self.detect_all():
            if self._try_auto_resolve(conflict):
                self._apply_auto_resolution(conflict)
                conflict.resolution = "auto"
            else:
                unresolved.append(conflict)
        return unresolved

    # ── Detection rules ─────────────────────────────────────────────────────

    def _detect_relation_event_mismatches(self) -> list[KnowledgeConflict]:
        """Detect when relation type contradicts event type.

        E.g., "A --friend--> B" but event says "A attacked B".
        """
        conflicts = []
        hostile_events = {"conflict", "turning_point"}
        friendly_relations = {"friend", "family", "romantic"}
        hostile_relations = {"enemy"}

        char_event_types: dict[str, set[str]] = {}
        for e in self.gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            for p in e_dict.get("participants", []):
                char_event_types.setdefault(p, set()).add(
                    e_dict.get("event_type", "transition")
                )

        for rel in self.gsk.relations:
            fc, tc = rel.from_char, rel.to_char
            rel_type = rel.relation_type
            if rel_type in friendly_relations:
                # Check if any event shows hostility between these two
                for char, events in char_event_types.items():
                    if char in (fc, tc) and events & hostile_events:
                        # Check if the OTHER person is also involved
                        other = tc if char == fc else fc
                        other_events = char_event_types.get(other, set())
                        if other_events & hostile_events:
                            conflicts.append(KnowledgeConflict(
                                conflict_type="relation_event_mismatch",
                                entity_a={
                                    "type": "relation",
                                    "from": fc, "to": tc,
                                    "relation_type": rel_type,
                                },
                                entity_b={
                                    "type": "events",
                                    "chars": [fc, tc],
                                    "event_types": list(events & hostile_events),
                                },
                            ))
                            break
            elif rel_type in hostile_relations:
                # Check if any event shows friendliness
                pass  # hostile relations are consistent with conflict events
        return conflicts

    def _detect_character_role_conflicts(self) -> list[KnowledgeConflict]:
        """Detect when a character's role is stated inconsistently across extractions."""
        conflicts = []
        # Group characters by normalized name
        name_groups: dict[str, list] = {}
        for c in self.gsk.characters:
            key = c.name.strip()
            name_groups.setdefault(key, []).append(c)

        # Check for same character with different role labels
        for name, chars in name_groups.items():
            if len(chars) < 2:
                continue
            roles = {getattr(c, "role", "supporting") for c in chars}
            if len(roles) > 1:
                conflicts.append(KnowledgeConflict(
                    conflict_type="character_role_conflict",
                    entity_a={"name": name, "roles": list(roles)},
                    entity_b={"name": name, "chars": [id(c) for c in chars]},
                ))
        return conflicts

    def _detect_character_identity_conflicts(self) -> list[KnowledgeConflict]:
        """Detect potential duplicate characters (same person, different names).

        Uses simple fuzzy match on description overlap.
        """
        conflicts = []
        chars = self.gsk.characters
        for i in range(len(chars)):
            for j in range(i + 1, len(chars)):
                c1, c2 = chars[i], chars[j]
                n1, n2 = c1.name.strip(), c2.name.strip()
                if n1 == n2:
                    continue  # exact match — handled by dedup, not identity conflict
                # Check description overlap
                d1 = getattr(c1, "description", "") or ""
                d2 = getattr(c2, "description", "") or ""
                if len(d1) > 5 and len(d2) > 5 and d1 == d2:
                    conflicts.append(KnowledgeConflict(
                        conflict_type="character_identity_merge",
                        entity_a={"name": n1, "description": d1[:50]},
                        entity_b={"name": n2, "description": d2[:50]},
                    ))
        return conflicts

    # ── Resolution helpers ───────────────────────────────────────────────────

    def _try_auto_resolve(self, conflict: KnowledgeConflict) -> bool:
        """Determine if a conflict can be auto-resolved."""
        ct = conflict.conflict_type
        if ct == "character_role_conflict":
            return True  # can auto-resolve by keeping most common role
        if ct == "character_identity_merge":
            return True  # can auto-resolve by keeping first occurrence
        return False  # relation_event_mismatch needs human judgment

    def _apply_auto_resolution(self, conflict: KnowledgeConflict) -> None:
        ct = conflict.conflict_type
        if ct == "character_role_conflict":
            # Keep the most common role
            name = conflict.entity_a.get("name", "")
            chars = [c for c in self.gsk.characters if c.name == name]
            if chars:
                role_counts: dict[str, int] = {}
                for c in chars:
                    r = getattr(c, "role", "supporting")
                    role_counts[r] = role_counts.get(r, 0) + 1
                majority_role = max(role_counts, key=role_counts.get)
                for c in chars:
                    old_role = getattr(c, "role", "supporting")
                    if old_role != majority_role:
                        before = {"name": c.name, "role": old_role}
                        c.role = majority_role
                        after = {"name": c.name, "role": majority_role}
                        self.audit_trail.record(
                            action="auto_correct",
                            target_type="character",
                            target_id=c.name,
                            before=before, after=after,
                            reason=f"Auto-resolve role conflict: {old_role} → {majority_role}",
                        )

        elif ct == "character_identity_merge":
            # Keep the first character (earlier in list), remove the duplicate
            name_a = conflict.entity_a.get("name", "")
            name_b = conflict.entity_b.get("name", "")
            chars_to_remove = [c for c in self.gsk.characters if c.name == name_b]
            if chars_to_remove:
                c = chars_to_remove[0]
                self.audit_trail.record(
                    action="auto_correct",
                    target_type="character",
                    target_id=name_b,
                    before={"name": name_b},
                    after=None,
                    reason=f"Auto-merge duplicate character: {name_b} → {name_a}",
                )
                self.gsk.characters.remove(c)
                # Update relations that reference name_b
                for rel in self.gsk.relations:
                    if rel.from_char == name_b:
                        rel.from_char = name_a
                    if rel.to_char == name_b:
                        rel.to_char = name_a

    def _apply_keep_a(self, conflict: KnowledgeConflict) -> None:
        """Keep entity_a, remove entity_b from gsk."""
        name_b = conflict.entity_b.get("name", "")
        name_a = conflict.entity_a.get("name", "")
        if name_b:
            self.gsk.characters = [c for c in self.gsk.characters if c.name != name_b]
            for rel in self.gsk.relations:
                if rel.from_char == name_b:
                    rel.from_char = name_a
                if rel.to_char == name_b:
                    rel.to_char = name_a
        conflict.resolved_value = conflict.entity_a
        self.audit_trail.record("resolve_conflict", conflict.entity_a.get("type", "unknown"),
                                conflict.entity_a.get("id", ""), conflict.entity_a, conflict.entity_b,
                                reason=f"Keep entity A, discard entity B")

    def _apply_keep_b(self, conflict: KnowledgeConflict) -> None:
        """Keep entity_b, remove entity_a from gsk."""
        name_a = conflict.entity_a.get("name", "")
        name_b = conflict.entity_b.get("name", "")
        if name_a:
            self.gsk.characters = [c for c in self.gsk.characters if c.name != name_a]
            for rel in self.gsk.relations:
                if rel.from_char == name_a:
                    rel.from_char = name_b
                if rel.to_char == name_a:
                    rel.to_char = name_b
        conflict.resolved_value = conflict.entity_b
        self.audit_trail.record("resolve_conflict", conflict.entity_b.get("type", "unknown"),
                                conflict.entity_b.get("id", ""), conflict.entity_b, conflict.entity_a,
                                reason=f"Keep entity B, discard entity A")

    def _apply_merge(self, conflict: KnowledgeConflict) -> None:
        """Merge entity_b into entity_a (keep A, remove B, update relations)."""
        name_a = conflict.entity_a.get("name", "")
        name_b = conflict.entity_b.get("name", "")
        if name_b and name_a:
            self.gsk.characters = [c for c in self.gsk.characters if c.name != name_b]
            for rel in self.gsk.relations:
                if rel.from_char == name_b:
                    rel.from_char = name_a
                if rel.to_char == name_b:
                    rel.to_char = name_a
        self.audit_trail.record("resolve_conflict", "character",
                                conflict.entity_a.get("name", ""),
                                conflict.entity_a, conflict.entity_b,
                                reason="Merge conflicting entities")


# ── Validator ──────────────────────────────────────────────────────────────────


@dataclass
class ValidationIssue:
    """A single validation issue found in the SKL."""
    severity: str      # "error" | "warning" | "info"
    code: str          # "MISSING_REQUIRED_FIELD" | "INVALID_TYPE" | "ORPHAN_ENTITY"
                       # | "UNRESOLVED_CONFLICT" | "EMPTY_FIELD"
    message: str
    entity_type: str = ""
    entity_id: str = ""


@dataclass
class ValidationReport:
    """Result of SKL validation."""
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def summary(self) -> str:
        if self.passed:
            return "Validation passed."
        lines = [f"{len(self.issues)} issue(s) found:"]
        for issue in self.issues:
            lines.append(f"  [{issue.severity.upper()}] {issue.code}: {issue.message}")
        return "\n".join(lines)


class SKLValidator:
    """Validates the completeness and consistency of GlobalStoryKnowledge."""

    VALID_EVENT_TYPES = {"conflict", "revelation", "transition", "turning_point", "resolution"}
    VALID_RELATION_TYPES = {"family", "friend", "enemy", "romantic", "professional", "stranger"}
    VALID_CHARACTER_ROLES = {"protagonist", "antagonist", "supporting"}

    def __init__(self, gsk):
        self.gsk = gsk

    def validate_all(self) -> ValidationReport:
        """Run all validation rules."""
        issues: list[ValidationIssue] = []
        issues.extend(self._check_required_fields())
        issues.extend(self._check_character_fields())
        issues.extend(self._check_event_fields())
        issues.extend(self._check_relation_fields())
        issues.extend(self._check_orphan_entities())
        issues.extend(self._check_scene_fields())
        return ValidationReport(
            passed=len([i for i in issues if i.severity == "error"]) == 0,
            issues=issues,
        )

    def _check_required_fields(self) -> list[ValidationIssue]:
        issues = []
        if not self.gsk.title:
            issues.append(ValidationIssue(
                severity="warning",
                code="MISSING_REQUIRED_FIELD",
                message="SKL missing title",
                entity_type="skl",
            ))
        if not self.gsk.characters:
            issues.append(ValidationIssue(
                severity="error",
                code="MISSING_REQUIRED_FIELD",
                message="SKL has no characters — story cannot proceed",
                entity_type="skl",
            ))
        if not self.gsk.scenes:
            issues.append(ValidationIssue(
                severity="warning",
                code="MISSING_REQUIRED_FIELD",
                message="SKL has no scenes",
                entity_type="skl",
            ))
        return issues

    def _check_character_fields(self) -> list[ValidationIssue]:
        issues = []
        for c in self.gsk.characters:
            name = getattr(c, "name", "")
            if not name or not name.strip():
                issues.append(ValidationIssue(
                    severity="error",
                    code="EMPTY_FIELD",
                    message="Character with empty name",
                    entity_type="character",
                    entity_id=str(id(c)),
                ))
            role = getattr(c, "role", "supporting")
            if role not in self.VALID_CHARACTER_ROLES:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="INVALID_TYPE",
                    message=f"Character '{name}' has invalid role '{role}'",
                    entity_type="character",
                    entity_id=name,
                ))
            desc = getattr(c, "description", "")
            if not desc or not desc.strip():
                issues.append(ValidationIssue(
                    severity="info",
                    code="EMPTY_FIELD",
                    message=f"Character '{name}' has empty description",
                    entity_type="character",
                    entity_id=name,
                ))
        return issues

    def _check_event_fields(self) -> list[ValidationIssue]:
        issues = []
        for e in self.gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            title = e_dict.get("title", "")
            if not title:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="EMPTY_FIELD",
                    message="Event with empty title",
                    entity_type="event",
                    entity_id=str(id(e)),
                ))
            event_type = e_dict.get("event_type", "")
            if event_type and event_type not in self.VALID_EVENT_TYPES:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="INVALID_TYPE",
                    message=f"Event '{title}' has invalid type '{event_type}'",
                    entity_type="event",
                    entity_id=title,
                ))
            participants = e_dict.get("participants", [])
            if participants:
                char_names = {c.name for c in self.gsk.characters}
                for p in participants:
                    if p and p not in char_names:
                        issues.append(ValidationIssue(
                            severity="warning",
                            code="ORPHAN_ENTITY",
                            message=f"Event '{title}' references unknown character '{p}'",
                            entity_type="event",
                            entity_id=title,
                        ))
        return issues

    def _check_relation_fields(self) -> list[ValidationIssue]:
        issues = []
        for r in self.gsk.relations:
            rel_type = getattr(r, "relation_type", "")
            if rel_type and rel_type not in self.VALID_RELATION_TYPES:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="INVALID_TYPE",
                    message=f"Relation '{getattr(r, 'from_char', '')} --{rel_type}--> {getattr(r, 'to_char', '')}' has invalid type",
                    entity_type="relation",
                    entity_id=getattr(r, "from_char", ""),
                ))
            fc, tc = getattr(r, "from_char", ""), getattr(r, "to_char", "")
            if fc == tc:
                issues.append(ValidationIssue(
                    severity="error",
                    code="INVALID_TYPE",
                    message=f"Relation has same source and target: '{fc}'",
                    entity_type="relation",
                    entity_id=fc,
                ))
        return issues

    def _check_orphan_entities(self) -> list[ValidationIssue]:
        """Check for characters/relations/events that are never referenced."""
        issues = []
        # Characters not in any scene or event
        char_names = {c.name for c in self.gsk.characters}
        referenced_chars: set[str] = set()
        for s in self.gsk.scenes:
            for ch in getattr(s, "characters", []):
                if ch:
                    referenced_chars.add(ch)
        for e in self.gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            for p in e_dict.get("participants", []):
                if p:
                    referenced_chars.add(p)

        for name in char_names:
            if name not in referenced_chars:
                issues.append(ValidationIssue(
                    severity="info",
                    code="ORPHAN_ENTITY",
                    message=f"Character '{name}' is not referenced in any scene or event",
                    entity_type="character",
                    entity_id=name,
                ))
        return issues

    def _check_scene_fields(self) -> list[ValidationIssue]:
        issues = []
        for s in self.gsk.scenes:
            title = getattr(s, "title", "")
            if not title or not title.strip():
                issues.append(ValidationIssue(
                    severity="error",
                    code="EMPTY_FIELD",
                    message="Scene with empty title",
                    entity_type="scene",
                    entity_id=str(id(s)),
                ))
            loc = getattr(s, "location", "")
            if not loc or not loc.strip():
                issues.append(ValidationIssue(
                    severity="info",
                    code="EMPTY_FIELD",
                    message=f"Scene '{title}' has empty location",
                    entity_type="scene",
                    entity_id=title,
                ))
        return issues


# ── Knowledge Patch ────────────────────────────────────────────────────────────


@dataclass
class Patch:
    """A user-initiated correction to the SKL."""
    target_type: str     # "character" | "scene" | "event" | "relation"
    target_id: str       # identifier (name for characters, title for scenes/events)
    field: str           # field name to update
    old_value: Any
    new_value: Any
    reason: str = ""
    user: str = "user"


class KnowledgePatch:
    """Handles user corrections with cascading updates to downstream entities."""

    def __init__(self, gsk, audit_trail: AuditTrail):
        self.gsk = gsk
        self.audit_trail = audit_trail

    def apply(self, patch: Patch) -> bool:
        """Apply a user patch to the SKL, returns True if successful."""
        handlers = {
            "character": self._patch_character,
            "scene": self._patch_scene,
            "event": self._patch_event,
            "relation": self._patch_relation,
        }
        handler = handlers.get(patch.target_type)
        if handler is None:
            return False

        success = handler(patch)
        if success:
            self.audit_trail.record(
                action="patch",
                target_type=patch.target_type,
                target_id=patch.target_id,
                before={patch.field: patch.old_value},
                after={patch.field: patch.new_value},
                reason=patch.reason,
                user=patch.user,
            )
            # Cascade updates
            self._cascade_character_rename(patch)
        return success

    def _patch_character(self, patch: Patch) -> bool:
        for c in self.gsk.characters:
            if c.name == patch.target_id:
                if hasattr(c, patch.field):
                    setattr(c, patch.field, patch.new_value)
                    return True
        return False

    def _patch_scene(self, patch: Patch) -> bool:
        for s in self.gsk.scenes:
            if getattr(s, "title", "") == patch.target_id:
                if hasattr(s, patch.field):
                    setattr(s, patch.field, patch.new_value)
                    return True
        return False

    def _patch_event(self, patch: Patch) -> bool:
        for e in self.gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            title = e_dict.get("title", "")
            if title == patch.target_id:
                if isinstance(e, dict):
                    e[patch.field] = patch.new_value
                else:
                    setattr(e, patch.field, patch.new_value)
                return True
        return False

    def _patch_relation(self, patch: Patch) -> bool:
        for r in self.gsk.relations:
            if getattr(r, "from_char", "") == patch.target_id or getattr(r, "to_char", "") == patch.target_id:
                if hasattr(r, patch.field):
                    setattr(r, patch.field, patch.new_value)
                    return True
        return False

    def _cascade_character_rename(self, patch: Patch) -> None:
        """When a character name is changed, update all references."""
        if patch.target_type != "character" or patch.field != "name":
            return
        old_name, new_name = patch.old_value, patch.new_value
        # Update scenes
        for s in self.gsk.scenes:
            chars = getattr(s, "characters", [])
            if old_name in chars:
                idx = chars.index(old_name)
                chars[idx] = new_name
        # Update events
        for e in self.gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            participants = e_dict.get("participants", [])
            if old_name in participants:
                idx = participants.index(old_name)
                participants[idx] = new_name
        # Update relations
        for r in self.gsk.relations:
            if r.from_char == old_name:
                r.from_char = new_name
            if r.to_char == old_name:
                r.to_char = new_name


# ── Knowledge Revision ─────────────────────────────────────────────────────────


class KnowledgeRevision:
    """Automatically corrects inferable errors in the SKL."""

    def __init__(self, gsk, audit_trail: AuditTrail):
        self.gsk = gsk
        self.audit_trail = audit_trail

    def auto_correct(self) -> list[dict]:
        """Run all auto-correction rules. Returns list of corrections applied."""
        corrections = []
        corrections.extend(self._normalize_event_types())
        corrections.extend(self._normalize_relation_types())
        corrections.extend(self._normalize_character_roles())
        return corrections

    def _normalize_event_types(self) -> list[dict]:
        """Normalize event_type values to canonical form."""
        corrections = []
        type_map = {
            "confllict": "conflict",
            "confli ct": "conflict",
            "reveal": "revelation",
            "revelation": "revelation",
            "trans": "transition",
            "turn": "turning_point",
            "turningpoint": "turning_point",
            "resolu": "resolution",
        }
        for e in self.gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            raw_type = e_dict.get("event_type", "")
            normalized = type_map.get(raw_type.strip().lower(), "")
            if normalized and raw_type != normalized:
                title = e_dict.get("title", "")
                before = {"event_type": raw_type}
                if isinstance(e, dict):
                    e["event_type"] = normalized
                else:
                    setattr(e, "event_type", normalized)
                corrections.append({
                    "type": "event_type_normalized",
                    "title": title,
                    "before": raw_type,
                    "after": normalized,
                })
                self.audit_trail.record(
                    action="auto_correct",
                    target_type="event",
                    target_id=title,
                    before=before,
                    after={"event_type": normalized},
                    reason=f"Normalize event_type: {raw_type} → {normalized}",
                )
        return corrections

    def _normalize_relation_types(self) -> list[dict]:
        """Normalize relation_type values."""
        corrections = []
        type_map = {
            "familiy": "family",
            "fam": "family",
            "frnd": "friend",
            "freind": "friend",
            "enmey": "enemy",
            "rom": "romantic",
            "romantic": "romantic",
            "prof": "professional",
            "professional": "professional",
            "stranger": "stranger",
        }
        for r in self.gsk.relations:
            raw_type = getattr(r, "relation_type", "")
            normalized = type_map.get(raw_type.strip().lower(), "")
            if normalized and raw_type != normalized:
                fc = r.from_char
                before = {"relation_type": raw_type}
                r.relation_type = normalized
                corrections.append({
                    "type": "relation_type_normalized",
                    "chars": f"{fc}",
                    "before": raw_type,
                    "after": normalized,
                })
                self.audit_trail.record(
                    action="auto_correct",
                    target_type="relation",
                    target_id=fc,
                    before=before,
                    after={"relation_type": normalized},
                    reason=f"Normalize relation_type: {raw_type} → {normalized}",
                )
        return corrections

    def _normalize_character_roles(self) -> list[dict]:
        """Normalize character role values."""
        corrections = []
        type_map = {
            "prot": "protagonist",
            "protagonist": "protagonist",
            "antag": "antagonist",
            "antagonist": "antagonist",
            "supp": "supporting",
            "support": "supporting",
            "supporting": "supporting",
        }
        for c in self.gsk.characters:
            raw_role = getattr(c, "role", "supporting")
            normalized = type_map.get(raw_role.strip().lower(), "supporting")
            if raw_role != normalized:
                before = {"role": raw_role}
                c.role = normalized
                corrections.append({
                    "type": "role_normalized",
                    "name": c.name,
                    "before": raw_role,
                    "after": normalized,
                })
                self.audit_trail.record(
                    action="auto_correct",
                    target_type="character",
                    target_id=c.name,
                    before=before,
                    after={"role": normalized},
                    reason=f"Normalize role: {raw_role} → {normalized}",
                )
        return corrections


# ── Governance Orchestrator ───────────────────────────────────────────────────


@dataclass
class GovernanceReport:
    """Complete governance report for a SKL."""
    validation: ValidationReport
    conflicts: list[KnowledgeConflict]
    auto_corrections: list[dict]
    patches_applied: int
    audit_trail: AuditTrail

    def summary(self) -> str:
        lines = [
            "=== Knowledge Governance Report ===",
            f"Validation: {'PASSED' if self.validation.passed else 'FAILED'}",
            f"  Issues: {len(self.validation.issues)}",
            f"Conflicts detected: {len(self.conflicts)}",
            f"Auto-corrected: {len(self.auto_corrections)}",
            f"Patches applied: {self.patches_applied}",
            f"Audit entries: {len(self.audit_trail.entries)}",
        ]
        for issue in self.validation.issues:
            lines.append(f"  [{issue.severity}] {issue.code}: {issue.message}")
        for conflict in self.conflicts:
            lines.append(f"  [conflict] {conflict.conflict_type}")
        return "\n".join(lines)


class KnowledgeGovernor:
    """Main entry point for SKL knowledge governance."""

    def __init__(self, gsk, graph=None, llm=None):
        self.gsk = gsk
        self.graph = graph
        self.llm = llm
        self.audit_trail = AuditTrail()
        self.validator = SKLValidator(gsk)
        self.conflict_resolver = ConflictResolver(gsk, self.audit_trail, llm=llm)
        self.patch_handler = KnowledgePatch(gsk, self.audit_trail)
        self.revision = KnowledgeRevision(gsk, self.audit_trail)

    def govern(self, auto_resolve: bool = True) -> GovernanceReport:
        """Run full governance pipeline.

        Steps:
        1. Auto-correct (KnowledgeRevision)
        2. Detect conflicts (ConflictResolver)
        3. Auto-resolve conflicts if enabled
        4. Validate (SKLValidator)
        """
        auto_corrections = self.revision.auto_correct()
        conflicts = self.conflict_resolver.detect_all()
        if auto_resolve:
            unresolved = self.conflict_resolver.auto_resolve()
            conflicts = unresolved

        validation = self.validator.validate_all()
        return GovernanceReport(
            validation=validation,
            conflicts=conflicts,
            auto_corrections=auto_corrections,
            patches_applied=0,
            audit_trail=self.audit_trail,
        )

    def apply_patch(self, patch: Patch) -> bool:
        """Apply a user correction to SKL and optionally propagate to StoryGraph."""
        success = self.patch_handler.apply(patch)
        if success and self.graph is not None:
            if patch.target_type == "character" and patch.field == "name":
                self.graph.apply_character_rename(patch.old_value, patch.new_value)
        return success


def govern_skl(gsk, auto_resolve: bool = True, graph=None, llm=None) -> GovernanceReport:
    """Convenience function: run full governance on a GlobalStoryKnowledge instance."""
    governor = KnowledgeGovernor(gsk, graph=graph, llm=llm)
    return governor.govern(auto_resolve=auto_resolve)
