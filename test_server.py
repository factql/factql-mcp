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
