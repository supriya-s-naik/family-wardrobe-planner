from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def start():
    return AppTest.from_file(str(APP_PATH)).run(timeout=15)


def await_plan(app):
    try:
        job = app.session_state["planning_job"]
    except KeyError:
        return app
    try:
        job.result(timeout=15)
    except RuntimeError:
        pass
    return app.run(timeout=15)


def test_overview_and_wardrobe_navigation():
    app = start()
    assert not app.exception
    assert app.title[0].value == "Life happens. Let’s get dressed."
    app.button(key="closet_member_arjun").click().run()
    assert not app.exception
    assert app.button(key="add_wardrobe_item").label == "＋ Add item"
    assert app.selectbox(key="owner").value == "member_arjun"
    app.selectbox[1].select("footwear").run()
    assert not app.exception
    assert any("pieces" in c.value for c in app.caption)


def test_generate_family_plan_button_completes_workflow():
    app = start()
    app.radio(key="page").set_value("Plan outfits").run()
    app.radio[1].set_value("Demo-safe local").run()
    app.button[0].click().run(timeout=15)
    app = await_plan(app)
    assert not app.exception
    assert "Your family plan is ready" in app.success[0].value
    assert (
        app.session_state["planning_state"]["final_result"]["workflow_metrics"]["tool_calls"] == 9
    )
    app.number_input[0].set_value(0).run()
    assert not app.success
    assert "selections have changed" in app.info[0].value


def test_event_action_scopes_plan_and_empty_selection_is_disabled():
    app = start()
    app.radio(key="page").set_value("Events").run()
    assert app.button(key="add_event").label == "＋ Add event"
    assert app.button(key="sync_calendar").label == "↻ Sync calendar"
    app.button(key="plan_event_school_celebration").click().run()
    assert app.multiselect[0].value == ["event_school_celebration"]
    app.radio[1].set_value("Demo-safe local").run()
    app.number_input[0].set_value(0).run()
    app.button[0].click().run(timeout=15)
    app = await_plan(app)
    assert not app.exception
    result = app.session_state["planning_state"]["final_result"]
    assert result["status"] == "valid"
    assert {o["event_id"] for o in result["outfits"]} == {"event_school_celebration"}
    assert result["total_purchase_cost"] == 0
    app.multiselect[0].set_value([]).run()
    assert app.button[0].disabled


def test_intake_buttons_open_prototype_forms():
    wardrobe_app = start()
    wardrobe_app.radio(key="page").set_value("Wardrobe").run()
    wardrobe_app.button(key="add_wardrobe_item").click().run()
    assert not wardrobe_app.exception
    assert wardrobe_app.button(key="analyze_wardrobe_photo").disabled
    assert any(field.label == "Item name" for field in wardrobe_app.text_input)

    event_app = start()
    event_app.radio(key="page").set_value("Events").run()
    event_app.button(key="add_event").click().run()
    assert not event_app.exception
    assert any(field.label == "Event name" for field in event_app.text_input)

    calendar_app = start()
    calendar_app.radio(key="page").set_value("Events").run()
    calendar_app.button(key="sync_calendar").click().run()
    assert not calendar_app.exception
    assert any(option.label == "Calendar provider" for option in calendar_app.radio)


def test_style_this_item_can_be_required_in_a_plan():
    app = start()
    app.radio(key="page").set_value("Wardrobe").run()
    app.button(key="style_maya_top_03").click().run()
    assert not app.exception
    assert app.session_state["page"] == "Plan outfits"
    assert any(
        "Styling around Navy striped T-shirt" in block.value for block in app.markdown
    )

    app.selectbox(key="style_item_mode").select("Must use").run()
    app.multiselect(key="selected_events").set_value(["event_coastal_outing"]).run()
    app.radio[1].set_value("Demo-safe local").run()
    app.button(key="generate_plan").click().run(timeout=15)
    app = await_plan(app)

    result = app.session_state["planning_state"]["final_result"]
    maya_outfit = next(
        outfit for outfit in result["outfits"] if outfit["member_id"] == "member_maya"
    )
    assert result["status"] == "valid"
    assert "maya_top_03" in maya_outfit["item_ids"]


def test_family_page_can_save_and_display_member_scoped_memory():
    class FakePreferenceStore:
        def __init__(self):
            self.rows = []

        def list_preferences(self, member_id):
            return [row for row in self.rows if row["member_id"] == member_id]

        def save_preference(self, member_id, text, category):
            row = {
                "id": "memory_1",
                "member_id": member_id,
                "text": text,
                "category": category,
                "provider": "mem0",
            }
            self.rows.append(row)
            return [row]

        def delete_preference(self, memory_id):
            self.rows = [row for row in self.rows if row["id"] != memory_id]

    store = FakePreferenceStore()
    with patch(
        "wardrobe_planner.adapters.mem0_memory.Mem0PreferenceMemory.from_env",
        return_value=store,
    ):
        app = start()
        app.radio(key="page").set_value("Family").run()
        assert not app.exception
        app.text_area[0].set_value("Maya prefers flats for long walks").run()
        app.selectbox(key="memory_member_id").select("member_maya").run()
        app.button(key="FormSubmitter:save_preference_form-Remember preference").click().run()

        app.radio(key="page").set_value("Plan outfits").run()
        app.multiselect(key="selected_events").set_value(["event_coastal_outing"]).run()
        app.radio[1].set_value("Demo-safe local").run()
        app.button(key="generate_plan").click().run(timeout=15)
        app = await_plan(app)

    assert not app.exception
    assert store.rows[0]["member_id"] == "member_maya"
    result = app.session_state["planning_state"]["final_result"]
    maya_outfit = next(
        outfit for outfit in result["outfits"] if outfit["member_id"] == "member_maya"
    )
    assert "maya_shoe_01" in maya_outfit["item_ids"]
    memory_result = next(
        row
        for row in app.session_state["planning_state"]["tool_results"]
        if row["name"] == "search_memories"
    )["result"]
    assert memory_result["memories_by_member"]["member_arjun"] == []


def test_failed_planning_renders_without_empty_columns():
    app = start()
    app.radio(key="page").set_value("Plan outfits").run()
    app.radio[1].set_value("Demo-safe local").run()
    with patch(
        "wardrobe_planner.workflow.graph.run_demo_workflow", side_effect=RuntimeError("offline")
    ):
        app.button[0].click().run()
        app = await_plan(app)
    assert not app.exception
    assert app.error
