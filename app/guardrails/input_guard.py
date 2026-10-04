"""Rule-based input screening for prompt injection, data-tampering and off-topic.

This is the fast, deterministic first layer. The `input_guard` graph node combines
this with an optional LLM classifier (see app/nodes/input_guard.py). Rules alone
must already catch the common attack phrasings in both Russian and English.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# category -> list of regex patterns (compiled case-insensitively below)
_RULES: dict[str, list[str]] = {
    "prompt_injection": [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"disregard\s+(the\s+)?(previous|above|system)",
        r"forget\s+(everything|all|previous|your\s+instructions)",
        r"ты\s+теперь\b",
        r"забудь\s+(все|всё|предыдущие|свои\s+инструкции)",
        r"игнорир\w*\s+(все\s+)?(предыдущие|прошлые|выше|инструкции)",
        r"new\s+instructions?\s*:",
        r"act\s+as\s+(if|a|an)\b",
        r"притвор\w+\s+(что|будто)",
        r"\bjailbreak\b",
        r"developer\s+mode",
        r"режим\s+разработчика",
    ],
    "system_leak": [
        r"system\s+prompt",
        r"систем\w*\s+промпт",
        r"(покажи|выведи|повтори|распечатай|дай)\s+(мне\s+)?(свой\s+|твой\s+)?(систем\w*\s+)?(промпт|инструкци)",
        r"(reveal|show|print|repeat|leak)\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions)",
        r"what\s+(is|are)\s+your\s+(system\s+)?(prompt|instructions)",
        r"твои\s+(систем\w*\s+)?инструкци",
    ],
    "sql_tamper": [
        r"\bdrop\s+table\b",
        r"\bdelete\s+from\b",
        r"\bupdate\s+\w+\s+set\b",
        r"\binsert\s+into\b",
        r"\btruncate\b",
        r"\balter\s+table\b",
        r"удали\w*\s+(все\s+|всю\s+)?(таблиц|записи|данные|строки|базу)",
        r"очисти\w*\s+(таблиц|базу|данные)",
        r"измени\w*\s+(данные|записи|таблиц)",
        r"\b;\s*drop\b",
    ],
}

_COMPILED: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in _RULES.items()
}

# Light off-topic signal: clearly-not-freight asks. Kept conservative so normal
# dispatch requests (which rarely use these verbs) are not misclassified.
_OFFTOPIC = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"напиши\s+(стих|поэму|песн|рассказ|сочинение|код|программу)",
        r"(реши|посчитай)\s+(уравнение|пример|задачу\s+по)",
        r"(курс|прогноз)\s+(доллар|валют|биткоин|погод)",
        r"(расскажи|что\s+ты\s+знаешь)\s+о\s+(политик|истори|религ)",
        r"write\s+(me\s+)?(a\s+)?(poem|story|essay|code|script)",
        r"recipe\s+for\b",
    ]
]


@dataclass
class InputScreen:
    blocked: bool
    category: str | None = None
    reason: str | None = None

    @property
    def is_attack(self) -> bool:
        return self.blocked and self.category in (
            "prompt_injection",
            "system_leak",
            "sql_tamper",
        )


def screen_input(text: str) -> InputScreen:
    """Return a screening verdict for a raw user message."""
    if not text or not text.strip():
        return InputScreen(blocked=False)

    for category, patterns in _COMPILED.items():
        for pat in patterns:
            if pat.search(text):
                return InputScreen(
                    blocked=True,
                    category=category,
                    reason=f"rule match: {category} (/{pat.pattern[:48]}/)",
                )

    for pat in _OFFTOPIC:
        if pat.search(text):
            return InputScreen(
                blocked=True,
                category="offtopic",
                reason=f"rule match: offtopic (/{pat.pattern[:48]}/)",
            )

    return InputScreen(blocked=False)
