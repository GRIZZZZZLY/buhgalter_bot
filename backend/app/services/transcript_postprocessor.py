import re


class TranscriptPostprocessor:
    STORE_MAP = {
        "самокате": "самокат",
        "самоката": "самокат",
        "вкусвилле": "вкусвилл",
        "вкусвил": "вкусвилл",
        "пятерочке": "пятёрка",
        "пятерочке": "пятёрка",
        "магните": "магнит",
        "перекрестке": "перекрёсток",
        "перекрестоке": "перекрёсток",
    }

    SLANG_MAP = {
        "зп": "зарплата",
        "зарп": "зарплата",
        "продуктосы": "продукты",
        "бабки": "деньги",
        "капнуло": "пришло",
        "упало": "пришло",
        "прилетело": "пришло",
        "вкинул": "потратил",
        "слил": "потратил",
        "занес": "заплатил",
        "занёс": "заплатил",
    }

    NUMBER_MAP = {
        "ноль": 0,
        "один": 1,
        "одна": 1,
        "два": 2,
        "две": 2,
        "три": 3,
        "четыре": 4,
        "пять": 5,
        "шесть": 6,
        "семь": 7,
        "восемь": 8,
        "девять": 9,
        "десять": 10,
        "двадцать": 20,
        "тридцать": 30,
        "сорок": 40,
        "пятьдесят": 50,
        "шестьдесят": 60,
        "семьдесят": 70,
        "восемьдесят": 80,
        "девяносто": 90,
        "сто": 100,
        "двести": 200,
        "триста": 300,
        "четыреста": 400,
        "пятьсот": 500,
        "шестьсот": 600,
        "семьсот": 700,
        "восемьсот": 800,
        "девятьсот": 900,
        "тысяча": 1000,
        "тысячи": 1000,
        "тысяч": 1000,
    }

    def normalize(self, text: str) -> str:
        normalized = text.strip().lower()
        normalized = self._cleanup_punctuation(normalized)
        normalized = self._replace_dictionary(normalized, self.STORE_MAP)
        normalized = self._replace_dictionary(normalized, self.SLANG_MAP)
        normalized = self._replace_number_phrases(normalized)
        normalized = self._normalize_currency(normalized)
        normalized = self._cleanup_spacing(normalized)
        return normalized

    @staticmethod
    def _cleanup_punctuation(text: str) -> str:
        text = text.replace("ё", "ё")
        text = re.sub(r"[\"'`]+", "", text)
        text = re.sub(r"[;:]+", " ", text)
        text = re.sub(r"[.!?]+", ".", text)
        return text

    @staticmethod
    def _replace_dictionary(text: str, mapping: dict[str, str]) -> str:
        for source, target in mapping.items():
            text = re.sub(rf"\b{re.escape(source)}\b", target, text)
        return text

    def _replace_number_phrases(self, text: str) -> str:
        tokens = text.split()
        result: list[str] = []
        i = 0
        while i < len(tokens):
            if tokens[i] not in self.NUMBER_MAP:
                result.append(tokens[i])
                i += 1
                continue

            total = 0
            current = 0
            while i < len(tokens) and tokens[i] in self.NUMBER_MAP:
                value = self.NUMBER_MAP[tokens[i]]
                if value == 1000:
                    current = max(current, 1)
                    total += current * 1000
                    current = 0
                else:
                    current += value
                i += 1
            total += current
            result.append(str(total))
        return " ".join(result)

    @staticmethod
    def _normalize_currency(text: str) -> str:
        text = re.sub(r"\bруб(?:ля|лей)?\b", "рублей", text)
        text = re.sub(r"\bр\b", "рублей", text)
        text = text.replace("₽", " рублей")
        return text

    @staticmethod
    def _cleanup_spacing(text: str) -> str:
        text = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\.\s*\.", ".", text)
        return text.strip(" .")
