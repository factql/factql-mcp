"""The shape a model sees. Run: uv run --with pytest pytest -q"""

import asyncio
import json

import httpx
import pytest

from factql_mcp import server as srv
from factql_mcp.server import ROW_CAP, shape_answer


def test_shape_answer_caps_rows_and_keeps_the_answer():
    payload = {
        "type": "text2sql",
        "result": "success",
        "sql": "SELECT 1",
        "explanation": "Found 60 records.",
        "thinking": "internal",  # dropped
        "data": {"columns": ["n"], "rows": [[i] for i in range(60)]},
    }
    out = shape_answer(payload)
    assert out["sql"] == "SELECT 1" and out["explanation"] == "Found 60 records."
    assert "thinking" not in out
    assert len(out["rows"]) == ROW_CAP and out["row_count"] == 60
    assert out["note"].startswith("Showing the first 50")


def test_shape_answer_passes_clarification_through():
    out = shape_answer(
        {"result": "needs_clarification", "clarification_request": "Which year?"}
    )
    assert out == {
        "result": "needs_clarification",
        "clarification_request": "Which year?",
    }


def test_shape_answer_marks_a_decline_as_deliberate():
    msg = "I couldn't find a reliable way to answer this from your data."
    out = shape_answer(
        {"result": "error", "kind": "decline", "error": msg, "explanation": msg}
    )
    assert out["result"] == "declined" and out["reason"] == msg
    assert "error" not in out and "not a tool failure" in out["note"]


def test_shape_answer_keeps_a_real_failure_apart_from_a_decline():
    out = shape_answer(
        {"result": "error", "error": "Error in text2sql agent. Trace: abc"}
    )
    assert out["result"] == "error" and out["reason"].startswith("Error in")
    assert "do not supply a figure" in out["note"]


def test_slow_ask_sends_progress_then_the_answer(monkeypatch):
    import asyncio

    import httpx
    from mcp import Client

    from factql_mcp import server as srv

    async def slow_query(body):
        await asyncio.sleep(0.3)
        return httpx.Response(200, json={"result": "success", "answer": "42"})

    monkeypatch.setenv("FACTQL_API_KEY", "test")
    monkeypatch.setattr(srv, "PROGRESS_EVERY", 0.05)
    monkeypatch.setattr(srv, "_post_query", slow_query)
    notes = []

    async def on_progress(progress, total, message):
        notes.append(message)

    async def run():
        async with Client(srv.server) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert "ctx" not in tools["ask"].input_schema["properties"]
            return await c.call_tool(
                "ask", {"question": "how many?"}, progress_callback=on_progress
            )

    res = asyncio.run(run())
    assert not res.is_error and '"42"' in res.content[0].text
    assert notes and "still working" in notes[0]


# --- setup states: no data, not ready, unverified email, plan limit ---------


BUDGET_MSG = (
    "You've used the free plan's usage. Choose a plan in Plan & billing to keep asking."
)
STATES = {
    "no_data": httpx.Response(
        422,
        json={
            "detail": "This workspace has no data yet. Upload a file or connect a database to it first."
        },
        headers={"X-FactQL-Reason": "no_data"},
    ),
    "schema_not_ready": httpx.Response(
        200,
        json={
            "result": "preparing",
            "kind": "workspace_preparing",
            "error": "Your data is still being read.",
        },
    ),
    "email_unverified": httpx.Response(
        403,
        json={
            "detail": {
                "error": "email_unverified",
                "message": "Verify your email to use this key.",
            }
        },
    ),
    "limit_reached": httpx.Response(
        402,
        json={
            "detail": {
                "error": "budget_exceeded",
                "message": BUDGET_MSG,
                "blocking_scope": {},
            }
        },
    ),
}
MESSAGES = {
    "no_data": (
        "No data is connected to this FactQL workspace yet. Add a database or "
        "upload a CSV or Excel file at https://factql.ai, then ask again."
    ),
    "schema_not_ready": "Your data is still being prepared. Try again in a minute or two.",
    "email_unverified": "Verify your email to start asking. Check your inbox for the link from FactQL.",
    "limit_reached": BUDGET_MSG,  # passed through unchanged
}


def _call(name, args, monkeypatch, query=None, whoami=None):
    """Call a tool through a real MCP client against a fake FactQL."""
    from mcp import Client

    monkeypatch.setenv("FACTQL_API_KEY", "test")

    async def fake_query(body):
        return query

    monkeypatch.setattr(srv, "_post_query", fake_query)
    if whoami is not None:
        transport = httpx.MockTransport(lambda req: whoami)
        monkeypatch.setattr(
            srv,
            "_client",
            lambda: httpx.Client(base_url=srv.BASE_URL, transport=transport),
        )

    async def run():
        async with Client(srv.server) as c:
            return await c.call_tool(name, args)

    res = asyncio.run(run())
    assert not res.is_error  # a normal result the model relays, never a protocol error
    return json.loads(res.content[0].text)


@pytest.mark.parametrize("code", list(STATES))
def test_ask_explains_each_setup_state(monkeypatch, code):
    out = _call("ask", {"question": "revenue?"}, monkeypatch, query=STATES[code])
    assert out == {"result": code, "message": MESSAGES[code]}


def test_a_plain_422_or_500_is_still_an_error(monkeypatch):
    plain = httpx.Response(422, json={"detail": "workspace_id is required"})
    out = _call("ask", {"question": "q"}, monkeypatch, query=plain)
    assert out == {
        "error": "HTTP 422",
        "detail": {"detail": "workspace_id is required"},
    }
    out = _call(
        "ask", {"question": "q"}, monkeypatch, query=httpx.Response(500, text="boom")
    )
    assert out == {"error": "HTTP 500", "detail": "boom"}


def test_a_success_and_a_decline_are_unchanged(monkeypatch):
    ok = httpx.Response(200, json={"result": "success", "answer": "42"})
    assert _call("ask", {"question": "q"}, monkeypatch, query=ok) == {
        "result": "success",
        "answer": "42",
    }
    no = httpx.Response(
        200, json={"result": "error", "kind": "decline", "error": "No churn data."}
    )
    out = _call("ask", {"question": "q"}, monkeypatch, query=no)
    assert out["result"] == "declined" and out["reason"] == "No churn data."


def test_whoami_says_whether_there_is_data(monkeypatch):
    full = httpx.Response(200, json={"client_id": "t1", "has_data": True})
    assert _call("whoami", {}, monkeypatch, whoami=full) == {
        "client_id": "t1",
        "has_data": True,
    }
    empty = httpx.Response(200, json={"client_id": "t1", "has_data": False})
    out = _call("whoami", {}, monkeypatch, whoami=empty)
    assert out["has_data"] is False and out["note"] == MESSAGES["no_data"]
    out = _call("whoami", {}, monkeypatch, whoami=STATES["email_unverified"])
    assert out == {
        "result": "email_unverified",
        "message": MESSAGES["email_unverified"],
    }
