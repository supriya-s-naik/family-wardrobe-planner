from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pinecone import Pinecone

from wardrobe_planner.domain.models import GuidanceDocument

DEFAULT_NAMESPACE = "reviewed-guidance-v1"
DEFAULT_EMBED_MODEL = "llama-text-embed-v2"


class PineconeGuidanceRAG:
    """Pinecone integrated-embedding adapter for reviewed style guidance."""

    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        namespace: str = DEFAULT_NAMESPACE,
        embed_model: str = DEFAULT_EMBED_MODEL,
        client: Any | None = None,
    ) -> None:
        self.index_name = index_name
        self.namespace = namespace
        self.embed_model = embed_model
        self.client = client or Pinecone(api_key=api_key)

    @classmethod
    def from_env(cls) -> PineconeGuidanceRAG:
        load_dotenv()
        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME")
        if not api_key or not index_name:
            raise RuntimeError("Pinecone guidance retrieval is not configured")
        return cls(
            api_key=api_key,
            index_name=index_name,
            namespace=os.getenv("PINECONE_NAMESPACE", DEFAULT_NAMESPACE),
            embed_model=os.getenv("PINECONE_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        )

    def ensure_index(self) -> None:
        existing = {index.name for index in self.client.indexes.list()}
        if self.index_name in existing:
            return
        self.client.indexes.create_for_model(
            name=self.index_name,
            cloud="aws",
            region="us-east-1",
            embed={
                "model": self.embed_model,
                "field_map": {"text": "chunk_text"},
                "write_parameters": {"input_type": "passage", "truncate": "END"},
                "read_parameters": {"input_type": "query", "truncate": "END"},
            },
            deletion_protection="disabled",
            tags={"project": "family-wardrobe-planner", "purpose": "style-guidance-rag"},
            timeout=120,
        )

    def ingest(self, documents: list[GuidanceDocument]) -> int:
        self.ensure_index()
        records = [
            {
                "_id": document.id,
                "chunk_text": document.text,
                "title": document.title,
                "source": document.source,
                "event_types": document.event_types,
                "dress_codes": document.dress_codes,
                "season_tags": document.season_tags,
                "audience_tags": document.audience_tags,
            }
            for document in documents
        ]
        response = self.client.index(self.index_name).upsert_records(
            namespace=self.namespace,
            records=records,
            timeout=60,
        )
        return int(response.record_count)

    def search_guidance(
        self,
        query_terms: list[str],
        limit: int = 4,
        dress_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query = build_guidance_query(query_terms)
        response = self.client.index(self.index_name).search(
            namespace=self.namespace,
            top_k=limit,
            inputs={"text": query},
            filter={"dress_codes": {"$in": dress_codes}} if dress_codes else None,
            fields=[
                "chunk_text",
                "title",
                "source",
                "event_types",
                "dress_codes",
                "season_tags",
                "audience_tags",
            ],
            timeout=30,
        )
        matches = []
        for hit in response.result.hits:
            fields = dict(hit.fields)
            matches.append(
                {
                    "id": hit.id,
                    "title": fields.get("title", "Untitled guidance"),
                    "source": fields.get("source", "Unknown source"),
                    "text": fields.get("chunk_text", ""),
                    "event_types": list(fields.get("event_types", [])),
                    "dress_codes": list(fields.get("dress_codes", [])),
                    "season_tags": list(fields.get("season_tags", [])),
                    "audience_tags": list(fields.get("audience_tags", [])),
                    "retrieval_provider": "pinecone",
                    "retrieval_query": query,
                    "retrieval_score": round(float(hit.score), 4),
                }
            )
        return matches


def build_guidance_query(query_terms: list[str]) -> str:
    normalized = [str(term).replace("_", " ").strip() for term in query_terms if str(term).strip()]
    return "Family wardrobe styling guidance for " + ", ".join(dict.fromkeys(normalized))
