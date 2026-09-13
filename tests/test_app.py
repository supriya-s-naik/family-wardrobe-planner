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
        app.session_state["planning_state"]["final_result"]["workflow_metrics"]["tool_calls"] == 8
    )
    app.number_input[0].set_value(0).run()
    assert not app.success
    assert "selections have changed" in app.info[0].value


def test_event_action_scopes_plan_and_empty_selection_is_disabled():
    app = start()
    app.radio(key="page").set_value("Events").run()
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
