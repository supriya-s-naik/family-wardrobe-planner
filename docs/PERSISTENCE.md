# Local application persistence

The Streamlit app stores mutable prototype data in SQLite. By default the database is
`data/wardrobe_planner.db`, which is excluded from Git. Set `WARDROBE_DB_PATH` to use another
location, including a temporary database for tests.

The database currently persists:

- Seeded and user-added wardrobe items.
- Uploaded wardrobe image bytes.
- Wardrobe availability changes.
- Seeded and user-added events.
- Seeded weather attached to events.

Version-controlled JSON remains the bootstrap source for the fictional household, member
profiles, sample catalog, guidance, and initial demo request. Database initialization inserts
new seed records without overwriting local edits, so it is safe to run on every Streamlit rerun.

## Manual persistence check

1. Start the app and add a wardrobe item with a photo.
2. Mark one seeded item unavailable.
3. Add an event.
4. Stop Streamlit completely and start it again.
5. Confirm the item, photo, availability state, and event remain present.
6. Generate a plan and confirm the unavailable item is absent.

Generated-plan persistence is a separate follow-up. Until that is added, a completed plan remains
in the current Streamlit session only.
