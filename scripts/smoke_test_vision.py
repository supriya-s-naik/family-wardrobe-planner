from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from wardrobe_planner.adapters.nebius import NebiusModel


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one wardrobe image with Nebius vision.")
    parser.add_argument("image", type=Path, help="Path to a JPG, PNG, or WebP wardrobe image")
    args = parser.parse_args()
    media_type = mimetypes.guess_type(args.image.name)[0] or "application/octet-stream"
    analysis = NebiusModel().analyze_wardrobe_image(
        image_bytes=args.image.read_bytes(),
        media_type=media_type,
    )
    print(analysis.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
