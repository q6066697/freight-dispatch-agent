"""sql_agent node: generate SQL, pass it through the guard, execute read-only.

On rejection (or execution error) the error text is fed back to the provider for up
to two self-correction retries (three attempts total).
"""

from __future__ import annotations

from app.db import readonly_connection
from app.guardrails.sql_guard import validate_sql
from app.llm.base import LLMProvider
from app.state import DispatchState

MAX_ATTEMPTS = 3  # 1 initial + 2 self-corrections


def sql_agent_node(state: DispatchState, provider: LLMProvider) -> dict:
    request = state.get("request") or {}
    attempts: list[dict] = []
    error: str | None = None
    sanitized: str | None = None
    rows: list[dict] = []

    for i in range(MAX_ATTEMPTS):
        raw_sql = provider.generate_sql(request, error=error)
        result = validate_sql(raw_sql)
        record = {
            "attempt": i + 1,
            "raw": raw_sql,
            "ok": result.ok,
            "reason": result.reason,
        }

        if not result.ok:
            error = result.reason
            attempts.append(record)
            continue

        try:
            conn = readonly_connection()
            try:
                rows = [dict(r) for r in conn.execute(result.sql).fetchall()]
            finally:
                conn.close()
            sanitized = result.sql
            attempts.append(record)
            break
        except Exception as e:  # noqa: BLE001 - surface any execution error for retry
            record["exec_error"] = str(e)
            error = f"ошибка выполнения: {e}"
            attempts.append(record)

    step = {
        "step": "sql_agent",
        "status": "ok" if sanitized else "failed",
        "detail": {
            "sql": sanitized,
            "rows": len(rows),
            "attempts": len(attempts),
            "blocked": sum(1 for a in attempts if not a["ok"]),
        },
    }
    return {
        "sql": sanitized,
        "sql_done": True,
        "sql_attempts": attempts,
        "rows": rows,
        "trace": [step],
    }
