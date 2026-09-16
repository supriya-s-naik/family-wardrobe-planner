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
- Validated family plans, including their request, result, evidence, and workflow metrics.
- Saved plans can be deleted from Events after confirmation; replans remain available and are
  detached from a deleted comparison baseline.

Version-controlled JSON remains the bootstrap source for the fictional household, member
profiles, sample catalog, guidance, and initial demo request. Database initialization inserts
new seed records without overwriting local edits, so it is safe to run on every Streamlit rerun.

## Manual persistence check

1. Start the app and add a wardrobe item with a photo.
2. Mark one seeded item unavailable.
3. Add an event.
4. Stop Streamlit completely and start it again.
5. Confirm the item, photo, availability state, and event remain present.
6. Generate a valid plan and choose **Save family plan**.
7. Open **Events** and confirm the plan appears under **Saved family plans**.
8. Mark one of its wardrobe items unavailable and choose **Review and replan**.
9. Generate the replacement and confirm the comparison lists changed and preserved outfits.
10. Restart Streamlit and reopen the saved plan from **Events**.
