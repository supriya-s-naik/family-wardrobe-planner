from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from wardrobe_planner.adapters.mem0_memory import Mem0PreferenceMemory
from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.workflow.graph import build_planning_graph

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dataset = load_seed_dataset(ROOT / "data" / "seed")
    member_id = "member_maya"
    marker = f"mem0-smoke-{uuid4().hex[:10]}"
    store = Mem0PreferenceMemory.from_env(f"{dataset.household.id}:{marker}")
    preference = f"Maya prefers flat shoes for long walks. Test reference: {marker}."
    before_ids = {row["id"] for row in store.list_preferences(member_id) if row.get("id")}
    created_ids: set[str] = set()

    try:
        saved = store.save_preference(member_id, preference, "test")
        created_ids.update(
            row["id"] for row in saved if row.get("id") and row["id"] not in before_ids
        )

        for _ in range(10):
            current = store.list_preferences(member_id)
            created_ids.update(
                row["id"] for row in current if row.get("id") and row["id"] not in before_ids
            )
            if created_ids:
                break
            time.sleep(1)

        if not created_ids:
            raise RuntimeError("Mem0 did not create a new member-scoped preference")

        matches = store.search_preferences(
            member_id,
            "What footwear does Maya prefer for long walks?",
            limit=10,
        )
        if not created_ids.intersection(row["id"] for row in matches if row.get("id")):
            raise RuntimeError("Mem0 created the preference but semantic search did not find it")
        print("Mem0 add/search/member-scope check passed.")

        dataset.demo_request.event_ids = ["event_coastal_outing"]
        graph = build_planning_graph(dataset, memory_search=store.search_preferences)
        state = graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})
        memory_result = next(
            result for result in state["tool_results"] if result["name"] == "search_memories"
        )["result"]
        maya_outfit = next(
            outfit
            for outfit in state["final_result"]["outfits"]
            if outfit["member_id"] == member_id
        )
        if memory_result["retrieval_metadata"]["provider"] != "mem0":
            raise RuntimeError("Planning workflow did not use the Mem0 provider")
        if "maya_shoe_01" not in maya_outfit["item_ids"]:
            raise RuntimeError("Planning workflow did not apply the remembered flats preference")
        print("Mem0 planning-tool and preference-application check passed.")
    finally:
        for memory_id in created_ids:
            store.delete_preference(memory_id)
        if created_ids:
            print("Temporary smoke-test memory deleted.")


if __name__ == "__main__":
    main()
