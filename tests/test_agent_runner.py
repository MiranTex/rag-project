import json

from backend.agent.runner import AgentRunner
from backend.agent.tools import ToolContext, build_registry


class _ScriptedLLM:
    """Devolve as mensagens do assistente por ordem e guarda o que recebeu."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        return self.replies.pop(0)


def _tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def _runner(llm, max_steps=8, tool_names=None):
    registry = build_registry()
    ctx = ToolContext(pipeline=None, vector_store=None, registry=None, export_store=None)
    return AgentRunner(llm=llm, tools=registry.select(tool_names), system_prompt="sys", context=ctx, max_steps=max_steps)


def test_runner_executes_tool_and_returns_answer():
    llm = _ScriptedLLM([
        {"content": "Vou calcular.", "tool_calls": [_tool_call("c1", "percentage_change", {"old_value": 1500, "new_value": 1650})]},
        {"content": "O salário aumentou 10%."},
    ])

    events = list(_runner(llm).run("Quanto aumentou?", history=[{"role": "user", "content": "antes"}, {"role": "assistant", "content": "ok"}]))

    assert [e.type for e in events] == ["thinking", "tool_call", "tool_result", "answer"]
    assert events[2].data["ok"] is True
    assert events[3].data["answer"] == "O salário aumentou 10%."
    second_call = llm.calls[1]["messages"]
    assert [m["role"] for m in second_call] == ["system", "user", "assistant", "user", "assistant", "tool"]
    assert json.loads(second_call[-1]["content"])["percent_change"] == 10.0


def test_runner_returns_tool_errors_to_model():
    llm = _ScriptedLLM([
        {"content": "", "tool_calls": [_tool_call("c1", "calculate", {"expression": "__import__('os')"}), _tool_call("c2", "nao_existe", {})]},
        {"content": "Não consegui."},
    ])

    events = list(_runner(llm).run("x"))

    results = [e for e in events if e.type == "tool_result"]
    assert [r.data["ok"] for r in results] == [False, False]
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert all("error" in json.loads(m["content"]) for m in tool_messages)


def test_runner_forces_final_answer_on_last_step():
    looping = {"content": "", "tool_calls": [_tool_call("c", "calculate", {"expression": "1 + 1"})]}
    llm = _ScriptedLLM([looping, looping, {"content": "Resposta final."}])

    events = list(_runner(llm, max_steps=3).run("x"))

    assert events[-1].type == "answer"
    assert [c["tool_choice"] for c in llm.calls] == [None, None, "none"]


def test_runner_only_exposes_profile_tools():
    llm = _ScriptedLLM([{"content": "ok"}])
    list(_runner(llm, tool_names=["calculate"]).run("x"))
    assert [t["function"]["name"] for t in llm.calls[0]["tools"]] == ["calculate"]
