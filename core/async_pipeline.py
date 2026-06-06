"""Async Pipeline — concurrent chapter-level knowledge extraction.

Uses asyncio.to_thread() to run synchronous LLM calls in parallel, reducing
total wall-clock time from O(n_chapters) to O(1) for extraction.

Usage:
    import asyncio
    from core.async_pipeline import extract_all_parallel

    results = asyncio.run(extract_all_parallel(chapters, llm))
    # results["characters"], results["scenes"], results["events"], results["relations"]
"""
import asyncio
from dataclasses import dataclass


@dataclass
class AsyncExtractionResult:
    characters: list
    scenes: list
    events: list
    relations: list


async def _extract_one_chapter(chapters_with_idx, char_agent, scene_agent, event_agent, relation_agent):
    """Extract knowledge from a single chapter."""
    idx, ch = chapters_with_idx
    try:
        chars = await asyncio.to_thread(char_agent.extract_from_chapters, [ch], None)
        scenes = await asyncio.to_thread(scene_agent.parse_from_chapters, [ch], None)
        events = await asyncio.to_thread(event_agent.extract_events_from_chapters, [ch], None)
        rels = await asyncio.to_thread(relation_agent.extract_from_chapters, [ch], None)
        return idx, ch.id, (chars, scenes, events, rels)
    except Exception as e:
        return idx, ch.id, e


async def extract_all_parallel(chapters, char_agent, scene_agent, event_agent, relation_agent):
    """Extract all knowledge from chapters concurrently.

    Runs character/scene/event/relation extraction for all chapters in parallel.
    Each chapter's extraction runs concurrently with others.

    Returns:
        AsyncExtractionResult with aggregated results from all chapters.

    Note: For smaller novels (<5 chapters), the overhead of asyncio may not
    be worth it. The sequential path (StoryForgeWorkflow.run()) is simpler and
    sufficient for those cases.
    """
    if not chapters:
        return AsyncExtractionResult(characters=[], scenes=[], events=[], relations=[])

    # Create tasks for all chapters in parallel
    tasks = [
        _extract_one_chapter((i, ch), char_agent, scene_agent, event_agent, relation_agent)
        for i, ch in enumerate(chapters)
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
            # Log but don't fail — continue with other chapters
            continue
        chars, scenes, events, rels = result
        all_chars.extend(chars)
        all_scenes.extend(scenes)
        all_events.extend(events)
        all_relations.extend(rels)

    return AsyncExtractionResult(
        characters=all_chars,
        scenes=all_scenes,
        events=all_events,
        relations=all_relations,
    )


def extract_all_parallel_sync(chapters, char_agent, scene_agent, event_agent, relation_agent):
    """Synchronous wrapper around extract_all_parallel. Use this from non-async code."""
    return asyncio.run(extract_all_parallel(chapters, char_agent, scene_agent, event_agent, relation_agent))
