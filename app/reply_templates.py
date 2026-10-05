"""Deterministic Russian reply templates (grounding, D14).

Used for the no-options case (always) and as the fallback when the output guard
rejects an LLM-composed reply. Every number here comes from priced `options`, so
these templates can never hallucinate a carrier or a price.
"""

from __future__ import annotations

from typing import Any


def _route(request: dict[str, Any]) -> str:
    return f"{request.get('origin') or '?'} — {request.get('destination') or '?'}"


def no_options_reply(request: dict[str, Any]) -> str:
    return (
        f"К сожалению, по маршруту {_route(request)} сейчас нет свободных машин "
        "под ваши параметры. Подскажите, пожалуйста, можно ли сдвинуть дату или "
        "рассмотреть другой тип кузова — тогда поищу ещё раз."
    )


def no_route_reply(request: dict[str, Any]) -> str:
    return (
        f"К сожалению, направление {_route(request)} мы пока не возим — этого "
        "маршрута нет в нашей базе. Уточните, пожалуйста, города отправления и "
        "назначения, и я проверю, чем сможем помочь."
    )


def grounded_reply(request: dict[str, Any], options: list[dict[str, Any]]) -> str:
    if not options:
        return no_options_reply(request)

    lines = [f"Здравствуйте! По маршруту {_route(request)} предлагаю варианты:"]
    for i, opt in enumerate(options[:3], start=1):
        price = opt.get("price") or 0
        currency = opt.get("currency", "RUB")
        eta = opt.get("eta_days")
        price_str = f"{price:,.0f}".replace(",", " ")
        eta_str = f", срок ~{eta} сут" if eta else ""
        lines.append(
            f"{i}) {opt.get('carrier')} — {opt.get('body_type')}, "
            f"{opt.get('capacity_t')} т, из города {opt.get('current_city')}. "
            f"Цена {price_str} {currency}{eta_str}."
        )
    lines.append("Если какой-то вариант подходит — подтвердите, оформим заявку.")
    return "\n".join(lines)
