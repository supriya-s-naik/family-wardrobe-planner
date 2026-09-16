from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from hashlib import sha256
from html import escape
from pathlib import Path
from uuid import uuid4

import streamlit as st

from wardrobe_planner.adapters.mem0_memory import Mem0PreferenceMemory
from wardrobe_planner.adapters.nebius import NebiusModel
from wardrobe_planner.adapters.sqlite_store import SQLiteApplicationStore
from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.domain.models import Event, WardrobeItem, WeatherSnapshot
from wardrobe_planner.workflow.graph import run_demo_workflow, run_nebius_workflow

ROOT = Path(__file__).resolve().parent
APP_STATE_VERSION = "sqlite-persistence-v11"
st.set_page_config(
    page_title="Everyday / together · Wardrobe Planner", page_icon="🌿", layout="wide"
)
st.html(f"<style>{(ROOT / 'assets' / 'app.css').read_text(encoding='utf-8')}</style>")
seed_dataset = load_seed_dataset(ROOT / "data" / "seed")
application_store = SQLiteApplicationStore.from_env(ROOT / "data" / "wardrobe_planner.db")
application_store.initialize(seed_dataset)

# Carry prototype-session additions into SQLite once when upgrading an active browser session.
legacy_items = st.session_state.pop("session_wardrobe_items", [])
legacy_images = st.session_state.pop("session_wardrobe_images", {})
for legacy_item in legacy_items:
    item = WardrobeItem.model_validate(legacy_item)
    application_store.save_wardrobe_item(
        item,
        image_bytes=legacy_images.get(item.id),
    )
legacy_weather = {
    snapshot.key: snapshot
    for snapshot in (
        WeatherSnapshot.model_validate(row)
        for row in st.session_state.pop("session_weather", [])
    )
}
for legacy_event_data in st.session_state.pop("session_events", []):
    legacy_event = Event.model_validate(legacy_event_data)
    if weather := legacy_weather.get(legacy_event.weather_key):
        application_store.save_event(legacy_event, weather)

dataset = application_store.load_dataset(seed_dataset)
if st.session_state.get("app_state_version") != APP_STATE_VERSION:
    st.session_state.pop("planning_state", None)
    st.session_state.pop("planning_job", None)
    st.session_state.pop("planning_error", None)
    st.session_state["app_state_version"] = APP_STATE_VERSION
st.session_state.setdefault("wardrobe_image_analysis_cache", {})
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


@st.cache_resource
def preference_memory(household_id: str):
    return Mem0PreferenceMemory.from_env(household_id)


@st.fragment(run_every=1)
def render_planning_progress():
    job = st.session_state.get("planning_job")
    if job is None:
        return
    if not job.done():
        st.info("Building your family plan… You can explore another section while this finishes.")
        return

    try:
        planning_state = job.result()
        planning_state["app_state_version"] = APP_STATE_VERSION
        st.session_state["planning_state"] = planning_state
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


def style_item(item_id):
    st.session_state["style_item_id"] = item_id
    st.session_state["style_item_mode"] = "Use if suitable"
    navigate("Plan outfits")


def clear_style_item():
    st.session_state.pop("style_item_id", None)
    st.session_state.pop("style_item_mode", None)


WARDROBE_FORM_KEYS = (
    "new_item_name",
    "new_item_category",
    "new_item_color",
    "new_item_formality",
    "new_item_warmth",
    "new_item_seasons",
    "new_item_occasion_tags",
)


def reset_wardrobe_intake():
    for key in WARDROBE_FORM_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("new_item_photo", None)
    st.session_state.pop("wardrobe_intake_image_hash", None)


def apply_wardrobe_analysis(analysis):
    st.session_state["new_item_name"] = analysis["name"]
    st.session_state["new_item_category"] = analysis["category"]
    st.session_state["new_item_color"] = analysis["color"]
    st.session_state["new_item_formality"] = analysis["formality"]
    st.session_state["new_item_warmth"] = analysis["warmth"]
    st.session_state["new_item_seasons"] = analysis["seasons"]
    st.session_state["new_item_occasion_tags"] = ", ".join(analysis["occasion_tags"])


