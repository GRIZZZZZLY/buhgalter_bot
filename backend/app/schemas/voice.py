from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from app.schemas.parser import ParseResult


VoiceAction = Literal["confirm_voice", "voice_fallback", "voice_confirmed", "voice_cancelled", "voice_edit_required", "clarify_category_choice"]


@dataclass(slots=True)
class VoiceTranscriptionResult:
    text: str | None
    confidence: float
    provider: str
    needs_fallback: bool = False
    failure_reason: str | None = None


@dataclass(slots=True)
class VoiceConfirmationResult:
    action: VoiceAction
    message: str
    voice_log_id: UUID | None = None
    transcript: str | None = None
    parsed_items: list[dict[str, str]] = field(default_factory=list)
    raw_category: str | None = None
    suggestions: list[str] = field(default_factory=list)
    parsed_result: ParseResult | None = None
