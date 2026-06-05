"""Knowledge Merger — merges local chapter-level knowledge into a global SKL.

Implements the "Local → Global" principle from think.md:
  Chapter → Local Knowledge → Knowledge Merge → Global Knowledge
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from schema.models import Character, Scene, SourceTrace


@dataclass
class LocalKnowledge:
    """Knowledge extracted from a single chapter."""
    chapter_id: str
    chapter_title: str
    characters: list[Character] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)


@dataclass
class GlobalStoryKnowledge:
    """Global Story Knowledge Layer — Single Source of Truth."""
    title: str = ""
    author: str = ""

    # Deduplicated, merged character list
    characters: list[Character] = field(default_factory=list)

    # Deduplicated, merged scene list
    scenes: list[Scene] = field(default_factory=list)

    # Character name → first chapter where they appeared
    character_first_appearance: dict[str, str] = field(default_factory=dict)

    # All source chapters for traceability
    source_chapters: list[dict] = field(default_factory=list)

    # Merge metadata
    total_chapters: int = 0
    duplicates_removed: int = 0

    def get_character(self, name: str) -> Optional[Character]:
        for c in self.characters:
            if c.name == name:
                return c
        return None

    def merge_characters(self, incoming: list[Character]) -> int:
        """Merge character list, deduplicating by name. Returns count of duplicates removed."""
        removed = 0
        for c in incoming:
            existing = self.get_character(c.name)
            if existing is None:
                self.characters.append(c)
            else:
                # Merge traits
                for t in c.traits:
                    if t not in existing.traits:
                        existing.traits.append(t)
                # Merge description (prefer longer one)
                if len(c.description) > len(existing.description):
                    existing.description = c.description
                removed += 1
        return removed

    def merge_scenes(self, incoming: list[Scene]) -> int:
        """Merge scene list, deduplicating by (title, location). Returns count removed."""
        removed = 0
        for s in incoming:
            duplicate = any(
                e.title == s.title and e.location == s.location
                for e in self.scenes
            )
            if not duplicate:
                self.scenes.append(s)
            else:
                removed += 1
        return removed

    def to_dict(self) -> dict:
        def strip_source(obj):
            if hasattr(obj, "__dataclass_fields__"):
                result = {}
                for name, f in obj.__dataclass_fields__.items():
                    val = getattr(obj, name)
                    if isinstance(val, list):
                        result[name] = [strip_source(v) for v in val]
                    elif hasattr(val, "__dataclass_fields__"):
                        result[name] = strip_source(val)
                    else:
                        result[name] = val
                return result
            return obj

        result = {
            "title": self.title,
            "author": self.author,
            "total_chapters": self.total_chapters,
            "duplicates_removed": self.duplicates_removed,
            "character_first_appearance": self.character_first_appearance,
            "source_chapters": self.source_chapters,
        }
        data = strip_source(self)
        result.update(data)
        return result


class KnowledgeMerger:
    """Merges Local Knowledge from each chapter into a Global SKL."""

    def __init__(self, title: str = "", author: str = ""):
        self.gsk = GlobalStoryKnowledge(title=title, author=author)

    def merge_local(self, local: LocalKnowledge) -> GlobalStoryKnowledge:
        """Merge one chapter's local knowledge into the global SKL."""
        self.gsk.source_chapters.append({
            "chapter_id": local.chapter_id,
            "chapter_title": local.chapter_title,
        })

        chars_removed = self.gsk.merge_characters(local.characters)
        scenes_removed = self.gsk.merge_scenes(local.scenes)

        self.gsk.duplicates_removed += chars_removed + scenes_removed

        # Track first appearance
        for c in local.characters:
            name = c.name
            if name not in self.gsk.character_first_appearance:
                src = c.source
                self.gsk.character_first_appearance[name] = (
                    src.chapter_title if src else local.chapter_title
                )

        self.gsk.total_chapters = len(self.gsk.source_chapters)
        return self.gsk

    def merge_all(self, locals: list[LocalKnowledge]) -> GlobalStoryKnowledge:
        """Merge multiple chapters' local knowledge in order."""
        for local in locals:
            self.merge_local(local)
        return self.gsk

    def get_global(self) -> GlobalStoryKnowledge:
        return self.gsk


def merge_chapters_to_skl(
    title: str,
    author: str,
    chapters: list,
    all_characters: list[Character],
    all_scenes: list[Scene],
) -> GlobalStoryKnowledge:
    """Convenience: one-shot merge from chapter-based extraction results."""
    from core.chapter_parser import Chapter

    chapter_map: dict[str, list[Character]] = defaultdict(list)
    chapter_scenes: dict[str, list[Scene]] = defaultdict(list)

    for c in all_characters:
        if c.source:
            chapter_map[c.source.chapter_id].append(c)
        else:
            chapter_map["unknown"].append(c)

    for s in all_scenes:
        if s.source:
            chapter_scenes[s.source.chapter_id].append(s)
        else:
            chapter_scenes["unknown"].append(s)

    all_chapter_ids = {getattr(ch, "id", f"ch_{i+1:03d}"): getattr(ch, "title", "未知")
                       for i, ch in enumerate(chapters)}
    for cid in chapter_map:
        if cid not in all_chapter_ids:
            all_chapter_ids[cid] = cid

    merger = KnowledgeMerger(title=title, author=author)
    locals_list = []
    for i, ch in enumerate(chapters):
        cid = getattr(ch, "id", f"ch_{i+1:03d}")
        ctitle = getattr(ch, "title", all_chapter_ids.get(cid, "未知"))
        locals_list.append(LocalKnowledge(
            chapter_id=cid,
            chapter_title=ctitle,
            characters=chapter_map.get(cid, []),
            scenes=chapter_scenes.get(cid, []),
        ))

    # Handle characters/scenes without source (fallback to chapter 1)
    for cid, chars in chapter_map.items():
        if cid == "unknown":
            for c in chars:
                locals_list[0].characters.append(c) if locals_list else None
    for cid, scenes in chapter_scenes.items():
        if cid == "unknown":
            for s in scenes:
                if locals_list:
                    locals_list[0].scenes.append(s)

    return merger.merge_all(locals_list)