@st.dialog("Add a wardrobe item")
def add_wardrobe_item_dialog():
    st.write("Upload a photo, let AI suggest the details, and review them before saving.")
    photo = st.file_uploader(
        "Garment or accessory photo",
        type=["jpg", "jpeg", "png", "webp"],
        help="Use one clear garment, pair of shoes, or accessory per photo; maximum 8 MB.",
        key="new_item_photo",
    )
    analysis = None
    image_bytes = photo.getvalue() if photo else b""
    image_hash = sha256(image_bytes).hexdigest() if image_bytes else None
    if image_hash and st.session_state.get("wardrobe_intake_image_hash") != image_hash:
        for key in WARDROBE_FORM_KEYS:
            st.session_state.pop(key, None)
        st.session_state["wardrobe_intake_image_hash"] = image_hash

    cached_analysis = st.session_state["wardrobe_image_analysis_cache"].get(image_hash)
    if cached_analysis:
        analysis = cached_analysis
        if "new_item_name" not in st.session_state:
            apply_wardrobe_analysis(analysis)
    if photo:
        st.image(image_bytes, caption="Photo to analyze", width=220)
    if st.button(
        "✨ Analyze photo with AI",
        disabled=not photo,
        key="analyze_wardrobe_photo",
    ):
        try:
            with st.spinner("Reading the garment and suggesting details…"):
                analysis_model = NebiusModel().analyze_wardrobe_image(
                    image_bytes=image_bytes,
                    media_type=photo.type,
                )
            analysis = analysis_model.model_dump(mode="json")
            st.session_state["wardrobe_image_analysis_cache"][image_hash] = analysis
            apply_wardrobe_analysis(analysis)
        except Exception as error:  # noqa: BLE001 -- Keep manual intake after provider errors.
            st.error("Photo analysis couldn’t finish. Try again or enter the details manually.")
            with st.expander("Technical details"):
                st.code(f"{type(error).__name__}: {error}")

    if analysis:
        st.success(f"AI suggestions ready · {analysis['confidence']:.0%} confidence")
        st.caption(analysis["description"] + " Review and correct any detail before saving.")

    st.session_state.setdefault("new_item_name", "")
    st.session_state.setdefault("new_item_category", "top")
    st.session_state.setdefault("new_item_color", "")
    st.session_state.setdefault("new_item_formality", "casual")
    st.session_state.setdefault("new_item_warmth", "light")
    st.session_state.setdefault("new_item_seasons", ["spring", "fall"])
    st.session_state.setdefault("new_item_occasion_tags", "")

    with st.form("add_wardrobe_item_form"):
        name = st.text_input("Item name", placeholder="Blue denim jacket", key="new_item_name")
        member_id = st.selectbox(
            "Belongs to",
            list(member_by_id),
            format_func=lambda mid: member_by_id[mid].name,
        )
        category, color = st.columns(2)
        with category:
            item_category = st.selectbox(
                "Category",
                ["top", "bottom", "one_piece", "outerwear", "footwear", "accessory"],
                format_func=lambda value: value.replace("_", " ").title(),
                key="new_item_category",
            )
        with color:
            item_color = st.text_input("Color", placeholder="Blue", key="new_item_color")
        formality, warmth = st.columns(2)
        with formality:
            item_formality = st.selectbox(
                "Style",
                ["casual", "smart_casual", "formal", "festive"],
                format_func=lambda value: value.replace("_", " ").title(),
                key="new_item_formality",
            )
        with warmth:
            item_warmth = st.selectbox(
                "Warmth", ["light", "medium", "warm"], key="new_item_warmth"
            )
        seasons = st.multiselect(
            "Seasons",
            ["spring", "summer", "fall", "winter"],
            key="new_item_seasons",
        )
        occasion_tags = st.text_input(
            "Good for",
            placeholder="school, work, travel, outdoor",
            key="new_item_occasion_tags",
        )
        submitted = st.form_submit_button("Add to wardrobe", type="primary")

    if submitted:
        if not name.strip() or not item_color.strip() or not seasons:
            st.error("Add an item name, color, and at least one season.")
            return
        item_id = f"session_item_{uuid4().hex[:10]}"
        item = WardrobeItem(
            id=item_id,
            member_id=member_id,
            name=name.strip(),
            category=item_category,
            color=item_color.strip().lower(),
            formality=item_formality,
            seasons=seasons,
            warmth=item_warmth,
            occasion_tags=[tag.strip() for tag in occasion_tags.split(",") if tag.strip()],
            image_path="sqlite_upload" if photo else None,
            notes="Added through wardrobe intake.",
        )
        application_store.save_wardrobe_item(
            item,
            image_bytes=photo.getvalue() if photo else None,
            image_media_type=photo.type if photo else None,
        )
        st.session_state["wardrobe_notice"] = f"{item.name} was added for {member_by_id[member_id].name}."
        st.rerun()


