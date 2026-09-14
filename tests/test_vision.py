import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wardrobe_planner.adapters.nebius import MAX_IMAGE_BYTES, NebiusModel
from wardrobe_planner.config import Settings


def vision_model() -> NebiusModel:
    return NebiusModel(
        Settings(
            nebius_api_key="test-key",
            nebius_base_url="https://example.invalid/v1/",
            nebius_model="planning-model",
            nebius_vision_model="vision-model",
        )
    )


def test_analyze_wardrobe_image_sends_image_and_validates_schema():
    model = vision_model()
    response_content = json.dumps(
        {
            "name": "Blue denim jacket",
            "category": "outerwear",
            "color": "blue",
            "formality": "casual",
            "seasons": ["spring", "fall"],
            "warmth": "medium",
            "occasion_tags": ["travel", "outdoor"],
            "description": "A medium-blue denim jacket.",
            "confidence": 0.94,
        }
    )
    create = Mock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_content))]
        )
    )
    model.client.chat.completions.create = create

    result = model.analyze_wardrobe_image(image_bytes=b"image-data", media_type="image/jpeg")

    assert result.category == "outerwear"
    assert result.confidence == 0.94
    request = create.call_args.kwargs
    assert request["model"] == "vision-model"
    image_url = request["messages"][1]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert request["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize(
    ("image_bytes", "media_type", "message"),
    [
        (b"", "image/jpeg", "empty"),
        (b"image", "image/gif", "JPG, PNG, or WebP"),
        (b"x" * (MAX_IMAGE_BYTES + 1), "image/png", "8 MB or smaller"),
    ],
    ids=["empty", "unsupported-type", "too-large"],
)
def test_analyze_wardrobe_image_rejects_invalid_uploads(image_bytes, media_type, message):
    with pytest.raises(ValueError, match=message):
        vision_model().analyze_wardrobe_image(
            image_bytes=image_bytes,
            media_type=media_type,
        )
