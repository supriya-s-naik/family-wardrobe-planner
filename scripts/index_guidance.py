from __future__ import annotations

import time
from pathlib import Path

from wardrobe_planner.adapters.pinecone_rag import PineconeGuidanceRAG
from wardrobe_planner.data.seed_loader import load_seed_dataset

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dataset = load_seed_dataset(ROOT / "data" / "seed")
    rag = PineconeGuidanceRAG.from_env()
    count = rag.ingest(dataset.guidance_documents)
    print(f"Indexed {count} reviewed guidance passages in {rag.index_name}/{rag.namespace}.")

    query_terms = ["school celebration", "smart_casual", "family"]
    for _ in range(10):
        matches = rag.search_guidance(query_terms, limit=3)
        if matches:
            print("Retrieval check:")
            for match in matches:
                print(f"- {match['id']} ({match['retrieval_score']:.4f})")
            return
        time.sleep(2)
    raise RuntimeError("Records were accepted but were not searchable within 20 seconds")


if __name__ == "__main__":
    main()