@st.dialog("Add an event")
def add_event_dialog():
    st.write("Add an occasion now so the family can start planning ahead.")
    with st.form("add_event_form"):
        name = st.text_input("Event name", placeholder="Family birthday dinner")
        event_date, location = st.columns(2)
        with event_date:
            date_value = st.date_input("Date")
        with location:
            location_value = st.text_input("Location", placeholder="San Jose, CA")
        participants = st.multiselect(
            "Who is attending?",
            list(member_by_id),
            default=list(member_by_id),
            format_func=lambda mid: member_by_id[mid].name,
        )
        event_type = st.text_input("Occasion type", placeholder="birthday dinner")
        dress_code, setting = st.columns(2)
        with dress_code:
            dress_code_value = st.selectbox(
                "Dress code",
                ["casual", "smart_casual", "formal", "festive"],
                format_func=lambda value: value.replace("_", " ").title(),
            )
        with setting:
            setting_value = st.selectbox("Setting", ["indoor", "outdoor", "mixed"])
        activities = st.text_input("Activities", placeholder="dinner, photos, walking")
        expected_weather = st.selectbox(
            "Expected weather",
            ["Mild and dry", "Warm and sunny", "Cool with possible rain"],
        )
        notes = st.text_area("Anything else the planner should know?", height=80)
        submitted = st.form_submit_button("Add event", type="primary")

    if submitted:
        if not name.strip() or not location_value.strip() or not participants:
            st.error("Add an event name, location, and at least one family member.")
            return
        weather_presets = {
            "Mild and dry": ("mild and dry", 72, 55, 5, 7),
            "Warm and sunny": ("warm and sunny", 86, 64, 0, 6),
            "Cool with possible rain": ("cool with possible showers", 61, 49, 45, 14),
        }
        event_id = f"session_event_{uuid4().hex[:10]}"
        weather_key = f"weather_{event_id}"
        condition, high_f, low_f, rain, wind = weather_presets[expected_weather]
        event = Event(
            id=event_id,
            household_id=dataset.household.id,
            name=name.strip(),
            date=date_value,
            location=location_value.strip(),
            participant_ids=participants,
            event_type=event_type.strip() or "family event",
            dress_code=dress_code_value,
            setting=setting_value,
            activities=[activity.strip() for activity in activities.split(",") if activity.strip()]
            or ["socializing"],
            weather_key=weather_key,
            notes=notes.strip() or None,
        )
        weather = WeatherSnapshot(
            key=weather_key,
            condition=condition,
            high_f=high_f,
            low_f=low_f,
            precipitation_probability=rain,
            wind_mph=wind,
        )
        application_store.save_event(event, weather)
        st.session_state["events_notice"] = f"{event.name} was added and is ready to plan."
        st.rerun()


@st.dialog("Sync your calendar")
def sync_calendar_dialog():
    st.write(
        "Connect a calendar to import upcoming occasions, dates, locations, and attendees. "
        "You can review every event before wardrobe planning begins."
    )
    provider = st.radio("Calendar provider", ["Google Calendar", "Microsoft Outlook"])
    st.caption("Calendar authorization is represented in this prototype; no account data is accessed.")
    if st.button("Connect and import events", type="primary", key="connect_calendar"):
        st.session_state["events_notice"] = (
            f"{provider} is ready for OAuth integration. No calendar data was accessed."
        )
        st.rerun()


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


