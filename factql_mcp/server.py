"""FactQL MCP server — a thin wrapper over ``POST /query``.

Configure with environment variables:

    FACTQL_API_KEY       required. A FactQL API key (a query-only key is enough).
    FACTQL_BASE_URL      default https://api.factql.ai
    FACTQL_WORKSPACE_ID  default workspace when the tenant uses workspaces.
    FACTQL_END_USER_ID   who is asking; default "mcp:<os user>". Query-only keys
                         require it on tenant routes.

Every question is a fresh, stateless ``/query`` call: the MCP client carries the
conversation, so a follow-up must restate what it refers to.
"""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import os
from typing import Any, Optional

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context

BASE_URL = os.environ.get("FACTQL_BASE_URL", "https://api.factql.ai").rstrip("/")
ROW_CAP = 50
PROGRESS_EVERY = 5.0  # seconds between "still working" notes on a slow answer
DECLINED_NOTE = (
    "FactQL could not verify an answer, so it gave none rather than guess. "
    "This is deliberate, not a tool failure: tell the user the reason and do "
    "not supply a figure yourself."
)
_PASS_THROUGH = (
    "type",
    "result",
    "explanation",
    "answer",
    "sql",
    "total_rows",
    "clarification_request",
    "suggestions",
    "sources",
    "chart",
    "chart_spec",
    "locale",
    "budget_alerts",
    "error",
    "detail",
)

server = MCPServer(
    "factql",
    instructions=(
        "Ask plain-English questions about the connected business data. Call "
        "`whoami` first when the tenant may use workspaces, then pass the "
        "workspace_id to `ask`. Each `ask` is stateless: restate the subject in "
        "follow-up questions."
    ),
)


def _headers() -> dict[str, str]:
    key = os.environ.get("FACTQL_API_KEY")
    if not key:
        raise RuntimeError("FACTQL_API_KEY is not set")
    return {
        "X-API-Key": key,
        "X-End-User-Id": os.environ.get("FACTQL_END_USER_ID")
        or f"mcp:{getpass.getuser()}",
    }


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, headers=_headers(), timeout=120.0)


async def _with_progress(ctx: Context, coro):
    """Await ``coro``, sending a progress note every PROGRESS_EVERY seconds.

    The SDK only sends a note when the client asked for progress, so this is
    silent otherwise. A failed note never fails the question."""
    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(coro)
    start = loop.time()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=PROGRESS_EVERY)
            if done:
                return task.result()
            secs = int(loop.time() - start)
            with contextlib.suppress(Exception):
                await ctx.report_progress(
                    secs, message=f"FactQL is still working on the answer ({secs}s)…"
                )
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def _post_query(body: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        base_url=BASE_URL, headers=_headers(), timeout=120.0
    ) as c:
        return await c.post("/query", json=body)


def _error(res: httpx.Response) -> dict[str, Any]:
    try:
        detail = res.json()
    except ValueError:
        detail = res.text
    return {"error": f"HTTP {res.status_code}", "detail": detail}


def shape_answer(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep what a model needs from an /ask-shaped payload; cap the rows."""
    if payload.get("result") == "error":
        # The API call succeeded; FactQL chose not to give a figure it couldn't
        # verify. Say so, so the client doesn't read it as a broken tool.
        return {
            "result": "declined",
            "reason": payload.get("error") or payload.get("explanation"),
            "note": DECLINED_NOTE,
        }
    out = {k: payload[k] for k in _PASS_THROUGH if payload.get(k) is not None}
    data = payload.get("data") or {}
    rows = data.get("rows") or []
    if rows or data.get("columns"):
        out["columns"] = data.get("columns") or []
        out["rows"] = rows[:ROW_CAP]
        out["row_count"] = payload.get("total_rows") or len(rows)
        if len(rows) > ROW_CAP:
            out["note"] = f"Showing the first {ROW_CAP} of {len(rows)} returned rows."
    return out


@server.tool()
def whoami() -> dict[str, Any]:
    """What this API key can see: tenant, plan, and the workspaces it may query.

    Use it to find a `workspace_id` before calling `ask` on a tenant that
    uses workspaces."""
    with _client() as c:
        res = c.get("/whoami")
    return res.json() if res.is_success else _error(res)


@server.tool()
async def ask(
    question: str,
    ctx: Context,
    workspace_id: Optional[str] = None,
    locale: Optional[str] = None,
) -> dict[str, Any]:
    """Ask a plain-English question about the connected data.

    Returns the answer, the SQL that was run (when any), and up to 50 rows.
    `workspace_id` scopes the question when the tenant uses workspaces
    (see `whoami`); `locale` is "en-GB" or "en-US" for the answer's wording.
    A `needs_clarification` result means the question was too vague: ask the
    user, then call again with the detail. A `declined` result means FactQL
    could not verify an answer and chose not to guess: pass the `reason` on
    and don't invent a figure."""
    body: dict[str, Any] = {"q": question}
    ws = workspace_id or os.environ.get("FACTQL_WORKSPACE_ID")
    if ws:
        body["workspace_id"] = ws
    if locale:
        body["locale"] = locale
    res = await _with_progress(ctx, _post_query(body))
    if not res.is_success:
        return _error(res)
    payload = res.json()
    return shape_answer(payload) if isinstance(payload, dict) else {"answer": payload}


def main() -> None:
    _headers()  # fail at startup, not on the first question
    server.run("stdio")


if __name__ == "__main__":
    main()
