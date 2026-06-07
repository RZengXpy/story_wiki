"""Incremental Update Module — avoids full pipeline rebuild when only some chapters change.

Detects which chapters have been modified by comparing content hashes, then
only re-runs extraction for changed chapters. Unchanged chapter results are
reused from the cache.

Usage:
    cache = ChapterCache()
    result = workflow.run_incremental(novel_text, cache=cache)
    # Second run with same novel_text will reuse all cached results
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ChapterHash:
    """A single chapter's content fingerprint."""
    chapter_id: str
    content_hash: str
    char_count: int


@dataclass
class ChapterCache:
    """Per-chapter extraction cache — keyed by chapter_id.

    Stores extracted characters, scenes, events, and relations per chapter.
    """
    version: str = "1"
    last_updated: str = ""
    chapter_hashes: list[ChapterHash] = field(default_factory=list)
    # chapter_id -> extracted results (stored as plain dicts to avoid dataclass factory issues)
    characters: dict = field(default_factory=dict)
    scenes: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    relations: dict = field(default_factory=dict)

    def content_hash(self, chapter_id: str) -> Optional[str]:
        for h in self.chapter_hashes:
            if h.chapter_id == chapter_id:
                return h.content_hash
        return None

    def has_cached(self, chapter_id: str) -> bool:
        return chapter_id in self.characters

    def get_changed_chapters(self, chapters: list) -> list:
        """Return chapters whose content hash differs from cache (or not in cache)."""
        changed = []
        for ch in chapters:
            cid = getattr(ch, "id", "")
            cached_hash = self.content_hash(cid)
            if cached_hash is None:
                changed.append(ch)
                continue
            current_hash = _hash_content(getattr(ch, "content", ""))
            if current_hash != cached_hash:
                changed.append(ch)
        return changed

    def update(self, chapter, characters, scenes, events, relations) -> None:
        """Cache extraction results for a single chapter."""
        cid = getattr(chapter, "id", "")
        content = getattr(chapter, "content", "")
        self.characters[cid] = characters
        self.scenes[cid] = scenes
        self.events[cid] = events
        self.relations[cid] = relations

        # Update hash
        new_hash = _hash_content(content)
        found = False
        for h in self.chapter_hashes:
            if h.chapter_id == cid:
                h.content_hash = new_hash
                h.char_count = len(content)
                found = True
                break
        if not found:
            self.chapter_hashes.append(ChapterHash(
                chapter_id=cid,
                content_hash=new_hash,
                char_count=len(content),
            ))

        self.last_updated = datetime.now().isoformat()

    def invalidate(self, chapter_id: str) -> None:
        """Remove a chapter from cache (e.g., after user edit)."""
        self.characters.pop(chapter_id, None)
        self.scenes.pop(chapter_id, None)
        self.events.pop(chapter_id, None)
        self.relations.pop(chapter_id, None)
        self.chapter_hashes = [h for h in self.chapter_hashes if h.chapter_id != chapter_id]

    def clear(self) -> None:
        self.chapter_hashes.clear()
        self.characters.clear()
        self.scenes.clear()
        self.events.clear()
        self.relations.clear()
        self.last_updated = ""

    def summary(self) -> dict:
        return {
            "version": self.version,
            "cached_chapters": len(self.characters),
            "last_updated": self.last_updated,
            "chapter_hashes": [
                {"id": h.chapter_id, "chars": h.char_count}
                for h in self.chapter_hashes
            ],
        }


def _hash_content(content: str) -> str:
    """SHA-256 hash of full chapter content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
