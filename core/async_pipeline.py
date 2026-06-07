"""Async Pipeline — concurrent chapter-level knowledge extraction.

Implements think.md Principles III and V:
  - Principle III: "Unified Knowledge Extraction" — ONE LLM call per chapter
  - Principle V:  "Local → Global" — parallel chapter extraction, then merge

Uses asyncio.to_thread() to run synchronous LLM calls in parallel across chapters.
Each chapter still uses a SINGLE unified LLM call via UnifiedExtractionAgent.

This gives O(n_chapters) LLM-call parallelism (extract all chapters concurrently)
while keeping 1 LLM call per chapter cost (not 4 calls per chapter).

Usage:
    from core.async_pipeline import extract_all_parallel_unified

    # Parallel extraction: all chapters at once
    unified_result = extract_all_parallel_unified(chapters, extraction_agent)
    # unified_result.characters, scenes, events, relations

    # Or the sync wrapper:
    from core.async_pipeline import extract_all_parallel_unified_sync
    unified_result = extract_all_parallel_unified_sync(chapters, extraction_agent)

    # Backward-compatible old interface (still uses single unified call per chapter):
    from core.async_pipeline import extract_all_parallel_sync
    unified_result = extract_all_parallel_sync(chapters, char_agent, scene_agent, event_agent, relation_agent)
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

try:
    from core.progress import ProgressTracker
except ImportError:
    ProgressTracker = None


@dataclass
class AsyncExtractionResult:
    """Aggregated extraction results from all chapters."""
    characters: list
    scenes: list
    events: list
    relations: list


async def _extract_one_chapter(chapters_with_idx, extraction_agent):
    """Extract all knowledge from a single chapter using unified extraction.

    This implements think.md Principle III: ONE LLM call per chapter.
    """
    idx, ch = chapters_with_idx
    ch_id = getattr(ch, "id", f"ch_{idx+1:03d}")
    ch_title = getattr(ch, "title", "")
    ch_content = getattr(ch, "content", "")

    try:
        result = await asyncio.to_thread(
            extraction_agent.extract,
            ch_content,
            ch_id,
            ch_title,
        )
        return idx, ch_id, result
    except Exception as e:
        return idx, ch_id, e


async def _extract_with_tracking(
    chapters_with_idx,
    extraction_agent,
    tracker: Optional["ProgressTracker"],
):
    """Extract one chapter and update tracker on completion."""
    idx, ch = chapters_with_idx
    ch_title = getattr(ch, "title", "")
    ch_id = getattr(ch, "id", f"ch_{idx+1:03d}")

    try:
        result = await asyncio.to_thread(
            extraction_agent.extract,
            getattr(ch, "content", ""),
            ch_id,
            ch_title,
        )
        if tracker:
            tracker.on_agent_done("知识抽取", idx, ch_title)
        return idx, ch_id, result
    except Exception as e:
        if tracker:
            tracker.on_agent_done("知识抽取", idx, ch_title)
        return idx, ch_id, e


async def extract_all_parallel_unified(
    chapters,
    extraction_agent,
    tracker: Optional["ProgressTracker"] = None,
) -> AsyncExtractionResult:
    """Extract all knowledge from all chapters concurrently using unified extraction.

    Each chapter uses a SINGLE LLM call (via UnifiedExtractionAgent.extract).
    Chapters are processed in parallel via asyncio.gather().

    This is the think.md-compliant parallel extraction function.

    Args:
        chapters: list of Chapter objects
        extraction_agent: UnifiedExtractionAgent instance
        tracker: optional ProgressTracker for UI updates

    Returns:
        AsyncExtractionResult with all knowledge from all chapters.

    Complexity:
        - Wall-clock time: O(1) for extraction phase (all chapters in parallel)
        - LLM calls: O(n_chapters) — 1 call per chapter, NOT 4 calls per chapter
    """
    if not chapters:
        return AsyncExtractionResult(characters=[], scenes=[], events=[], relations=[])

    indexed = [(i, ch) for i, ch in enumerate(chapters)]

    if tracker:
        tasks = [
            _extract_with_tracking(indexed_ch, extraction_agent, tracker)
            for indexed_ch in indexed
        ]
    else:
        tasks = [
            _extract_one_chapter(indexed_ch, extraction_agent)
            for indexed_ch in indexed
        ]

    results = await asyncio.gather(*tasks)

    all_chars = []
    all_scenes = []
    all_events = []
    all_relations = []

    # Sort by chapter index to maintain order
    results.sort(key=lambda x: x[0])

    for idx, cid, result in results:
        if isinstance(result, Exception):
            # Log but continue — don't fail all chapters for one error
            continue

        all_chars.extend(result.characters)
        all_scenes.extend(result.scenes)
        all_events.extend(result.events)
        all_relations.extend(result.relations)

    return AsyncExtractionResult(
        characters=all_chars,
        scenes=all_scenes,
        events=all_events,
        relations=all_relations,
    )


def extract_all_parallel_unified_sync(
    chapters,
    extraction_agent,
    tracker: Optional["ProgressTracker"] = None,
) -> AsyncExtractionResult:
    """Synchronous wrapper around extract_all_parallel_unified."""
    return asyncio.run(extract_all_parallel_unified(chapters, extraction_agent, tracker))


# ── Backward-compatible interface (for legacy callers) ──────────────────────────
# These still use the single unified extraction call internally,
# but expose the old 4-agent interface for callers that still use it.


async def _legacy_extract_one_chapter(chapters_with_idx, char_agent, scene_agent, event_agent, relation_agent):
    """Extract using the old 4-agent interface (still unified internally)."""
    idx, ch = chapters_with_idx
    ch_id = getattr(ch, "id", f"ch_{idx+1:03d}")
    ch_title = getattr(ch, "title", "")
    ch_content = getattr(ch, "content", "")

    try:
        # Use UnifiedExtractionAgent if available, fall back to old pattern
        try:
            from agent.unified_extraction_agent import UnifiedExtractionAgent
            agent = UnifiedExtractionAgent(char_agent.llm)
            result = await asyncio.to_thread(agent.extract, ch_content, ch_id, ch_title)
            return idx, ch_id, result
        except ImportError:
            # Fall back to old 4-agent pattern
            chars = await asyncio.to_thread(char_agent.extract_from_chapters, [ch], None)
            scenes = await asyncio.to_thread(scene_agent.parse_from_chapters, [ch], None)
            events = await asyncio.to_thread(event_agent.extract_events_from_chapters, [ch], None)
            rels = await asyncio.to_thread(relation_agent.extract_from_chapters, [ch], None)
            from agent.unified_extraction_agent import UnifiedExtractionResult
            return idx, ch_id, UnifiedExtractionResult(
                characters=chars, scenes=scenes, events=events, relations=rels
            )
    except Exception as e:
        return idx, ch_id, e


async def extract_all_parallel(chapters, char_agent, scene_agent, event_agent, relation_agent) -> AsyncExtractionResult:
    """Backward-compatible: extract using unified extraction (internally).

    Note: The old interface took 4 separate agents but now uses a single
    UnifiedExtractionAgent internally. This maintains API compatibility
    while fixing the architectural violation.
    """
    if not chapters:
        return AsyncExtractionResult(characters=[], scenes=[], events=[], relations=[])

    indexed = [(i, ch) for i, ch in enumerate(chapters)]
    tasks = [
        _legacy_extract_one_chapter(indexed_ch, char_agent, scene_agent, event_agent, relation_agent)
        for indexed_ch in indexed
    ]
    results = await asyncio.gather(*tasks)

    all_chars = []
    all_scenes = []
    all_events = []
    all_relations = []

    results.sort(key=lambda x: x[0])

    for idx, cid, result in results:
        if isinstance(result, Exception):
            continue
        all_chars.extend(result.characters)
        all_scenes.extend(result.scenes)
        all_events.extend(result.events)
        all_relations.extend(result.relations)

    return AsyncExtractionResult(
        characters=all_chars,
        scenes=all_scenes,
        events=all_events,
        relations=all_relations,
    )


def extract_all_parallel_sync(chapters, char_agent, scene_agent, event_agent, relation_agent) -> AsyncExtractionResult:
    """Synchronous wrapper — backward-compatible API."""
    return asyncio.run(extract_all_parallel(chapters, char_agent, scene_agent, event_agent, relation_agent))
