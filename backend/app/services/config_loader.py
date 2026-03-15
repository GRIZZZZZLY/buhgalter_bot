from pathlib import Path
from typing import Any

import yaml

BASE_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_yaml(filename: str) -> dict[str, Any]:
    path = BASE_CONFIG_DIR / filename
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)
