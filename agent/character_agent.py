"""Character Agent — character knowledge governance.

Implements think.md Principle IV: "Agent 负责治理而非抽取"
All governance methods operate on the pre-built SKL (no extraction).

Governance capabilities:
  - deduplicate: remove duplicate characters by name
  - merge_aliases: merge same-person characters with different names
  - identify_protagonist: find the main character by appearance frequency
  - assign_roles: auto-assign protagonist/antagonist/supporting roles
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from schema.models import Character

if TYPE_CHECKING:
    from core.knowledge_merger import GlobalStoryKnowledge


class CharacterAgent:
    """Character governance agent — operates on SKL, not raw text."""

    def __init__(self, llm_client=None):
        pass  # Governance methods don't need LLM

    # ── Governance (think.md Principle IV) ────────────────────────────────

    def deduplicate(self, gsk: "GlobalStoryKnowledge") -> list[dict]:
        """Remove duplicate characters by name. Returns audit records."""
        audit = []
        seen_names: dict[str, int] = {}
        to_remove: list[int] = []

        for idx, char in enumerate(gsk.characters):
            name = char.name.strip()
            if name in seen_names:
                # Duplicate found
                existing_idx = seen_names[name]
                existing = gsk.characters[existing_idx]
                # Merge traits
                for trait in char.traits:
                    if trait not in existing.traits:
                        existing.traits.append(trait)
                # Keep longer description
                if len(char.description) > len(existing.description):
                    existing.description = char.description
                audit.append({
                    "action": "deduplicate",
                    "name": name,
                    "kept": existing_idx,
                    "removed": idx,
                    "reason": "Duplicate character name",
                })
                to_remove.append(idx)
            else:
                seen_names[name] = idx

        # Remove in reverse order to preserve indices
        for idx in reversed(to_remove):
            gsk.characters.pop(idx)
        return audit

    def merge_aliases(self, gsk: "GlobalStoryKnowledge") -> list[dict]:
        """Merge characters that are the same person with different names (aliases).

        Uses simple heuristics:
        - Exact name match (case-insensitive)
        - Name contained within other name (e.g. "林远" vs "林远（真名）")
        """
        audit = []
        i = 0
        while i < len(gsk.characters):
            char_a = gsk.characters[i]
            j = i + 1
            merged_any = False
            while j < len(gsk.characters):
                char_b = gsk.characters[j]
                if self._is_alias(char_a.name, char_b.name):
                    # Merge B into A
                    for trait in char_b.traits:
                        if trait not in char_a.traits:
                            char_a.traits.append(trait)
                    if len(char_b.description) > len(char_a.description):
                        char_a.description = char_b.description
                    audit.append({
                        "action": "merge_alias",
                        "primary": char_a.name,
                        "merged": char_b.name,
                    })
                    gsk.characters.pop(j)
                    merged_any = True
                else:
                    j += 1
            i += 1
        return audit

    def _is_alias(self, name_a: str, name_b: str) -> bool:
        """Check if two names refer to the same person."""
        if not name_a or not name_b:
            return False
        a, b = name_a.strip(), name_b.strip()
        if a == b:
            return True
        # One name contains the other
        if a in b or b in a:
            return True
        # Case-insensitive match
        if a.lower() == b.lower():
            return True
        return False

    def identify_protagonist(self, gsk: "GlobalStoryKnowledge") -> Optional[Character]:
        """Identify the protagonist based on:
        1. Explicit role annotation
        2. Frequency of appearance (first_appearance tracking)
        """
        # Priority 1: explicitly labeled protagonist
        for char in gsk.characters:
            if char.role == "protagonist":
                return char

        # Priority 2: character who appears first and has most events
        if not gsk.character_first_appearance:
            return None

        # Find character with earliest first appearance
        first_appearances = {}
        for name, ch_title in gsk.character_first_appearance.items():
            if ch_title:
                first_appearances[name] = ch_title

        if not first_appearances:
            return None

        # Count events per character
        event_counts: Counter = Counter()
        for e in gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            for p in e_dict.get("participants", []):
                event_counts[p] += 1

        # Score by event count + first appearance
        best_score = -1
        best_char: Optional[Character] = None
        for char in gsk.characters:
            score = event_counts.get(char.name, 0)
            if score > best_score:
                best_score = score
                best_char = char

        return best_char

    def assign_roles(self, gsk: "GlobalStoryKnowledge") -> list[dict]:
        """Auto-assign or correct character roles based on narrative importance.

        Governance rule:
        - Protagonist: character with most event participations + earliest first appearance
        - Antagonist: character with most "conflict" event participations
        - Supporting: all others
        """
        audit = []
        if not gsk.events:
            return audit

        # Count event participations by type
        all_events_count: Counter = Counter()
        conflict_count: Counter = Counter()

        for e in gsk.events:
            e_dict = e if isinstance(e, dict) else {}
            e_type = e_dict.get("event_type", "")
            for p in e_dict.get("participants", []):
                all_events_count[p] += 1
                if e_type == "conflict":
                    conflict_count[p] += 1

        # Score each character
        scored: list[tuple[int, int, Character]] = []
        for char in gsk.characters:
            total = all_events_count.get(char.name, 0)
            conflicts = conflict_count.get(char.name, 0)
            scored.append((total, conflicts, char))

        if not scored:
            return audit

        # Sort by total participation (descending)
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        protagonist_name = scored[0][2].name if scored else None

        # Antagonist: highest conflict count (excluding protagonist)
        antagonist_scores = [(c[1], c[0], c[2]) for c in scored if c[2].name != protagonist_name]
        antagonist_scores.sort(reverse=True)
        antagonist_name = antagonist_scores[0][2].name if antagonist_scores else None

        # Assign roles
        for total, conflicts, char in scored:
            old_role = char.role
            if char.name == protagonist_name:
                new_role = "protagonist"
            elif char.name == antagonist_name:
                new_role = "antagonist"
            else:
                new_role = "supporting"

            if old_role != new_role:
                char.role = new_role
                audit.append({
                    "action": "assign_role",
                    "name": char.name,
                    "old_role": old_role,
                    "new_role": new_role,
                    "event_count": total,
                    "conflict_count": conflicts,
                })

        return audit
