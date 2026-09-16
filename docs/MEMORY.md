# Durable preference memory

## User flow

1. Open **Family**.
2. Choose a family member under **Remembered preferences**.
3. Enter a durable preference the person has explicitly expressed.
4. Choose a category and select **Remember preference**.
5. Generate a new outfit plan.
6. Open **Planning details** to inspect the `search_memories` tool call and the exact
   member-scoped memories returned by Mem0.
7. Return to **Family** to review or delete a memory.

A useful demo preference is: “Maya prefers flats for events with extensive walking.” Plan the
Santa Cruz outing before and after saving it, then compare Maya’s footwear and rationale.

## Boundaries

- Memories are saved only through an explicit user action.
- Each Mem0 `user_id` combines the stable household and member IDs.
- Searches always use that member-specific `user_id` filter.
- A retrieved memory is a soft preference. Current requests, ownership, availability, event
  requirements, and validator rules take precedence.
- Mem0 failure does not stop planning. The run is visibly marked as a memory fallback and uses
  the family profile preferences already present in authoritative application data.
- Users can inspect and delete their remembered preferences.

## Technical flow

```text
Explicit preference
    → member-scoped Mem0 add
    → later search_memories workflow tool
    → member-isolated planning context
    → Nebius or local planner
    → deterministic validation
```

The adapter uses Mem0 Platform’s current v3 behavior: `add` receives the scoped `user_id`, while
`search` and `get_all` place it inside the `filters` object.

Run the reversible live smoke check with:

```powershell
uv run python scripts/smoke_test_mem0.py
```

The script adds a uniquely marked temporary preference for Maya, verifies member-scoped semantic
search, and deletes the temporary record before exiting.
