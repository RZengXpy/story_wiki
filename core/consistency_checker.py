"""Consistency Checker — cross-chapter and intra-chapter consistency validation.

Implements the "Consistency By Design" and "Retrieval Before Generation" principles.
Not a post-processing step — it's an architectural goal built into the workflow.
"""
from dataclasses import dataclass, field
from typing import Optional

from core.story_graph import (
    StoryGraph,
    WarningNode,
    WarningCode,
    WarningSeverity,
)


@dataclass
class ConsistencyReport:
    passed: bool
    warnings: list[WarningNode] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.passed and not self.warnings:
            return "All checks passed."
        lines = [f"{len(self.warnings)} warning(s) found:"]
        for w in self.warnings:
            lines.append(f"  [{w.severity.value.upper()}] {w.code.value}: {w.message}")
        return "\n".join(lines)


class ConsistencyChecker:
    """Validates consistency across characters, scenes, events, and relationships."""

    def __init__(self, graph: StoryGraph):
        self.graph = graph

    def check_all(self) -> ConsistencyReport:
        warnings: list[WarningNode] = []
        info: list[str] = []

        warnings.extend(self._check_characters())
        warnings.extend(self._check_scene_character_consistency())
        warnings.extend(self._check_event_characters())
        warnings.extend(self._check_timeline())

        return ConsistencyReport(
            passed=len([w for w in warnings if w.severity == WarningSeverity.ERROR]) == 0,
            warnings=warnings,
            info=info,
        )

    def _check_characters(self) -> list[WarningNode]:
        """Check for duplicate characters, role conflicts."""
        warnings: list[WarningNode] = []
        seen_names: dict[str, int] = {}
        for i, char in enumerate(self.graph.characters):
            if char.name in seen_names:
                warnings.append(WarningNode(
                    code=WarningCode.CHARACTER_DISCREPANCY,
                    message=f"角色「{char.name}」在章节间出现多次（角色去重可能未生效）",
                    severity=WarningSeverity.WARNING,
                    scene_ids=[],
                    characters_involved=[char.name],
                ))
            else:
                seen_names[char.name] = i
        return warnings

    def _check_scene_character_consistency(self) -> list[WarningNode]:
        """Verify every character referenced in a scene exists in the character list."""
        warnings: list[WarningNode] = []
        char_names = {c.name for c in self.graph.characters}
        for scene in self.graph.scenes:
            for ch in scene.characters_present:
                if ch and ch not in char_names and len(ch.strip()) > 0:
                    warnings.append(WarningNode(
                        code=WarningCode.CHARACTER_DISCREPANCY,
                        message=f"场景「{scene.title}」引用了未识别角色：{ch}",
                        severity=WarningSeverity.WARNING,
                        scene_ids=[scene.id],
                        characters_involved=[ch],
                    ))
        return warnings

    def _check_event_characters(self) -> list[WarningNode]:
        """Verify event participants exist in character list."""
        warnings: list[WarningNode] = []
        char_names = {c.name for c in self.graph.characters}
        for evt in self.graph.events:
            for p in evt.participants:
                if p and p not in char_names:
                    warnings.append(WarningNode(
                        code=WarningCode.EVENT_CONTRADICTION,
                        message=f"事件「{evt.title}」涉及未知角色：{p}",
                        severity=WarningSeverity.INFO,
                        scene_ids=[],
                        characters_involved=[p],
                    ))
        return warnings

    def _check_timeline(self) -> list[WarningNode]:
        """Check for timeline anomalies (time marker conflicts within same location)."""
        warnings: list[WarningNode] = []
        location_times: dict[str, list[tuple[str, str]]] = {}
        for evt in self.graph.events:
            if evt.location and evt.time_marker:
                location_times.setdefault(evt.location, []).append(
                    (evt.title, evt.time_marker)
                )
        for loc, events in location_times.items():
            if len(events) > 3:
                unique_times = {t for _, t in events}
                if len(unique_times) == len(events):
                    warnings.append(WarningNode(
                        code=WarningCode.TIMELINE_CONFLICT,
                        message=f"地点「{loc}」的事件时间标记各不相同，建议检查是否存在时间矛盾",
                        severity=WarningSeverity.INFO,
                        scene_ids=[],
                        characters_involved=[],
                    ))
        return warnings


def run_consistency_check(graph: StoryGraph) -> ConsistencyReport:
    checker = ConsistencyChecker(graph)
    return checker.check_all()
