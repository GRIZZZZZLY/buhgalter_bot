"""Read/write categories.yaml using ruamel.yaml (preserves formatting)."""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "config" / "categories.yaml"


class YamlLearnerService:
    def __init__(self, path: Path = CATEGORIES_PATH) -> None:
        self._path = path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True

    def add_synonym(self, category_slug: str, synonym: str) -> bool:
        """Add synonym to existing category. Returns False if slug not found or synonym already exists."""
        data = self._load()
        for cat in data["ru"]["categories"]:
            if cat["slug"] == category_slug:
                if synonym in cat["synonyms"]:
                    return False
                cat["synonyms"].append(synonym)
                self._save(data)
                return True
        return False

    def add_category(self, slug: str, tx_type: str, synonyms: list[str]) -> bool:
        """Add new category entry. Returns False if slug already exists."""
        data = self._load()
        categories = data["ru"]["categories"]
        for cat in categories:
            if cat["slug"] == slug:
                return False
        categories.append({"slug": slug, "type": tx_type, "synonyms": synonyms})
        self._save(data)
        return True

    def _load(self):
        with open(self._path, encoding="utf-8") as f:
            return self._yaml.load(f)

    def _save(self, data) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            self._yaml.dump(data, f)
