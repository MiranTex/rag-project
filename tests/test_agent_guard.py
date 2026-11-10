import json

from backend.agent.guard import ScopeGuard
from backend.agent.profiles import PROFILES

BLOCKED = PROFILES["assistente"].blocked_categories


class _ClassifierLLM:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        if self.error:
            raise self.error
        return self.reply


def _classified(category, reason="motivo"):
    arguments = json.dumps({"category": category, "reason": reason})
    return {"content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "classify", "arguments": arguments}}]}


def test_blocks_out_of_scope():
    guard = ScopeGuard(_ClassifierLLM(_classified("fora_do_ambito", "jogo")))
    decision = guard.check("vamos jogar um jogo", [], ["contrato.pdf"], BLOCKED)
    assert (decision.allowed, decision.category, decision.reason) == (False, "fora_do_ambito", "jogo")


def test_allows_in_scope_categories():
    for category in ["documentos", "seguimento", "assistente", "conversa", "conhecimento_geral", "calculo"]:
        guard = ScopeGuard(_ClassifierLLM(_classified(category)))
        assert guard.check("x", [], [], BLOCKED).allowed, category


def test_policy_comes_from_profile_not_model():
    guard = ScopeGuard(_ClassifierLLM(_classified("calculo")))
    assert guard.check("quanto é 2+2", [], [], frozenset({"fora_do_ambito", "calculo"})).allowed is False


def test_forces_classify_tool_and_sends_context():
    llm = _ClassifierLLM(_classified("seguimento"))
    history = [
        {"role": "user", "content": "Qual o salário?"},
        {"role": "assistant", "content": "x" * 1000},
    ]
    ScopeGuard(llm).check("e em percentagem?", history, ["contrato.pdf"], BLOCKED)

    call = llm.calls[0]
    assert call["tool_choice"] == {"type": "function", "function": {"name": "classify"}}
    assert "contrato.pdf" in call["messages"][0]["content"]
    transcript = call["messages"][1]["content"]
    assert "Utilizador: Qual o salário?" in transcript
    assert "e em percentagem?" in transcript
    assert "x" * 301 not in transcript  # respostas longas cortadas


def test_fails_open_on_errors():
    for llm in [
        _ClassifierLLM(error=TimeoutError("timeout")),
        _ClassifierLLM({"content": "não sei"}),
        _ClassifierLLM(_classified("categoria_inventada")),
    ]:
        decision = ScopeGuard(llm).check("x", [], [], BLOCKED)
        assert decision.allowed and decision.category == "erro_guarda"
