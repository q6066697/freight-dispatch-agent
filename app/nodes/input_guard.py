"""input_guard node: block prompt-injection / tamper / off-topic before extraction.

Combines the deterministic rule layer (`screen_input`) with the provider's attack
classifier (a second opinion). If either flags the message, the graph refuses.
"""

from __future__ import annotations

from app.guardrails.input_guard import screen_input
from app.llm.base import LLMProvider
from app.state import DispatchState

_REFUSALS = {
    "prompt_injection": (
        "Извините, но я не могу выполнить эту просьбу. Я — диспетчер по подбору "
        "грузоперевозок. Опишите, пожалуйста, ваш груз и маршрут."
    ),
    "sql_tamper": (
        "Извините, изменять или удалять данные я не могу — только подбирать машины "
        "под перевозку. Напишите, что и куда нужно отвезти."
    ),
    "system_leak": (
        "Извините, служебную информацию я не раскрываю. Могу помочь с подбором "
        "транспорта: укажите груз, вес и маршрут."
    ),
    "offtopic": (
        "Я помогаю только с грузоперевозками. Опишите груз, вес и города "
        "отправления/назначения — подберу машину и цену."
    ),
}


def refusal_text(category: str | None) -> str:
    return _REFUSALS.get(category or "offtopic", _REFUSALS["offtopic"])


def input_guard_node(state: DispatchState, provider: LLMProvider) -> dict:
    text = state["text"]
    rule = screen_input(text)
    llm = provider.classify_attack(text)

    blocked = rule.blocked or bool(llm.get("is_attack"))
    category = rule.category or (llm.get("category") if llm.get("is_attack") else None)

    step = {
        "step": "input_guard",
        "status": "blocked" if blocked else "ok",
        "detail": {"rule": rule.reason, "llm": llm},
    }
    out: dict = {
        "screen": {"blocked": blocked, "category": category},
        "blocked": blocked,
        "block_category": category,
        "trace": [step],
    }
    if blocked:
        out["reply"] = refusal_text(category)
        out["status"] = "refused"
    return out
