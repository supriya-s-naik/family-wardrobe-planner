from __future__ import annotations

import os
import tempfile
from typing import Any

import httpx
from dotenv import load_dotenv


class Mem0PreferenceMemory:
    """Member-scoped durable preference storage backed by Mem0 Platform."""

    provider_name = "mem0"

    def __init__(self, household_id: str, client: Any) -> None:
        self.household_id = household_id
        self.client = client

    @classmethod
    def from_env(cls, household_id: str) -> Mem0PreferenceMemory:
        load_dotenv()
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            raise RuntimeError("MEM0_API_KEY is not configured")

        # The SDK keeps a small telemetry identity file. A temporary directory keeps
        # that SDK detail outside the project and works in restricted environments.
        os.environ.setdefault(
            "MEM0_DIR", os.path.join(tempfile.gettempdir(), "wardrobe-planner-mem0")
        )
        try:
            from mem0 import MemoryClient

            client = MemoryClient(
                api_key=api_key,
                client=httpx.Client(timeout=httpx.Timeout(30.0)),
            )
        except Exception as exc:
            raise RuntimeError(f"Mem0 connection failed: {type(exc).__name__}") from exc
        return cls(household_id=household_id, client=client)

    def save_preference(
        self,
        member_id: str,
        preference: str,
        category: str,
    ) -> list[dict[str, Any]]:
        text = preference.strip()
        if not text:
            raise ValueError("Preference cannot be empty")
        response = self.client.add(
            messages=[{"role": "user", "content": text}],
            user_id=self._user_id(member_id),
            metadata={
                "household_id": self.household_id,
                "member_id": member_id,
                "category": category,
                "source": "user_explicit",
            },
        )
        return self._normalize_results(response, member_id)

    def search_preferences(
        self,
        member_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        response = self.client.search(
            query=query.strip() or "clothing style and comfort preferences",
            filters={"user_id": self._user_id(member_id)},
            top_k=limit,
            threshold=0.0,
        )
        return self._normalize_results(response, member_id)

    def list_preferences(self, member_id: str, limit: int = 50) -> list[dict[str, Any]]:
        response = self.client.get_all(
            filters={"user_id": self._user_id(member_id)},
            page=1,
            page_size=limit,
        )
        return self._normalize_results(response, member_id)

    def delete_preference(self, memory_id: str) -> None:
        if not memory_id:
            raise ValueError("Memory ID is required")
        self.client.delete(memory_id)

    def _user_id(self, member_id: str) -> str:
        return f"wardrobe-planner:{self.household_id}:{member_id}"

    @staticmethod
    def _normalize_results(response: Any, member_id: str) -> list[dict[str, Any]]:
        if isinstance(response, dict):
            rows = response.get("results", [])
        elif isinstance(response, list):
            rows = response
        else:
            rows = []

        normalized = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            text = row.get("memory") or row.get("text")
            if not text:
                continue
            normalized.append(
                {
                    "id": str(row.get("id") or row.get("memory_id") or ""),
                    "member_id": member_id,
                    "text": str(text),
                    "category": str(metadata.get("category") or "general"),
                    "score": row.get("score"),
                    "created_at": row.get("created_at"),
                    "provider": "mem0",
                }
            )
        return normalized
