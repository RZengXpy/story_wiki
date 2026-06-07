"""Chapter Parser — splits a novel into chapters with IDs and source traces."""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Chapter:
    id: str
    number: int
    title: str
    content: str
    start_char: int
    end_char: int


CHAPTER_PATTERN = re.compile(r"第[一二三四五六七八九十百千零\d]+章[：:]\s*(.+)")


def parse_chapters(novel_text: str) -> list[Chapter]:
    """Split novel into chapters by "第X章" headings."""
    chapters: list[Chapter] = []

    chapter_num = 0
    last_end = 0

    for match in CHAPTER_PATTERN.finditer(novel_text):
        chapter_num += 1
        heading_start = match.start()
        heading_end = match.end()

        if heading_start > last_end:
            prelude = novel_text[last_end:heading_start].strip()
            if prelude and chapters:
                prev = chapters[-1]
                chapters[-1] = Chapter(
                    id=prev.id,
                    number=prev.number,
                    title=prev.title,
                    content=prev.content + "\n\n" + prelude,
                    start_char=prev.start_char,
                    end_char=heading_start,
                )

        # Strip trailing punctuation / notes from chapter title
        chapter_title = re.sub(r"[（(].+$", "", match.group(1)).strip()
        chapter_id = f"ch_{chapter_num:03d}"

        next_match = CHAPTER_PATTERN.search(novel_text, heading_end)
        content_end = next_match.start() if next_match else len(novel_text)

        chapters.append(Chapter(
            id=chapter_id,
            number=chapter_num,
            title=chapter_title,
            content=novel_text[heading_end:content_end].strip(),
            start_char=heading_start,
            end_char=content_end,
        ))
        last_end = content_end

    if not chapters and novel_text.strip():
        chapters.append(Chapter(
            id="ch_001",
            number=1,
            title="全文",
            content=novel_text.strip(),
            start_char=0,
            end_char=len(novel_text),
        ))

    return chapters


def get_chapter_by_id(chapters: list[Chapter], chapter_id: str) -> Optional[Chapter]:
    """Retrieve a chapter by its ID."""
    for ch in chapters:
        if ch.id == chapter_id:
            return ch
    return None
