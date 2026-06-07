"""Story Storage — JSON-file-based persistence for all pipeline intermediate documents.

Directory layout per story:
    data/
      {story_id}/
        meta.json                       ← title, author, created_at, novel_hash
        chapters.json                   ← 阶段2：章节列表
        local_knowledge/                ← 阶段3+4：每章抽取的知识
          ch_001.json
          ch_002.json
          ...
        skl.json                       ← 阶段5：GlobalStoryKnowledge
        governance.json                 ← 阶段6：治理报告
        graph.json                      ← 阶段7+8：StoryGraph
        graph.yaml                     ← YAML 导出
        pipeline_log.json               ← 各阶段统计

Anti-overwrite strategy:
    Each upload generates a fresh UUID story_id directory.
    Historical versions are NEVER overwritten — they are immutable.
    Only graph.json/graph.yaml can be re-exported from the same skl.json.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import is_dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from enum import Enum

from core.story_graph import (
    StoryGraph,
    CharacterNode,
    RelationNode,
    EventNode,
    SceneNode,
    ScriptNode,
    ScriptItem,
    WarningNode,
    CharacterRole,
    EventType,
    WarningCode,
    WarningSeverity,
)
from core.workflow import WorkflowResult
from core.consistency_checker import ConsistencyReport


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ── JSON Encoder ──────────────────────────────────────────────────────────────

def _is_dataclass_or_enum(obj: Any) -> bool:
    return is_dataclass(obj) or hasattr(obj, "value")


def _to_serializable(obj: Any) -> Any:
    """Recursively convert dataclass/enum objects to plain dicts/lists for JSON."""
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _to_serializable(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(i) for i in obj]
    return obj


def _dataclass_to_dict(obj: Any) -> dict:
    """Convert a dataclass/enum object to a plain dict suitable for JSON dump."""
    return json.loads(json.dumps(_to_serializable(obj), ensure_ascii=False))


# ── Hash helper ───────────────────────────────────────────────────────────────

def _novel_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Story metadata ─────────────────────────────────────────────────────────────

def _story_meta_from_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Core Storage ──────────────────────────────────────────────────────────────

class StoryStorage:
    """Read/write all pipeline intermediate documents as JSON files."""

    def __init__(self, data_dir: Path | str = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.last_saved_story_id: str = ""

    # ── Story lifecycle ──────────────────────────────────────────────────────

    def create_story(self, title: str = "", author: str = "", novel_text: str = "") -> str:
        """Create a new story directory and return its story_id (UUID)."""
        story_id = str(uuid.uuid4())
        story_dir = self.data_dir / story_id
        story_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "story_id": story_id,
            "title": title,
            "author": author,
            "novel_hash": _novel_hash(novel_text),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "pipeline_version": "1.0",
        }
        self._write_json(story_dir / "meta.json", meta)
        return story_id

    def list_stories(self) -> list[dict]:
        """Return metadata for all stories, newest first."""
        stories = []
        for story_dir in self.data_dir.iterdir():
            if not story_dir.is_dir():
                continue
            meta_path = story_dir / "meta.json"
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    stories.append(json.load(f))
        stories.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return stories

    def get_story_dir(self, story_id: str) -> Path:
        return self.data_dir / story_id

    def story_exists(self, story_id: str) -> bool:
        return (self.data_dir / story_id / "meta.json").exists()

    # ── Phase 2: Chapters ────────────────────────────────────────────────────

    def save_chapters(self, story_id: str, chapters: list) -> None:
        """Persist parsed chapters list (list of Chapter dataclass)."""
        story_dir = self.get_story_dir(story_id)
        chapters_data = [_dataclass_to_dict(ch) for ch in chapters]
        self._write_json(story_dir / "chapters.json", {
            "story_id": story_id,
            "saved_at": datetime.now().isoformat(),
            "chapters": chapters_data,
        })

    def load_chapters(self, story_id: str) -> list[dict]:
        """Return list of chapter dicts."""
        path = self.get_story_dir(story_id) / "chapters.json"
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("chapters", [])

    # ── Phase 3+4: Local Knowledge ────────────────────────────────────────────

    def save_local_knowledge(
        self,
        story_id: str,
        chapter_id: str,
        chapter_title: str,
        characters: list,
        scenes: list,
        events: list,
        relations: list,
    ) -> None:
        """Persist extracted knowledge for a single chapter."""
        story_dir = self.get_story_dir(story_id)
        lk_dir = story_dir / "local_knowledge"
        lk_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "story_id": story_id,
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "saved_at": datetime.now().isoformat(),
            "characters": _dataclass_to_dict(characters),
            "scenes": _dataclass_to_dict(scenes),
            "events": _dataclass_to_dict(events),
            "relations": _dataclass_to_dict(relations),
        }
        self._write_json(lk_dir / f"{chapter_id}.json", data)

    def load_local_knowledge(self, story_id: str, chapter_id: str) -> dict:
        """Load extracted knowledge for a specific chapter."""
        path = self.get_story_dir(story_id) / "local_knowledge" / f"{chapter_id}.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def load_all_local_knowledge(self, story_id: str) -> list[dict]:
        """Load all chapter local knowledge for a story."""
        lk_dir = self.get_story_dir(story_id) / "local_knowledge"
        if not lk_dir.exists():
            return []
        results = []
        for path in sorted(lk_dir.iterdir()):
            if path.suffix == ".json":
                with open(path, encoding="utf-8") as f:
                    results.append(json.load(f))
        return results

    # ── Phase 5: GlobalStoryKnowledge (SKL) ─────────────────────────────────

    def save_skl(self, story_id: str, gsk) -> None:
        """Persist GlobalStoryKnowledge object as JSON."""
        story_dir = self.get_story_dir(story_id)
        data = _dataclass_to_dict(gsk)
        self._write_json(story_dir / "skl.json", {
            "story_id": story_id,
            "saved_at": datetime.now().isoformat(),
            "skl": data,
        })

    def load_skl(self, story_id: str) -> dict:
        """Load SKL as a plain dict (reconstruction to dataclass is caller responsibility)."""
        path = self.get_story_dir(story_id) / "skl.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("skl", {})

    # ── Phase 6: Governance Report ───────────────────────────────────────────

    def save_governance_report(self, story_id: str, report) -> None:
        """Persist GovernanceReport as JSON."""
        story_dir = self.get_story_dir(story_id)
        data = _dataclass_to_dict(report)
        self._write_json(story_dir / "governance.json", {
            "story_id": story_id,
            "saved_at": datetime.now().isoformat(),
            "report": data,
        })

    def load_governance_report(self, story_id: str) -> dict:
        """Load governance report as a plain dict."""
        path = self.get_story_dir(story_id) / "governance.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("report", {})

    # ── Phase 7+8: StoryGraph ────────────────────────────────────────────────

    def save_graph(self, story_id: str, graph: StoryGraph) -> None:
        """Persist StoryGraph as JSON + YAML."""
        story_dir = self.get_story_dir(story_id)

        graph_data = _dataclass_to_dict(graph)
        self._write_json(story_dir / "graph.json", {
            "story_id": story_id,
            "saved_at": datetime.now().isoformat(),
            "graph": graph_data,
        })

        yaml_content = graph.to_yaml()
        (story_dir / "graph.yaml").write_text(yaml_content, encoding="utf-8")

    def load_graph(self, story_id: str) -> dict:
        """Load StoryGraph as a plain dict (reconstruction to dataclass is caller responsibility)."""
        path = self.get_story_dir(story_id) / "graph.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("graph", {})

    def load_graph_yaml(self, story_id: str) -> str:
        """Load the YAML export of a story."""
        path = self.get_story_dir(story_id) / "graph.yaml"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ── Phase log ────────────────────────────────────────────────────────────

    def save_pipeline_log(self, story_id: str, log: dict) -> None:
        """Persist pipeline statistics/log."""
        story_dir = self.get_story_dir(story_id)
        self._write_json(story_dir / "pipeline_log.json", {
            "story_id": story_id,
            "saved_at": datetime.now().isoformat(),
            "log": log,
        })

    def load_pipeline_log(self, story_id: str) -> dict:
        """Load pipeline log."""
        path = self.get_story_dir(story_id) / "pipeline_log.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("log", {})

    # ── Convenience: save full WorkflowResult in one call ───────────────────

    def save_result(self, result: WorkflowResult, novel_text: str = "") -> str:
        """Save everything from a WorkflowResult to a new story directory.

        Returns the new story_id.
        """
        title = result.graph.metadata.get("title", "") if result.graph else ""
        author = result.graph.metadata.get("author", "") if result.graph else ""
        story_id = self.create_story(title, author, novel_text)

        # Phase 2
        if result.chapters:
            self.save_chapters(story_id, result.chapters)

        # Phase 3+4: per-chapter local knowledge
        # Agents return flat lists; group by source.chapter_id
        step_results = result.step_results or {}
        by_chapter = {ch.id: {"characters": [], "scenes": [], "events": [], "relations": []}
                      for ch in result.chapters}

        for lst, key in [
            (step_results.get("characters", []), "characters"),
            (step_results.get("scenes", []), "scenes"),
            (step_results.get("events", []), "events"),
            (step_results.get("relations", []), "relations"),
        ]:
            for item in lst:
                src = getattr(item, "source", None)
                if src and hasattr(src, "chapter_id") and src.chapter_id in by_chapter:
                    by_chapter[src.chapter_id][key].append(item)

        for ch in result.chapters:
            cid = getattr(ch, "id", "")
            if cid in by_chapter:
                self.save_local_knowledge(
                    story_id=story_id,
                    chapter_id=cid,
                    chapter_title=getattr(ch, "title", ""),
                    characters=by_chapter[cid]["characters"],
                    scenes=by_chapter[cid]["scenes"],
                    events=by_chapter[cid]["events"],
                    relations=by_chapter[cid]["relations"],
                )

        # Phase 5
        if result.global_skl:
            self.save_skl(story_id, result.global_skl)

        # Phase 6
        if result.governance_report:
            self.save_governance_report(story_id, result.governance_report)

        # Phase 7+8
        if result.graph:
            self.save_graph(story_id, result.graph)

        # Pipeline log
        self.save_pipeline_log(story_id, result.merger_report or {})

        # Update meta updated_at
        meta_path = self.get_story_dir(story_id) / "meta.json"
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["updated_at"] = datetime.now().isoformat()
        if result.graph:
            meta["stats"] = {
                "characters": len(result.graph.characters),
                "scenes": len(result.graph.scenes),
                "events": len(result.graph.events),
                "relations": len(result.graph.relations),
                "warnings": len(result.graph.warnings),
            }
        self._write_json(meta_path, meta)
        self.last_saved_story_id = story_id

        return story_id

    # ── Load helpers (return plain dicts) ────────────────────────────────────

    def load_story_summary(self, story_id: str) -> dict:
        """Load the meta + pipeline_log + graph metadata in one call."""
        meta_path = self.get_story_dir(story_id) / "meta.json"
        log = self.load_pipeline_log(story_id)
        graph_data = self.load_graph(story_id)
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return {
            **meta,
            "pipeline_log": log,
            "graph_metadata": graph_data.get("metadata", {}),
        }

    def delete_story(self, story_id: str) -> bool:
        """Delete a story directory. Returns True if deleted."""
        import shutil
        story_dir = self.get_story_dir(story_id)
        if story_dir.exists():
            shutil.rmtree(story_dir)
            return True
        return False

    # ── Internal ─────────────────────────────────────────────────────────────

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
