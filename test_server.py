"""One check: the shape a model sees. Run: uv run --with pytest pytest -q"""

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
    out = shape_answer({"result": "error", "error": msg, "explanation": msg})
    assert out["result"] == "declined" and out["reason"] == msg
    assert "error" not in out and "not a tool failure" in out["note"]


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