def memory_manager():
    st.subheader("Remembered preferences")
    st.write(
        "Save a lasting preference only when someone has clearly expressed it. "
        "Mem0 keeps each family member’s memories separate."
    )
    selected_member_id = st.selectbox(
        "Family member",
        list(member_by_id),
        format_func=lambda member_id: member_by_id[member_id].name,
        key="memory_member_id",
    )
    try:
        store = preference_memory(dataset.household.id)
    except RuntimeError:
        st.warning("Mem0 is unavailable. Add MEM0_API_KEY to enable durable preferences.")
        return

    memory_cache = st.session_state.setdefault("member_memory_cache", {})
    refresh_requested = st.button("Refresh from Mem0", key="refresh_memories")
    if selected_member_id not in memory_cache or refresh_requested:
        try:
            memory_cache[selected_member_id] = store.list_preferences(selected_member_id)
        except Exception:  # noqa: BLE001 -- keep the preference UI usable after provider failure.
            st.error("Mem0 couldn’t load preferences. Please try again.")
            memory_cache.setdefault(selected_member_id, [])

    with st.form("save_preference_form", clear_on_submit=True):
        preference_text = st.text_area(
            "Preference to remember",
            placeholder="Example: Maya prefers flats for events with extensive walking.",
        )
        preference_category = st.selectbox(
            "Preference category",
            ["comfort", "footwear", "color", "style", "cultural", "outfit_repeat"],
        )
        save_preference = st.form_submit_button("Remember preference", type="primary")
    if save_preference:
        if not preference_text.strip():
            st.warning("Enter a preference before saving.")
        else:
            try:
                store.save_preference(
                    selected_member_id,
                    preference_text,
                    preference_category,
                )
                memory_cache[selected_member_id] = store.list_preferences(selected_member_id)
                st.success(
                    f"Preference saved for {member_by_id[selected_member_id].name}."
                )
            except Exception:  # noqa: BLE001 -- provider details stay behind the UI boundary.
                st.error("Mem0 couldn’t save this preference. Please try again.")

    memories = memory_cache.get(selected_member_id, [])
    if not memories:
        st.info(f"No durable preferences saved for {member_by_id[selected_member_id].name} yet.")
        return
    for memory in memories:
        with st.container(border=True):
            details, action = st.columns([5, 1], vertical_alignment="center")
            with details:
                st.write(memory["text"])
                st.caption(f"{memory['category'].replace('_', ' ').title()} · Mem0")
            with action:
                memory_id = memory.get("id")
                if st.button(
                    "Delete",
                    key=f"delete_memory_{memory_id}",
                    disabled=not memory_id,
                ):
                    try:
                        store.delete_preference(memory_id)
                        memory_cache[selected_member_id] = [
                            row for row in memories if row.get("id") != memory_id
                        ]
                        st.rerun()
                    except Exception:  # noqa: BLE001
                        st.error("Mem0 couldn’t delete this preference. Please try again.")


def render_results(state):
    result = state["final_result"]
    preferred_item_ids = set(state["request"].get("preferred_item_ids", []))
    required_item_ids = set(state["request"].get("required_item_ids", []))
    styled_item_ids = preferred_item_ids | required_item_ids
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
                    marker = "★ " if item_id in styled_item_ids else "• "
                    st.write(marker + item_by_id[item_id].name)
                st.caption(outfit["rationale"])
    used_item_ids = {
        item_id for outfit in result.get("outfits", []) for item_id in outfit["item_ids"]
    }
    for preferred_item_id in preferred_item_ids - used_item_ids:
        preferred_item = item_by_id.get(preferred_item_id)
        if preferred_item is not None:
            st.info(
                f"{preferred_item.name} was considered but not selected under “Use if suitable.” "
                "Choose “Must use” to make it a validated requirement."
            )
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
            guidance = context.get("guidance", [])
            retrieval = context.get("retrieval_metadata", {})
            st.markdown("#### Retrieved guidance")
            providers = {
                document.get("retrieval_provider")
                for document in guidance
                if document.get("retrieval_provider")
            }
            provider = retrieval.get("provider") or (
                providers.pop() if len(providers) == 1 else "unknown"
            )
            match_count = retrieval.get("match_count", len(guidance))
            st.caption(f"Provider: {provider} · Matches: {match_count}")
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
            for document in guidance:
                score = document.get("retrieval_score")
                score_text = f" · relevance {score:.3f}" if score is not None else ""
                st.write(f"**{document['title']}**{score_text}")
                st.caption(f"{document['source']} · `{document['id']}`")
                st.write(document["text"])
        memory_record = next(
            (
                record
                for record in state.get("tool_results", [])
                if record["name"] == "search_memories"
            ),
            None,
        )
        if memory_record:
            memory_context = memory_record["result"]
            memory_retrieval = memory_context.get("retrieval_metadata", {})
            st.markdown("#### Remembered preferences")
            st.caption(
                f"Provider: {memory_retrieval.get('provider', 'unknown')} · "
                f"Matches: {memory_retrieval.get('match_count', 0)}"
            )
            if memory_retrieval.get("fallback_used"):
                st.warning(
                    "Mem0 was unavailable for this run; planning continued with saved family "
                    "profile preferences only."
                )
            for member_id, memories in memory_context.get("memories_by_member", {}).items():
                for memory in memories:
                    st.write(f"**{member_by_id[member_id].name}:** {memory['text']}")


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
    memory_manager()
