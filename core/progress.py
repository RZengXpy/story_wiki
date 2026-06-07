"""Progress tracking for StoryForge workflow — allows real-time progress display in Streamlit.

Usage:
    from core.progress import ProgressTracker

    tracker = ProgressTracker()
    tracker.set_total(3, 10)           # 3 chapters, 10 total LLM calls
    tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)
    tracker.on_chapter_done(1, "第一章：失踪的航海日志")

    # In Streamlit:
    my_bar = st.progress(0)
    for p in tracker.stream():
        my_bar.progress(p.value / p.total, text=p.message)

Note on LLM call counts (think.md Principle III — Unified Extraction):
    - Per-chapter unified extraction: 1 call × n_chapters (not 4)
    - Outline generation: 1 call
    - Script generation: 1 call × n_scenes
    - Total SKL: n + 1;  Total with scripts: n + 1 + n_scenes
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from threading import Lock


class Phase(Enum):
    IDLE = "idle"
    PARSING_CHAPTERS = "parsing_chapters"
    EXTRACTING_KNOWLEDGE = "extracting_knowledge"
    MERGING_KNOWLEDGE = "merging_knowledge"
    GOVERNANCE = "governance"
    CHECKING_CONSISTENCY = "checking_consistency"
    BUILDING_GRAPH = "building_graph"
    GENERATING_SCRIPTS = "generating_scripts"
    DONE = "done"
    ERROR = "error"


@dataclass
class StepProgress:
    """A single progress step snapshot."""
    phase: Phase
    phase_label: str
    message: str
    current: int
    total: int
    chapter_info: str = ""

    @property
    def value(self) -> int:
        return self.current

    @property
    def fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.current / self.total


class ProgressTracker:
    """Thread-safe progress tracker with incremental step support.

    Estimates total LLM calls (think.md Principle III — Unified Extraction):
        - Per-chapter unified extraction: 1 call × n_chapters
        - Outline generation: 1 call
        - Script generation: n_scenes calls
        - Total SKL: n + 1;  Total with scripts: n + 1 + n_scenes
    """

    # Rough weight: 1 LLM call = 1 step unit
    PHASE_WEIGHTS = {
        Phase.PARSING_CHAPTERS: 0,
        Phase.EXTRACTING_KNOWLEDGE: 1,   # 1 unified call per chapter
        Phase.MERGING_KNOWLEDGE: 0,
        Phase.GOVERNANCE: 0,
        Phase.CHECKING_CONSISTENCY: 0,
        Phase.BUILDING_GRAPH: 0,
        Phase.GENERATING_SCRIPTS: 1,     # 1 agent, 1 call per scene
    }

    PHASE_LABELS = {
        Phase.IDLE: "空闲",
        Phase.PARSING_CHAPTERS: "解析章节",
        Phase.EXTRACTING_KNOWLEDGE: "提取知识",
        Phase.MERGING_KNOWLEDGE: "合并知识图谱",
        Phase.GOVERNANCE: "知识治理",
        Phase.CHECKING_CONSISTENCY: "一致性检查",
        Phase.BUILDING_GRAPH: "构建图谱",
        Phase.GENERATING_SCRIPTS: "生成剧本",
        Phase.DONE: "完成",
        Phase.ERROR: "出错",
    }

    def __init__(self):
        self._lock = Lock()
        self._phase = Phase.IDLE
        self._chapter_total = 0
        self._chapter_done = 0
        self._current_agent: str = ""
        self._llm_total = 0
        self._llm_done = 0
        self._scene_total = 0
        self._scene_done = 0
        self._error_message = ""

    def set_total(self, n_chapters: int, n_scenes: int = 0) -> None:
        with self._lock:
            self._chapter_total = n_chapters
            self._scene_total = n_scenes
            # LLM total: 1 unified call per chapter + 1 outline + n_scenes scripts
            # (Principle III: one LLM call per chapter, not 4)
            self._llm_total = 1 * n_chapters + 1 + n_scenes

    def set_phase(self, phase: Phase) -> None:
        with self._lock:
            self._phase = phase
            self._llm_done = 0

    def on_chapter_start(self, chapter_idx: int, chapter_title: str) -> None:
        with self._lock:
            self._chapter_done = chapter_idx
            self._current_agent = ""

    def on_chapter_done(self, chapter_idx: int, chapter_title: str) -> None:
        """Mark a chapter as fully processed (unified extraction done)."""
        with self._lock:
            self._chapter_done = chapter_idx

    def on_agent_done(self, agent_name: str, chapter_idx: int, chapter_title: str) -> None:
        with self._lock:
            self._llm_done += 1
            self._current_agent = agent_name

    def on_outline_done(self) -> None:
        with self._lock:
            self._llm_done += 1

    def on_scene_start(self, scene_idx: int, scene_title: str) -> None:
        with self._lock:
            self._scene_done = scene_idx

    def on_scene_done(self, scene_idx: int, scene_title: str) -> None:
        with self._lock:
            self._llm_done += 1

    def on_merge_done(self) -> None:
        with self._lock:
            pass

    def on_error(self, msg: str) -> None:
        with self._lock:
            self._phase = Phase.ERROR
            self._error_message = msg

    def get_progress(self) -> StepProgress:
        with self._lock:
            phase = self._phase
            label = self.PHASE_LABELS.get(phase, str(phase.value))

            if phase == Phase.EXTRACTING_KNOWLEDGE:
                msg = f"正在提取：{self._current_agent}" if self._current_agent else "正在提取章节知识..."
                total = self._llm_total
                current = self._llm_done
                chapter_info = f"第 {self._chapter_done + 1} 章 / 共 {self._chapter_total} 章"
            elif phase == Phase.GENERATING_SCRIPTS:
                msg = f"正在生成场景剧本..."
                total = self._scene_total
                current = self._scene_done
                chapter_info = f"场景 {self._scene_done} / 共 {self._scene_total}"
            elif phase == Phase.DONE:
                msg = "处理完成！"
                total = 1
                current = 1
                chapter_info = ""
            elif phase == Phase.ERROR:
                msg = f"错误：{self._error_message}"
                total = 1
                current = 0
                chapter_info = ""
            elif phase == Phase.MERGING_KNOWLEDGE:
                msg = "正在合并章节知识，构建全局知识图谱..."
                total = 1
                current = 0
                chapter_info = f"已处理 {self._chapter_total} 章"
            elif phase == Phase.GOVERNANCE:
                msg = "正在进行知识治理与冲突检测..."
                total = 1
                current = 0
                chapter_info = ""
            elif phase == Phase.CHECKING_CONSISTENCY:
                msg = "正在进行一致性检查..."
                total = 1
                current = 0
                chapter_info = ""
            elif phase == Phase.BUILDING_GRAPH:
                msg = "正在构建 StoryGraph..."
                total = 1
                current = 0
                chapter_info = ""
            elif phase == Phase.PARSING_CHAPTERS:
                msg = "正在解析章节结构..."
                total = 1
                current = 0
                chapter_info = ""
            else:
                msg = "等待中..."
                total = 1
                current = 0
                chapter_info = ""

            return StepProgress(
                phase=phase,
                phase_label=label,
                message=msg,
                current=current,
                total=total,
                chapter_info=chapter_info,
            )

    def get_llm_progress(self) -> tuple[int, int]:
        """Return (llm_done, llm_total) for quick access."""
        with self._lock:
            return self._llm_done, self._llm_total

    @property
    def current_phase(self) -> Phase:
        with self._lock:
            return self._phase
