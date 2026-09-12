from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str
    nebius_base_url: str
    nebius_model: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        missing = [
            name
            for name in ("NEBIUS_API_KEY", "NEBIUS_BASE_URL", "NEBIUS_MODEL")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(f"Missing required environment settings: {', '.join(missing)}")
        return cls(
            nebius_api_key=os.environ["NEBIUS_API_KEY"],
            nebius_base_url=os.environ["NEBIUS_BASE_URL"].rstrip("/") + "/",
            nebius_model=os.environ["NEBIUS_MODEL"],
        )