elif page == "Wardrobe":
    st.title("Good things, already yours.")
    st.write("Explore your family’s closet, one person at a time.")
    action, _ = st.columns([1, 4])
    with action:
        if st.button("＋ Add item", type="primary", key="add_wardrobe_item"):
            reset_wardrobe_intake()
            add_wardrobe_item_dialog()
    if wardrobe_notice := st.session_state.pop("wardrobe_notice", None):
        st.success(wardrobe_notice)
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
        f"{len(items)} pieces · Uploaded photos appear when available; seeded items use illustrations."
    )
    if not items:
        st.info("No pieces in this category yet. Try another category.")
    for start in range(0, len(items), 3):
        for column, item in zip(st.columns(3), items[start : start + 3]):
            with column, st.container(border=True):
                uploaded_image = application_store.get_wardrobe_image(item.id)
                if uploaded_image:
                    st.image(uploaded_image, caption=item.name, use_container_width=True)
                else:
                    st.html(illustration(item.category, item.color, item.name))
                st.markdown(f"**{item.name}**")
                st.caption(f"{item.color.title()} · {item.formality.replace('_', ' ').title()}")
                st.write("Available" if item.available else "Unavailable")
                with st.expander("Item details"):
                    st.write(f"**Warmth:** {item.warmth.title()}")
                    st.write("**Occasions:** " + ", ".join(item.occasion_tags))
                    if item.notes:
                        st.write(item.notes)
                style_action, availability_action = st.columns(2)
                with style_action:
                    st.button(
                        "Style this item →",
                        key=f"style_{item.id}",
                        on_click=style_item,
                        args=(item.id,),
                        disabled=not item.available,
                    )
                with availability_action:
                    planning_job = st.session_state.get("planning_job")
                    planning_is_running = planning_job is not None and not planning_job.done()
                    if st.button(
                        "Mark unavailable" if item.available else "Mark available",
                        key=f"availability_{item.id}",
                        disabled=planning_is_running,
                    ):
                        updated_item = application_store.set_wardrobe_item_availability(
                            item.id, not item.available
                        )
                        if not updated_item.available and st.session_state.get(
                            "style_item_id"
                        ) == item.id:
                            clear_style_item()
                        st.session_state.pop("planning_state", None)
                        status = "available" if updated_item.available else "unavailable"
                        st.session_state["wardrobe_notice"] = (
                            f"{updated_item.name} is now {status}. Generate a new plan to use "
                            "the updated wardrobe."
                        )
                        st.rerun()
