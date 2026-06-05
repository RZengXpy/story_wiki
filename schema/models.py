from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceTrace:
    chapter_id: str
    chapter_title: str
    char_range: tuple[int, int] = (0, 0)


@dataclass
class Relation:
    from_char: str
    to_char: str
    relation_type: str  # "family" | "friend" | "enemy" | "romantic" | "professional" | "stranger"
    description: str = ""
    source: Optional[SourceTrace] = None


@dataclass
class Character:
    name: str
    description: str
    traits: list[str] = field(default_factory=list)
    role: str = "supporting"  # "protagonist" | "antagonist" | "supporting"
    source: Optional[SourceTrace] = None


@dataclass
class Scene:
    title: str
    location: str
    time_of_day: str  # "day" | "night" | "dawn" | "dusk"
    description: str
    characters: list[str] = field(default_factory=list)
    dialogue: list[dict] = field(default_factory=list)
    notes: str = ""
    source: Optional[SourceTrace] = None

    def add_dialogue(self, speaker: str, text: str):
        self.dialogue.append({"speaker": speaker, "text": text})


@dataclass
class Act:
    title: str
    scenes: list[Scene] = field(default_factory=list)

    def add_scene(self, scene: Scene):
        self.scenes.append(scene)


@dataclass
class Script:
    title: str
    author: str
    genre: str
    acts: list[Act] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_act(self, act: Act):
        self.acts.append(act)


@dataclass
class StoryConfig:
    novel_text: str
    genre: str = "general"
    target_length: str = "medium"  # "short" | "medium" | "feature"
    style: str = "cinematic"
    custom_prompt: str = ""
