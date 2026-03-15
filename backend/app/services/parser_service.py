import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.schemas.parser import MultiParseResult, ParseResult
from app.services.config_loader import load_yaml


@dataclass(slots=True)
class PatternSpec:
    name: str
    regex: str


class ParserService:
    MERCHANT_HINTS = {
        "золотое яблоко": "Золотое яблоко",
        "золотом яблоке": "Золотое яблоко",
        "ozon": "Ozon",
        "озон": "Ozon",
        "wildberries": "Wildberries",
        "wb": "Wildberries",
        "вб": "Wildberries",
        "самокат": "Самокат",
        "самокате": "Самокат",
        "вкусвилл": "ВкусВилл",
        "пятерка": "Пятёрочка",
        "пятёрка": "Пятёрочка",
        "перекресток": "Перекрёсток",
        "перекрёсток": "Перекрёсток",
        "магнит": "Магнит",
    }

    def __init__(self) -> None:
        self.categories_config = load_yaml("categories.yaml")
        self.verbs_config = load_yaml("verbs.yaml")
        self.patterns_config = load_yaml("patterns.yaml")
        self.category_lookup = self._build_category_lookup()
        self.verb_lookup = self._build_verb_lookup()
        self.patterns = [
            PatternSpec(name=item["name"], regex=item["regex"])
            for item in self.patterns_config["ru"]["patterns"]
        ]

    def parse(self, text: str) -> ParseResult:
        normalized = self._normalize(text)
        if not normalized:
            return self._fallback(text)

        amount_only = self._extract_amount(normalized)
        for pattern in self.patterns:
            match = re.match(pattern.regex, normalized, flags=re.IGNORECASE)
            if not match:
                continue
            return self._build_result(pattern.name, normalized, match.groupdict())

        if amount_only is not None:
            return ParseResult(
                matched=False,
                confidence=0.3,
                confidence_label="low",
                transaction_type=None,
                amount=amount_only,
                category=None,
                description=None,
                pattern=None,
                raw_input=text,
            )

        return self._fallback(text)

    def parse_many(self, text: str) -> MultiParseResult:
        normalized = self._normalize(text)
        if not normalized:
            return MultiParseResult(items=[], raw_input=text)

        segments = self._split_into_segments(normalized)
        items: list[ParseResult] = []
        for segment in segments:
            result = self.parse(segment)
            if result.amount is not None and result.amount > 0:
                items.append(result)
        return MultiParseResult(items=items, raw_input=text)

    def _split_into_segments(self, text: str) -> list[str]:
        text = re.sub(
            r",\s+(?=(?:я\s+)?(?:потратил|потратила|потратили|заплатил|заплатила|заплатили|купил|купила|купили|получил|получила|получили|заработал|заработала|заработали|пришло|капнуло))",
            " | ",
            text,
            flags=re.IGNORECASE,
        )
        pieces = re.split(r"\s+(?:и|потом|затем)\s+|\s*\|\s*", text)
        segments: list[str] = []
        for piece in pieces:
            part = piece.strip(" ,.")
            if not part:
                continue
            segments.append(part)
        return segments

    def _build_result(self, pattern_name: str, raw_input: str, groups: dict[str, str]) -> ParseResult:
        amount = self._extract_amount(groups.get("amount", ""))
        if amount is None:
            return self._fallback(raw_input)

        transaction_type = self._resolve_type(groups)
        category, description = self._resolve_category_and_description(groups)

        if category is not None:
            return ParseResult(
                matched=True,
                confidence=0.95,
                confidence_label="high",
                transaction_type=transaction_type or "expense",
                amount=amount,
                category=category,
                description=description,
                pattern=pattern_name,
                raw_input=raw_input,
            )

        if groups.get("desc") or groups.get("category"):
            fallback_label = "low" if pattern_name == "P5" and transaction_type is None else "medium"
            fallback_confidence = 0.3 if fallback_label == "low" else 0.6
            fallback_type = transaction_type if fallback_label == "low" else (transaction_type or "expense")
            fallback_category = None if fallback_label == "low" else "other"
            return ParseResult(
                matched=True,
                confidence=fallback_confidence,
                confidence_label=fallback_label,
                transaction_type=fallback_type,
                amount=amount,
                category=fallback_category,
                description=(groups.get("desc") or groups.get("category") or "").strip() or None,
                pattern=pattern_name,
                raw_input=raw_input,
            )

        return ParseResult(
            matched=False,
            confidence=0.3,
            confidence_label="low",
            transaction_type=transaction_type,
            amount=amount,
            category=None,
            description=None,
            pattern=pattern_name,
            raw_input=raw_input,
        )

    def _resolve_type(self, groups: dict[str, str]) -> str | None:
        explicit_type = (groups.get("type") or "").strip().lower()
        if explicit_type in {"доход", "+", "income"}:
            return "income"
        if explicit_type in {"расход", "expense", "-"}:
            return "expense"

        sign = (groups.get("sign") or "").strip()
        if sign == "+":
            return "income"
        if sign == "-":
            return "expense"

        verb = (groups.get("verb") or "").strip().lower()
        return self.verb_lookup.get(verb)

    def _resolve_category_and_description(self, groups: dict[str, str]) -> tuple[str | None, str | None]:
        category_raw = self._cleanup_desc((groups.get("category") or "").strip().lower())
        if category_raw:
            category = self._find_category_in_text(category_raw)
            if category:
                description = self._extract_merchant_description(category_raw, category)
                return category, description
            return None, category_raw

        desc_raw = self._cleanup_desc((groups.get("desc") or "").strip().lower())
        if not desc_raw:
            return None, None

        category = self._find_category_in_text(desc_raw)
        if category:
            description = self._extract_merchant_description(desc_raw, category)
            return category, description
        return None, desc_raw

    def _extract_merchant_description(self, text: str, category: str) -> str | None:
        cleaned = text.strip()
        if not cleaned:
            return None

        for merchant, canonical in sorted(self.MERCHANT_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
            if merchant in cleaned:
                return canonical

        # Keep composite/free-form descriptions when they contain more than category words.
        category_terms = self._category_terms(category)
        text_terms = set(cleaned.split())
        if text_terms - category_terms:
            return cleaned
        return None

    def _category_terms(self, category: str) -> set[str]:
        terms = {category}
        for key, value in self.category_lookup.items():
            if value == category:
                terms.update(key.split())
        return terms

    def _find_category_in_text(self, text: str) -> str | None:
        tokens = re.split(r"\s+", text)
        for size in range(min(4, len(tokens)), 0, -1):
            for start in range(0, len(tokens) - size + 1):
                candidate = " ".join(tokens[start : start + size])
                if candidate in self.category_lookup:
                    return self.category_lookup[candidate]
        return None

    def _build_category_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for item in self.categories_config["ru"]["categories"]:
            slug = item["slug"]
            lookup[slug] = slug
            for synonym in item["synonyms"]:
                lookup[synonym.lower()] = slug
        return lookup

    def normalize_category_candidate(self, text: str) -> str:
        normalized = self._cleanup_desc(self._normalize(text))
        return normalized.strip()

    def detect_merchant_label(self, text: str) -> str | None:
        normalized = self.normalize_category_candidate(text)
        for merchant, canonical in sorted(self.MERCHANT_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
            if merchant in normalized:
                return canonical
        return None

    def extract_category_fragment(self, text: str) -> str:
        normalized = self._normalize(text)
        if not normalized:
            return ""
        normalized = re.sub(r"^\s*(?:расход|доход)\s+", "", normalized)
        normalized = re.sub(r"^\s*(?:я\s+)?(?:потратил|потратила|потратили|заплатил|заплатила|заплатили|купил|купила|купили|получил|получила|получили|заработал|заработала|заработали|пришло|капнуло)\s+", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\d+(?:\.\d{1,2})?", "", normalized)
        normalized = self._cleanup_desc(normalized)
        return normalized.strip()

    def suggest_categories(self, text: str, limit: int = 3) -> list[str]:
        normalized = self._cleanup_desc(self._normalize(text))
        if not normalized:
            return []

        scored: list[tuple[int, str]] = []
        seen: set[str] = set()
        words = set(normalized.split())
        for item in self.categories_config["ru"]["categories"]:
            slug = item["slug"]
            if slug in seen:
                continue
            score = 0
            label_words = set(slug.replace("_", " ").split())
            score += len(words & label_words) * 4
            for synonym in item["synonyms"]:
                synonym_normalized = synonym.lower()
                synonym_words = set(synonym_normalized.split())
                if synonym_normalized in normalized:
                    score += 6
                score += len(words & synonym_words) * 3
            if score > 0:
                scored.append((score, slug))
                seen.add(slug)

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [slug for _, slug in scored[:limit]]

    def _build_verb_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for key, verbs in self.verbs_config["ru"]["verbs"].items():
            for verb in verbs:
                lookup[verb.lower()] = key
        return lookup

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = text.strip().lower().replace("ё", "ё")
        normalized = re.sub(r"[.!?]+$", "", normalized)
        normalized = re.sub(r"\bруб(?:ля|лей)?\b", "", normalized)
        normalized = re.sub(r"\bр\b", "", normalized)
        normalized = normalized.replace("₽", "")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _cleanup_desc(text: str) -> str:
        text = re.sub(r"\b(в|во|на|за|из|у|от)\b\s*", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _extract_amount(text: str) -> Decimal | None:
        cleaned = text.replace("₽", "").replace(",", ".").strip()
        cleaned = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", cleaned)
        match = re.search(r"\d+(?:\.\d{1,2})?", cleaned)
        if not match:
            return None
        try:
            return Decimal(match.group(0))
        except InvalidOperation:
            return None

    @staticmethod
    def _fallback(raw_input: str) -> ParseResult:
        return ParseResult(
            matched=False,
            confidence=0.0,
            confidence_label="fallback",
            transaction_type=None,
            amount=None,
            category=None,
            description=None,
            pattern=None,
            raw_input=raw_input,
        )
