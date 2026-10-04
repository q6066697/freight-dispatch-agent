"""Output guard tests — including the exact real hallucination case."""

from app.guardrails.output_guard import check_reply

OPTIONS = [
    {"carrier": "ООО «БелТрансЛогистик»", "price": 37800.0, "body_type": "тент",
     "capacity_t": 20.0, "current_city": "Гданьск", "eta_days": 2, "currency": "RUB"},
    {"carrier": "ИП Мороз Д.И.", "price": 42300.0, "body_type": "тент",
     "capacity_t": 20.0, "current_city": "Гродно", "eta_days": 2, "currency": "RUB"},
]


def test_grounded_reply_passes():
    reply = (
        "Здравствуйте! По маршруту Минск — Москва предлагаю варианты:\n"
        "1) ООО «БелТрансЛогистик» — тент, 20.0 т, из города Гданьск. "
        "Цена 37 800 RUB, срок ~2 сут.\n"
        "2) ИП Мороз Д.И. — тент, 20.0 т, из города Гродно. Цена 42 300 RUB, срок ~2 сут."
    )
    assert check_reply(reply, OPTIONS).ok


def test_real_hallucination_case_blocked():
    # Exactly what ollama/qwen2.5 produced on a no-options request.
    reply = (
        "Здравствуйте! Предлагаю варианты:\n"
        '1) ООО "Автотрейдинг" — тент. Цена 50 000 руб, срок 3 дня.\n'
        '2) ФКУ "Транспорт" — тент. Цена 48 000 руб, срок 3 дня.'
    )
    screen = check_reply(reply, [])  # no options at all
    assert not screen.ok
    assert any("Автотрейдинг" in v for v in screen.violations)
    assert any("50000" in v or "48000" in v for v in screen.violations)


def test_invented_carrier_among_real_ones_blocked():
    reply = (
        "1) ООО «БелТрансЛогистик» — тент. Цена 37 800 RUB.\n"
        '2) ООО "Небылица" — тент. Цена 37 800 RUB.'
    )
    screen = check_reply(reply, OPTIONS)
    assert not screen.ok
    assert any("Небылица" in v for v in screen.violations)


def test_wrong_price_blocked():
    reply = "ООО «БелТрансЛогистик» — тент. Цена 99 999 RUB."
    screen = check_reply(reply, OPTIONS)
    assert not screen.ok
    assert any("99999" in v for v in screen.violations)


def test_no_options_template_has_no_mentions():
    reply = (
        "К сожалению, по маршруту Минск — Москва сейчас нет свободных машин под "
        "ваши параметры. Подскажите, можно ли сдвинуть дату или сменить кузов."
    )
    assert check_reply(reply, []).ok


def test_empty_reply_ok():
    assert check_reply("", OPTIONS).ok
