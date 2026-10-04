"""sql_agent node: generate SQL, pass it through the guard, execute read-only.

On rejection (or execution error) the error text is fed back to the provider for up
to two self-correction retries (three attempts total). If the model never produces a
working query — or produces a valid query that returns 0 rows for an otherwise
complete request — we fall back to a trusted parameterized query (D15). The trace
records which path produced the rows: `llm_sql`, `fallback_sql`, or `none`.
"""

from __future__ import annotations

from app.db import readonly_connection
from app.guardrails.sql_guard import validate_sql
from app.llm.base import LLMProvider
from app.retrieval import build_candidate_query, run_candidates
from app.state import DispatchState

MAX_ATTEMPTS = 3  # 1 initial + 2 self-corrections


def _is_complete(request: dict) -> bool:
    return bool(
        request.get("origin")
        and request.get("destination")
        and request.get("body_type")
        and request.get("weight_t") is not None
    )


def sql_agent_node(state: DispatchState, provider: LLMProvider) -> dict:
    request = state.get("request") or {}
    attempts: list[dict] = []
    error: str | None = None
    llm_sql: str | None = None
    llm_rows: list[dict] = []

    # 1) Try the model (guarded, read-only), self-correcting on rejection.
    for i in range(MAX_ATTEMPTS):
        raw_sql = provider.generate_sql(request, error=error)
        result = validate_sql(raw_sql)
        record = {"attempt": i + 1, "raw": raw_sql, "ok": result.ok,
                  "reason": result.reason, "path": "llm"}

        if not result.ok:
            error = result.reason
            attempts.append(record)
            continue

        try:
            conn = readonly_connection()
            try:
                llm_rows = [dict(r) for r in conn.execute(result.sql).fetchall()]
            finally:
                conn.close()
            llm_sql = result.sql
            attempts.append(record)
            break
        except Exception as e:  # noqa: BLE001 - surface execution error for retry
            record["exec_error"] = str(e)
            error = f"ошибка выполнения: {e}"
            attempts.append(record)

    rows = llm_rows
    sql_text = llm_sql
    sql_path = "llm_sql" if (llm_sql and llm_rows) else "none"

    # 2) Deterministic fallback when the model failed, or returned nothing for a
    #    complete request (e.g. a small model wrote shaky SQL / garbled the cities).
    need_fallback = llm_sql is None or (not llm_rows and _is_complete(request))
    if need_fallback and request.get("origin") and request.get("destination"):
        fb_sql, fb_params = build_candidate_query(request)
        try:
            rows = run_candidates(request)
            attempts.append({
                "attempt": len(attempts) + 1,
                "raw": " ".join(fb_sql.split()),
                "params": fb_params,
                "ok": True,
                "reason": None,
                "path": "fallback",
            })
            sql_text = " ".join(fb_sql.split())
            sql_path = "fallback_sql"
        except Exception as e:  # noqa: BLE001
            attempts.append({"attempt": len(attempts) + 1, "ok": False,
                             "reason": f"fallback error: {e}", "path": "fallback"})
    elif llm_sql:
        sql_path = "llm_sql"

    step = {
        "step": "sql_agent",
        "status": "ok" if rows else ("ok" if sql_text else "failed"),
        "detail": {
            "sql": sql_text,
            "sql_path": sql_path,
            "rows": len(rows),
            "attempts": len(attempts),
            "blocked": sum(1 for a in attempts if not a["ok"]),
        },
    }
    return {
        "sql": sql_text,
        "sql_done": True,
        "sql_path": sql_path,
        "sql_attempts": attempts,
        "rows": rows,
        "trace": [step],
    }