elif page == "Events":
    st.title("A little planning. A lighter morning.")
    st.write("Bring the whole family’s outfits together, occasion by occasion.")
    add_action, sync_action, _ = st.columns([1, 1.2, 3])
    with add_action:
        if st.button("＋ Add event", type="primary", key="add_event"):
            add_event_dialog()
    with sync_action:
        if st.button("↻ Sync calendar", key="sync_calendar"):
            sync_calendar_dialog()
    if events_notice := st.session_state.pop("events_notice", None):
        st.success(events_notice)
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
    styled_item_id = st.session_state.get("style_item_id")
    styled_item = item_by_id.get(styled_item_id)
    if styled_item_id and styled_item is None:
        clear_style_item()
        styled_item_id = None
    if styled_item is not None:
        with st.container(border=True):
            item_details, item_action = st.columns([4, 1], vertical_alignment="center")
            with item_details:
                owner_name = member_by_id[styled_item.member_id].name
                st.markdown(f"**Styling around {styled_item.name} for {owner_name}**")
                st.caption(
                    f"{styled_item.color.title()} · "
                    f"{styled_item.formality.replace('_', ' ').title()} · "
                    f"{', '.join(styled_item.seasons).title()}"
                )
            with item_action:
                st.button("Remove", key="clear_style_item", on_click=clear_style_item)
            style_item_mode = st.selectbox(
                "How should the planner use it?",
                ["Use if suitable", "Must use"],
                key="style_item_mode",
                help=(
                    "Use if suitable is a preference the planner may decline with a reason. "
                    "Must use is a hard constraint checked by the validator."
                ),
            )
    else:
        style_item_mode = "Use if suitable"
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
    style_item_applies = styled_item is None or styled_item.member_id in participants
    if styled_item is not None and not style_item_applies:
        st.warning(
            f"Choose an event attended by {member_by_id[styled_item.member_id].name} "
            f"to style {styled_item.name}."
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
        disabled=not selected_events or job_running or not style_item_applies,
        key="generate_plan",
    ):
        st.session_state.pop("planning_state", None)
        st.session_state.pop("planning_error", None)
        request_dataset = dataset.model_copy(deep=True)
        request_dataset.demo_request.event_ids = selected_events
        request_dataset.demo_request.purchase_budget = budget
        request_dataset.demo_request.preferred_item_ids = []
        request_dataset.demo_request.required_item_ids = []
        item_instruction = ""
        if styled_item is not None:
            if style_item_mode == "Must use":
                request_dataset.demo_request.required_item_ids = [styled_item.id]
                item_instruction = (
                    f" Required constraint: use {styled_item.name} ({styled_item.id}) in every "
                    f"selected outfit for {member_by_id[styled_item.member_id].name}."
                )
            else:
                request_dataset.demo_request.preferred_item_ids = [styled_item.id]
                item_instruction = (
                    f" Prefer {styled_item.name} ({styled_item.id}) for "
                    f"{member_by_id[styled_item.member_id].name} when it suits the event and "
                    "conditions; otherwise explain why it was skipped."
                )
        request_dataset.demo_request.user_message = (
            "Plan outfits for "
            + ", ".join(event_by_id[eid].name for eid in selected_events)
            + f". Use owned items first, coordinate without identical outfits, and keep all suggested purchases within ${budget:.0f} total."
            + item_instruction
        )
        if backend == "Nebius live":
            runner = run_nebius_workflow
        else:
            cached_memories = {
                member_id: [dict(memory) for memory in memories]
                for member_id, memories in st.session_state.get(
                    "member_memory_cache", {}
                ).items()
            }
            if any(cached_memories.values()):
                def search_cached_memories(member_id: str, _query: str, limit: int):
                    return cached_memories.get(member_id, [])[:limit]

                runner = partial(
                    run_demo_workflow,
                    memory_search=search_cached_memories,
                )
            else:
                runner = run_demo_workflow
        st.session_state["planning_job"] = planning_executor().submit(runner, request_dataset)
        st.rerun()
    if st.session_state.get("planning_job") is not None:
        render_planning_progress()
    if planning_error := st.session_state.pop("planning_error", None):
        st.error(planning_error)
    planning_state = st.session_state.get("planning_state")
    if planning_state:
        if planning_state.get("app_state_version") != APP_STATE_VERSION:
            st.session_state.pop("planning_state", None)
            st.info("The app was updated. Generate a fresh plan to continue.")
        else:
            request = planning_state["request"]
            expected_preferred = (
                [styled_item.id]
                if styled_item is not None and style_item_mode == "Use if suitable"
                else []
            )
            expected_required = (
                [styled_item.id]
                if styled_item is not None and style_item_mode == "Must use"
                else []
            )
            if (
                request["event_ids"] == selected_events
                and request["purchase_budget"] == budget
                and request.get("preferred_item_ids", []) == expected_preferred
                and request.get("required_item_ids", []) == expected_required
            ):
                render_results(planning_state)
            else:
                st.info(
                    "Your selections have changed. Generate a new plan to use these events and budget."
                )

st.divider()
st.caption(
    f"{dataset.household.name} · {len(dataset.family_members)} people · {len(dataset.wardrobe_items)} wardrobe items · Fictional demo household"
)
