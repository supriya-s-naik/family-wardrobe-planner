from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.workflow.graph import run_demo_workflow, run_nebius_workflow

ROOT = Path(__file__).resolve().parent
APP_STATE_VERSION = "background-planning-v4"
st.set_page_config(
    page_title="Everyday / together · Wardrobe Planner", page_icon="🌿", layout="wide"
)
st.html(f"<style>{(ROOT / 'assets' / 'app.css').read_text(encoding='utf-8')}</style>")
dataset = load_seed_dataset(ROOT / "data" / "seed")
if st.session_state.get("app_state_version") != APP_STATE_VERSION:
    st.session_state.pop("planning_state", None)
    st.session_state.pop("planning_job", None)
    st.session_state.pop("planning_error", None)
    st.session_state["app_state_version"] = APP_STATE_VERSION
member_by_id = {m.id: m for m in dataset.family_members}
event_by_id = {e.id: e for e in dataset.events}
item_by_id = {i.id: i for i in dataset.wardrobe_items}
COLORS = {
    "teal": "#477d78",
    "navy": "#35415b",
    "burgundy": "#813f54",
    "olive": "#777e54",
    "white": "#eeeade",
    "coral": "#cb806d",
    "purple": "#8e709e",
    "blue": "#5c88ae",
    "black": "#343634",
    "gray": "#959892",
    "gold": "#bba367",
    "brown": "#92715b",
    "cream": "#e5ddc7",
}


@st.cache_resource
def planning_executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="wardrobe-planner")


@st.fragment(run_every=1)
def render_planning_progress():
    job = st.session_state.get("planning_job")
    if job is None:
        return
    if not job.done():
        st.info("Building your family plan… You can explore another section while this finishes.")
        return

    try:
        st.session_state["planning_state"] = job.result()
    except Exception:  # noqa: BLE001 -- Background failures stay inside the UI boundary.
        st.session_state["planning_error"] = (
            "Planning couldn’t finish. Please try again or choose Demo-safe local in Planning options."
        )
    finally:
        st.session_state.pop("planning_job", None)
    st.rerun()


def navigate(page, event_id=None):
    st.session_state["page"] = page
    if event_id:
        st.session_state["selected_events"] = [event_id]


def open_wardrobe(member_id):
    st.session_state["owner"] = member_id
    navigate("Wardrobe")


def illustration(category, color, label=""):
    shade = COLORS.get(color.lower(), "#9aa48c")
    return f'<div class="garment-stage" role="img" aria-label="{escape(label or category)} illustration"><div class="garment {escape(category)}" style="--fabric:{shade}"></div></div>'


def family_cards():
    for column, member in zip(
        st.columns(len(dataset.family_members)), dataset.family_members, strict=True
    ):
        with column, st.container(border=True):
            swatches = "".join(
                f'<span style="background:{COLORS.get(c, "#9aa48c")}"></span>'
                for c in member.preferred_colors
            )
            st.html(
                f'<div class="person-heading"><span class="avatar">{escape(member.name[0])}</span><div><h3>{escape(member.name)}</h3><span class="muted">{member.age_group.title()}</span></div></div><div class="swatches">{swatches}</div>'
            )
            st.caption(", ".join(member.preferred_colors).title())
            st.write("; ".join(member.comfort_needs))
            with st.expander("Style preferences"):
                st.write("**Avoids:** " + ", ".join(member.avoided_styles or ["None specified"]))
                if member.avoided_colors:
                    st.write("**Colors to avoid:** " + ", ".join(member.avoided_colors))
                if member.cultural_preferences:
                    st.write("**Personal preferences:** " + "; ".join(member.cultural_preferences))
                st.write("**Sizes:** " + ", ".join(f"{k}: {v}" for k, v in member.sizes.items()))
            st.button(
                f"Explore {member.name}’s wardrobe →",
                key=f"closet_{member.id}",
                on_click=open_wardrobe,
                args=(member.id,),
            )


