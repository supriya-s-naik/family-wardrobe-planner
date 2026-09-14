# Multimodal wardrobe intake

## User flow

1. Open **Wardrobe** and choose **Add item**.
2. Upload one JPG, PNG, or WebP image, up to 8 MB.
3. Choose **Analyze photo with AI**.
4. Review the suggested name, category, color, formality, seasons, warmth, and occasion tags.
5. Correct any field and choose **Add to wardrobe**.
6. The item and photo become available to planning for the rest of the app session.

The review form is the human-in-the-loop boundary. Vision output is a suggestion and does
not become authoritative inventory data until the user submits the form.

## Technical flow

The application base64-encodes the uploaded image and sends it directly to the
OpenAI-compatible Nebius Chat Completions endpoint. The vision model returns a strict
Pydantic-derived JSON schema. The planner continues to use the existing Qwen model.

```text
Uploaded image
    → Nebius Gemma vision model
    → WardrobeImageAnalysis schema
    → editable Streamlit form
    → validated WardrobeItem
    → session inventory
    → LangGraph planning context
```

Configuration:

```text
NEBIUS_VISION_MODEL=google/gemma-3-27b-it
```

The adapter accepts `image/jpeg`, `image/png`, and `image/webp`. It rejects empty images,
unsupported media types, and files larger than 8 MB. Analysis results are cached by image
hash for the current session so the same upload is not billed twice.

## Demo and evaluation checks

- Use a clear photo containing one primary garment or accessory.
- Confirm that all suggested fields remain editable.
- Correct at least one field during the demo to show human review.
- Save the item and confirm that it appears for the chosen family member.
- Generate a plan and confirm that the new item can enter the authoritative wardrobe context.
- Keep a manual-entry path available if vision inference is unavailable.

The live smoke command verifies image input and structured output without printing the API
key:

```powershell
uv run python scripts/smoke_test_vision.py path\to\garment.jpg
```
