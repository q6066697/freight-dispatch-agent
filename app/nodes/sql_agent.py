"""sql_agent node: generate SQL, guard it, execute read-only, then *verify* it.

Passing the SQL guard only proves a query is safe, not correct. So rows from the
model are accepted only if they satisfy the column/type contract AND the semantic
filter (app/sql_contract.py). Otherwise — or if the model never produced a working
query, or it returned no rows — we use the trusted parameterized fallback and record
why (`fallback_reason`). The trace records which path produced the rows (`sql_path`).
"""

from __future__ import annotations

from app.db import readonly_connection
from app.guardrails.sql_guard import validate_sql
from app.llm.base import LLMProvider
from app.retrieval import build_candidate_query, run_candidates
from app.sql_contract import semantic_filter, validate_rows
from app.state import DispatchState

MAX_ATTEMPTS = 3  # 1 initial + 2 self-corrections


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

    # 2) Decide whether the model's rows are usable.
    rows: list[dict] = []
    sql_text: str | None = None
    sql_path = "none"
    fallback_reason: str | None = None

    if llm_sql is None:
        fallback_reason = "guard_rejected"
    elif not llm_rows:
        fallback_reason = "zero_rows"
    else:
        reason = validate_rows(llm_rows)
        if reason:
            fallback_reason = reason  # missing_columns | invalid_values
        else:
            filtered = semantic_filter(llm_rows, request)
            if not filtered:
                fallback_reason = "semantic_mismatch"
            else:
                rows, sql_text, sql_path = filtered, llm_sql, "llm_sql"

    # 3) Deterministic fallback when the model's rows were not usable.
    if sql_path != "llm_sql":
        fb_sql, fb_params = build_candidate_query(request)
        try:
            rows = semantic_filter(run_candidates(request), request)
            sql_text = " ".join(fb_sql.split())
            sql_path = "fallback_sql"
            attempts.append({"attempt": len(attempts) + 1, "raw": sql_text,
                             "params": fb_params, "ok": True, "reason": None,
                             "path": "fallback"})
        except Exception as e:  # noqa: BLE001
            attempts.append({"attempt": len(attempts) + 1, "ok": False,
                             "reason": f"fallback error: {e}", "path": "fallback"})

    step = {
        "step": "sql_agent",
        "status": "ok" if sql_text else "failed",
        "detail": {
            "sql": sql_text,
            "sql_path": sql_path,
            "fallback_reason": fallback_reason,
            "rows": len(rows),
            "attempts": len(attempts),
            "blocked": sum(1 for a in attempts if not a["ok"]),
        },
    }
    return {
        "sql": sql_text,
        "sql_done": True,
        "sql_path": sql_path,
        "fallback_reason": fallback_reason,
        "sql_attempts": attempts,
        "rows": rows,
        "trace": [step],
    }
