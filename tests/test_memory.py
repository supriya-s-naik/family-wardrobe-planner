from wardrobe_planner.adapters.mem0_memory import Mem0PreferenceMemory


class FakeMem0Client:
    def __init__(self) -> None:
        self.calls = []

    def add(self, **kwargs):
        self.calls.append(("add", kwargs))
        return {
            "results": [
                {
                    "id": "memory_1",
                    "memory": "Prefers flats for long walks",
                    "metadata": {"category": "footwear"},
                }
            ]
        }

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return {
            "results": [
                {
                    "id": "memory_1",
                    "memory": "Prefers flats for long walks",
                    "metadata": {"category": "footwear"},
                    "score": 0.91,
                }
            ]
        }

    def get_all(self, **kwargs):
        self.calls.append(("get_all", kwargs))
        return {
            "count": 1,
            "results": [
                {
                    "id": "memory_1",
                    "memory": "Prefers flats for long walks",
                    "metadata": {"category": "footwear"},
                }
            ],
        }

    def delete(self, memory_id):
        self.calls.append(("delete", {"memory_id": memory_id}))
        return {"message": "deleted"}


def test_mem0_adapter_scopes_every_operation_to_one_family_member() -> None:
    client = FakeMem0Client()
    memory = Mem0PreferenceMemory("household_rivera", client)

    saved = memory.save_preference(
        "member_maya",
        "Prefers flats for long walks",
        "footwear",
    )
    searched = memory.search_preferences("member_maya", "walking footwear", limit=3)
    listed = memory.list_preferences("member_maya")
    memory.delete_preference("memory_1")

    expected_user_id = "wardrobe-planner:household_rivera:member_maya"
    add_call = client.calls[0][1]
    assert add_call["user_id"] == expected_user_id
    assert add_call["metadata"]["member_id"] == "member_maya"
    assert add_call["metadata"]["source"] == "user_explicit"
    assert client.calls[1][1]["filters"] == {"user_id": expected_user_id}
    assert client.calls[2][1]["filters"] == {"user_id": expected_user_id}
    assert client.calls[3] == ("delete", {"memory_id": "memory_1"})
    assert saved[0]["member_id"] == "member_maya"
    assert searched[0]["score"] == 0.91
    assert listed[0]["category"] == "footwear"
