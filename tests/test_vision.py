import base64
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APITimeoutError
from PIL import Image

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


def sample_image(size=(32, 32)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "blue").save(output, format="PNG")
    return output.getvalue()


def test_analyze_wardrobe_image_sends_image_and_validates_schema():
    model = vision_model()
    response_content = json.dumps(
        {
            "name": "Blue denim jacket",
            "category": "outerwear",
            "garment_type": "jacket",
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

    result = model.analyze_wardrobe_image(
        image_bytes=sample_image(), media_type="image/png"
    )

    assert result.category == "outerwear"
    assert result.garment_type == "jacket"
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


def test_analyze_wardrobe_image_resizes_large_upload_before_sending():
    model = vision_model()
    create = Mock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "name": "Blue top",
                                "category": "top",
                                "garment_type": "shirt",
                                "color": "blue",
                                "formality": "casual",
                                "seasons": ["spring"],
                                "warmth": "light",
                                "occasion_tags": ["everyday"],
                                "description": "A blue top.",
                                "confidence": 0.9,
                            }
                        )
                    )
                )
            ]
        )
    )
    model.client.chat.completions.create = create

    model.analyze_wardrobe_image(
        image_bytes=sample_image((2400, 1800)), media_type="image/png"
    )

    image_url = create.call_args.kwargs["messages"][1]["content"][1]["image_url"]["url"]
    normalized = BytesIO(base64.b64decode(image_url.split(",", 1)[1]))
    with Image.open(normalized) as image:
        assert max(image.size) == 1536


def test_analyze_wardrobe_image_retries_one_transient_timeout():
    model = vision_model()
    successful_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "name": "Floral dress",
                            "category": "one_piece",
                            "garment_type": "dress",
                            "color": "coral",
                            "formality": "smart_casual",
                            "seasons": ["spring", "summer"],
                            "warmth": "light",
                            "occasion_tags": ["brunch"],
                            "description": "A light floral dress.",
                            "confidence": 0.9,
                        }
                    )
                )
            )
        ]
    )
    create = Mock(
        side_effect=[
            APITimeoutError(request=httpx.Request("POST", "https://example.invalid")),
            successful_response,
        ]
    )
    model.client.chat.completions.create = create

    result = model.analyze_wardrobe_image(
        image_bytes=sample_image(), media_type="image/png"
    )

    assert result.category == "one_piece"
    assert create.call_count == 2
