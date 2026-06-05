"""RelationAgent — extracts character relationships from novel text."""
from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT, RELATION_EXTRACTION_PROMPT
from core.chapter_parser import Chapter
from schema.models import Relation, SourceTrace


class RelationAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract_relations(self, text: str) -> list[Relation]:
        """Extract all character relationships from a single text."""
        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + RELATION_EXTRACTION_PROMPT,
            text,
        )
        relations = []
        for data in response.get("relations", []):
            relations.append(Relation(
                from_char=data.get("from_char", ""),
                to_char=data.get("to_char", ""),
                relation_type=data.get("relation_type", "stranger"),
                description=data.get("description", ""),
            ))
        return relations

    def extract_from_chapters(self, chapters: list[Chapter], llm: LLMClient) -> list[Relation]:
        """Extract relations from each chapter, attaching source trace."""
        all_relations = []
        for ch in chapters:
            relations = self.extract_relations(ch.content)
            for r in relations:
                r.source = SourceTrace(
                    chapter_id=ch.id,
                    chapter_title=ch.title,
                    char_range=(0, 0),
                )
            all_relations.extend(relations)
        return all_relations
