from pathlib import Path

from wardrobe_planner.adapters.local import LocalPlanningData
from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.workflow.tools import ToolExecutor

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def planning_context_arguments(dataset):
    return {
        "member_ids": [member.id for member in dataset.family_members],
        "event_ids": [event.id for event in dataset.events],
        "purchase_budget": dataset.demo_request.purchase_budget,
    }


def test_planning_context_uses_pinecone_matches_when_available() -> None:
    dataset = load_seed_dataset(SEED_DIR)

    def fake_search(query_terms: list[str], limit: int):
        assert "school celebration" in query_terms
        assert limit == 6
        return [
            {
                **dataset.guidance_documents[0].model_dump(mode="json"),
                "retrieval_provider": "pinecone",
                "retrieval_query": "test query",
                "retrieval_score": 0.91,
            }
        ]

    tools = ToolExecutor(LocalPlanningData(dataset), guidance_search=fake_search)
    context = tools.execute("prepare_planning_context", planning_context_arguments(dataset))

    assert context["retrieval_metadata"]["provider"] == "pinecone"
    assert context["retrieval_metadata"]["fallback_used"] is False
    assert context["guidance"][0]["retrieval_score"] == 0.91


def test_planning_context_falls_back_when_pinecone_fails() -> None:
    dataset = load_seed_dataset(SEED_DIR)

    def failing_search(_query_terms: list[str], _limit: int):
        raise ConnectionError("test outage")

    tools = ToolExecutor(LocalPlanningData(dataset), guidance_search=failing_search)
    context = tools.execute("prepare_planning_context", planning_context_arguments(dataset))

    assert context["retrieval_metadata"]["provider"] == "local_keyword"
    assert context["retrieval_metadata"]["fallback_used"] is True
    assert context["retrieval_metadata"]["fallback_reason"] == "ConnectionError"
    assert context["guidance"]