def render_results(state):
    result = state["final_result"]
    if result["status"] == "valid":
        st.success(
            f"Your family plan is ready · ${result['total_purchase_cost']:.0f} in suggested purchases"
        )
    else:
        st.error(result.get("error", "This plan needs review before you use it."))
        for error in result.get("validation_errors", []):
            st.write(error)
    for event_id in state["request"]["event_ids"]:
        outfits = [o for o in result.get("outfits", []) if o["event_id"] == event_id]
        if not outfits:
            continue
        st.subheader(event_by_id[event_id].name)
        for column, outfit in zip(st.columns(len(outfits)), outfits, strict=True):
            with column, st.container(border=True):
                st.markdown(f"### {member_by_id[outfit['member_id']].name}")
                st.caption("FROM YOUR WARDROBE")
                for item_id in outfit["item_ids"]:
                    st.write("• " + item_by_id[item_id].name)
                st.caption(outfit["rationale"])
    if result.get("purchases"):
        st.subheader("A few missing pieces")
        st.caption("Suggestions from the sample catalog. Nothing is purchased automatically.")
        catalog = {i.id: i for i in dataset.catalog_items}
        for purchase in result["purchases"]:
            product = catalog[purchase["catalog_item_id"]]
            with st.container(border=True):
                st.write(
                    f"**{product.name}** for {member_by_id[purchase['member_id']].name} · ${product.price:.0f}"
                )
                st.caption(purchase["rationale"])
    with st.expander("Planning details"):
        st.json(result.get("workflow_metrics", {}))
        for trace in state.get("tool_trace", []):
            actor = "Workflow" if trace.get("actor") == "workflow" else "Agent"
            st.write(f"**{trace['step']}. {trace['tool']}** · {actor} — {trace['reason']}")
            st.json(trace["arguments"])
        context_record = next(
            (
                record
                for record in state.get("tool_results", [])
                if record["name"] == "prepare_planning_context"
            ),
            None,
        )
        if context_record:
            context = context_record["result"]
            retrieval = context.get("retrieval_metadata", {})
            st.markdown("#### Retrieved guidance")
            provider = retrieval.get("provider", "unknown")
            st.caption(f"Provider: {provider} · Matches: {retrieval.get('match_count', 0)}")
            for query_record in retrieval.get("queries", []):
                event_name = (
                    "All selected events"
                    if query_record["event_id"] == "all_selected_events"
                    else event_by_id[query_record["event_id"]].name
                )
                st.caption(f"{event_name}: {query_record['query']}")
            if retrieval.get("fallback_used"):
                st.warning(
                    "Pinecone was unavailable for this run; local keyword retrieval was used."
                )
            for document in context.get("guidance", []):
                score = document.get("retrieval_score")
                score_text = f" · relevance {score:.3f}" if score is not None else ""
                st.write(f"**{document['title']}**{score_text}")
                st.caption(f"{document['source']} · `{document['id']}`")
                st.write(document["text"])


brand, household = st.columns([3, 1])
with brand:
    st.html('<div class="brand">Everyday <span>/</span> together</div>')
with household:
    st.html(
        f'<div class="household"><span class="avatar">R</span> {escape(dataset.household.name)}</div>'
    )
page = st.radio(
    "Navigation",
    ["Overview", "Wardrobe", "Events", "Family", "Plan outfits"],
    horizontal=True,
    label_visibility="collapsed",
    key="page",
)
if st.session_state.get("planning_job") is not None:
    render_planning_progress()
if planning_error := st.session_state.pop("planning_error", None):
    st.error(planning_error)

if page == "Overview":
    heading, action = st.columns([3, 1], vertical_alignment="center")
    with heading:
        st.html('<div class="eyebrow">A little planning. A lighter morning.</div>')
        st.title("Life happens. Let’s get dressed.")
        st.write("Thoughtful outfits for your family, starting with what you own.")
    with action:
        st.button("Plan outfits ↗", type="primary", on_click=navigate, args=("Plan outfits",))
    events = sorted(dataset.events, key=lambda e: e.date)
    upcoming = [e for e in events if e.date >= datetime.now().astimezone().date()]
    featured = (upcoming or events)[0] if events else None
    if featured:
        with st.container(key="occasion"):
            copy, art = st.columns([1.25, 1], vertical_alignment="center")
            with copy:
                st.html(
                    '<div class="eyebrow">'
                    + ("Your next occasion" if upcoming else "Explore a sample occasion")
                    + "</div>"
                )
                st.subheader(featured.name)
                st.write(f"{featured.date:%a, %b %d} · {featured.location}")
                st.caption(
                    featured.dress_code.replace("_", " ").title()
                    + " · "
                    + ", ".join(member_by_id[mid].name for mid in featured.participant_ids)
                )
                if featured.notes:
                    st.write(featured.notes)
                st.button(
                    "Plan for this event →", on_click=navigate, args=("Plan outfits", featured.id)
                )
            with art:
                st.html(
                    '<div class="hero-art">'
                    + illustration("top", "teal", "Teal top")
                    + illustration("bottom", "navy", "Navy trousers")
                    + illustration("one_piece", "coral", "Coral dress")
                    + "</div>"
                )
                st.caption("Easy layers · Everyday comfort · Room to play")
    st.subheader("Everyone’s own style.")
    family_cards()
elif page == "Family":
    st.title("Different people. Personal preferences.")
    st.write("Comfort comes first, for everyone.")
    family_cards()
