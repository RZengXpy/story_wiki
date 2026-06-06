"""StoryGraph data model — 小说知识图谱表示."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CharacterRole(Enum):
    PROTAGONIST = "protagonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"


class EventType(Enum):
    CONFLICT = "conflict"
    REVELATION = "revelation"
    TRANSITION = "transition"
    TURNING_POINT = "turning_point"
    RESOLUTION = "resolution"


class WarningSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class WarningCode(Enum):
    CHARACTER_DISCREPANCY = "CHARACTER_DISCREPANCY"
    SCENE_INCONSISTENCY = "SCENE_INCONSISTENCY"
    EVENT_CONTRADICTION = "EVENT_CONTRADICTION"
    RELATION_MISSING = "RELATION_MISSING"
    UNRESOLVED_PLOT = "UNRESOLVED_PLOT"
    TIMELINE_CONFLICT = "TIMELINE_CONFLICT"


@dataclass
class CharacterNode:
    id: str
    name: str
    role: CharacterRole = CharacterRole.SUPPORTING
    age: str = ""
    gender: str = ""
    description: str = ""
    first_appearance: str = ""


@dataclass
class RelationNode:
    from_char: str
    to_char: str
    relation_type: str
    description: str = ""


@dataclass
class EventNode:
    title: str
    event_type: EventType
    location: str = ""
    time_marker: str = ""
    participants: list[str] = field(default_factory=list)
    description: str = ""
    cause: str = ""
    consequence: str = ""


@dataclass
class SceneNode:
    id: str
    title: str
    location: str = ""
    time: str = ""
    act: int = 1
    characters_present: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ScriptItem:
    type: str  # "action" | "dialogue"
    text: str
    character: str = ""


@dataclass
class ScriptNode:
    id: str
    content: list[ScriptItem] = field(default_factory=list)


@dataclass
class WarningNode:
    code: WarningCode
    message: str
    severity: WarningSeverity
    scene_ids: list[str] = field(default_factory=list)
    characters_involved: list[str] = field(default_factory=list)


@dataclass
class StoryGraph:
    version: str = "1.0"
    metadata: dict = field(default_factory=dict)
    characters: list[CharacterNode] = field(default_factory=list)
    relations: list[RelationNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)
    scenes: list[SceneNode] = field(default_factory=list)
    scripts: dict = field(default_factory=dict)  # scene_id -> ScriptNode
    warnings: list[WarningNode] = field(default_factory=list)

    def to_yaml(self) -> str:
        import yaml

        def enum_safe(obj):
            if hasattr(obj, "value"):
                return obj.value
            if hasattr(obj, "__dataclass_fields__"):
                return {k: enum_safe(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [enum_safe(i) for i in obj]
            if isinstance(obj, dict):
                return {k: enum_safe(v) for k, v in obj.items()}
            return obj

        data = enum_safe({
            "version": self.version,
            "metadata": self.metadata,
            "characters": self.characters,
            "relations": self.relations,
            "events": self.events,
            "scenes": self.scenes,
            "scripts": self.scripts,
            "warnings": self.warnings,
        })
        return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def apply_character_rename(self, old_name: str, new_name: str) -> int:
        """Rename a character across all entities in the graph. Returns count of changes made."""
        changed = 0

        # Character nodes
        for cn in self.characters:
            if cn.id == old_name or cn.name == old_name:
                cn.name = new_name
                cn.id = new_name
                changed += 1

        # Scene characters_present
        for sn in self.scenes:
            if old_name in sn.characters_present:
                idx = sn.characters_present.index(old_name)
                sn.characters_present[idx] = new_name
                changed += 1

        # Event participants
        for en in self.events:
            if old_name in en.participants:
                idx = en.participants.index(old_name)
                en.participants[idx] = new_name
                changed += 1

        # Relations
        for rn in self.relations:
            if rn.from_char == old_name:
                rn.from_char = new_name
                changed += 1
            if rn.to_char == old_name:
                rn.to_char = new_name
                changed += 1

        # Scripts: character field and text content
        for script_node in self.scripts.values():
            for item in script_node.content:
                if item.character == old_name:
                    item.character = new_name
                    changed += 1
                # Replace character name in text (word-boundary aware)
                if old_name in item.text:
                    item.text = item.text.replace(old_name, new_name)
                    changed += 1

        return changed
