from app.services.advisor_intent_router import AdvisorIntent, AdvisorIntentRouter


router = AdvisorIntentRouter()


def test_router_detects_budget_question() -> None:
    route = router.route("Где я вылезаю из бюджета в этом месяце?")
    assert route.intent == AdvisorIntent.BUDGET_CHECK


def test_router_detects_upcoming_question() -> None:
    route = router.route("Какие платежи у меня скоро?")
    assert route.intent == AdvisorIntent.UPCOMING


def test_router_detects_trend_question() -> None:
    route = router.route("Сравни расходы за 3 месяца")
    assert route.intent == AdvisorIntent.TREND_ANALYSIS


def test_router_question_shortcut_detects_question_prefix() -> None:
    assert router.looks_like_advisor_question("Сколько я трачу на еду") is True
    assert router.looks_like_advisor_question("такси 300") is False