elif page == "Wardrobe":
    st.title("Good things, already yours.")
    st.write("Explore your family’s closet, one person at a time.")
    owner, category = st.columns(2)
    with owner:
        selected_member = st.selectbox(
            "Family member",
            list(member_by_id),
            format_func=lambda mid: member_by_id[mid].name,
            key="owner",
        )
    with category:
        selected_category = st.selectbox(
            "Category",
            ["All", "top", "bottom", "one_piece", "outerwear", "footwear", "accessory"],
            format_func=lambda v: v.replace("_", " ").title(),
        )
    items = [
        i
        for i in dataset.wardrobe_items
        if i.member_id == selected_member
        and (selected_category == "All" or i.category == selected_category)
    ]
    st.caption(
        f"{len(items)} pieces · Illustrations show category and color; item photos aren’t available yet."
    )
    if not items:
        st.info("No pieces in this category yet. Try another category.")
    for start in range(0, len(items), 3):
        for column, item in zip(st.columns(3), items[start : start + 3]):
            with column, st.container(border=True):
                st.html(illustration(item.category, item.color, item.name))
                st.markdown(f"**{item.name}**")
                st.caption(f"{item.color.title()} · {item.formality.replace('_', ' ').title()}")
                st.write("Available" if item.available else "Unavailable")
                with st.expander("Item details"):
                    st.write(f"**Warmth:** {item.warmth.title()}")
                    st.write("**Occasions:** " + ", ".join(item.occasion_tags))
                    if item.notes:
                        st.write(item.notes)
elif page == "Events":
    st.title("A little planning. A lighter morning.")
    st.write("Bring the whole family’s outfits together, occasion by occasion.")
    for event in sorted(dataset.events, key=lambda e: e.date):
        with st.container(border=True):
            details, action = st.columns([3, 1], vertical_alignment="center")
            with details:
                st.caption(f"{event.date:%A, %B %d, %Y} · {event.location}")
                st.subheader(event.name)
                st.write(
                    event.dress_code.replace("_", " ").title()
                    + " · "
                    + ", ".join(member_by_id[mid].name for mid in event.participant_ids)
                )
                st.caption(" · ".join(event.activities).capitalize())
            with action:
                st.button(
                    "Plan this event →",
                    key=f"plan_{event.id}",
                    on_click=navigate,
                    args=("Plan outfits", event.id),
                )
else:
    st.title("Let’s make getting dressed easier.")
    st.write(
        "Choose your occasions. We’ll start with your wardrobe and highlight any missing pieces."
    )
    st.session_state.setdefault("selected_events", dataset.demo_request.event_ids)
    selected_events = st.multiselect(
        "What are you dressing for?",
        list(event_by_id),
        key="selected_events",
        format_func=lambda eid: event_by_id[eid].name,
    )
    participants = list(
        dict.fromkeys(mid for eid in selected_events for mid in event_by_id[eid].participant_ids)
    )
    st.caption(
        "Planning for: "
        + (", ".join(member_by_id[mid].name for mid in participants) or "Choose an event above")
    )
    budget = st.number_input(
        "Maximum budget for new items ($)",
        min_value=0.0,
        max_value=float(dataset.household.planning_budget),
        value=float(dataset.demo_request.purchase_budget),
        step=5.0,
    )
    with st.expander("Planning options"):
        backend = st.radio(
            "Planning backend",
            ["Nebius live", "Demo-safe local"],
            horizontal=True,
            help=(
                "Live gathers context locally, then uses one AI request to create the plan. "
                "Local works offline."
            ),
        )
        if backend == "Nebius live":
            st.caption(
                "Live planning usually takes about a minute while the AI builds all family outfits."
            )
    active_job = st.session_state.get("planning_job")
    job_running = active_job is not None and not active_job.done()
    if st.button(
        "Generate family plan",
        type="primary",
        disabled=not selected_events or job_running,
    ):
        st.session_state.pop("planning_state", None)
        st.session_state.pop("planning_error", None)
        request_dataset = dataset.model_copy(deep=True)
        request_dataset.demo_request.event_ids = selected_events
        request_dataset.demo_request.purchase_budget = budget
        request_dataset.demo_request.user_message = (
            "Plan outfits for "
            + ", ".join(event_by_id[eid].name for eid in selected_events)
            + f". Use owned items first, coordinate without identical outfits, and keep all suggested purchases within ${budget:.0f} total."
        )
        runner = run_nebius_workflow if backend == "Nebius live" else run_demo_workflow
        st.session_state["planning_job"] = planning_executor().submit(runner, request_dataset)
        st.rerun()
    planning_state = st.session_state.get("planning_state")
    if planning_state:
        request = planning_state["request"]
        if request["event_ids"] == selected_events and request["purchase_budget"] == budget:
            render_results(planning_state)
        else:
            st.info(
                "Your selections have changed. Generate a new plan to use these events and budget."
            )

st.divider()
st.caption(
    f"{dataset.household.name} · {len(dataset.family_members)} people · {len(dataset.wardrobe_items)} wardrobe items · Fictional demo household"
)
