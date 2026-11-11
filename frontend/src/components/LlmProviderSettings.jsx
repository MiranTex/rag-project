import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, PlugZap, Save } from "lucide-react";
import { getLlmSettings, saveLlmProvider, testLlmProvider } from "../api";
import { Button, ErrorText, inputClass, Spinner } from "./ui";

function draftFrom(provider) {
  return {
    api_key: "",
    base_url: provider.base_url,
    chat_model: provider.chat_model,
    utility_model: provider.utility_model,
  };
}

function Field({ id, label, help, children }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium text-stone-800 dark:text-stone-200">
        {label}
      </label>
      {children}
      {help && <p className="text-xs text-stone-500 dark:text-stone-400">{help}</p>}
    </div>
  );
}

// Configurações → Modelo de linguagem: fornecedor de LLM, chave de API e modelos usados em toda a aplicação.
export default function LlmProviderSettings({ onSaved }) {
  const [state, setState] = useState(null);
  const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState(null);
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState(null);

  function select(data, id) {
    setSelected(id);
    setDraft(draftFrom(data.providers.find((p) => p.id === id)));
    setTestResult(null);
    setError("");
  }

  useEffect(() => {
    getLlmSettings()
      .then((data) => {
        setState(data);
        select(data, data.active);
      })
      .catch((err) => setError(err.message));
  }, []);

  const provider = state?.providers.find((p) => p.id === selected);
  const update = (field) => (e) => setDraft({ ...draft, [field]: e.target.value });

  function payload() {
    return {
      // Campo vazio: mantém a chave já guardada.
      api_key: draft.api_key.trim() || null,
      base_url: draft.base_url,
      chat_model: draft.chat_model,
      utility_model: draft.utility_model,
      activate: true,
    };
  }

  async function run(kind, action) {
    setWorking(kind);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setWorking("");
    }
  }

  const handleTest = () =>
    run("test", async () => {
      setTestResult(null);
      setTestResult(await testLlmProvider(selected, payload()));
    });

  const handleSave = () =>
    run("save", async () => {
      const data = await saveLlmProvider(selected, payload());
      setState(data);
      setDraft(draftFrom(data.providers.find((p) => p.id === selected)));
      onSaved?.(`Modelo de linguagem: a usar ${provider.label}.`);
    });

  const busy = !!working;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">Modelo de linguagem</h2>
      <div className="space-y-4 rounded-xl border border-stone-200 p-4 dark:border-stone-800">
        {!state && !error && <Spinner label="A carregar…" />}

        {state && provider && draft && (
          <>
            <p className="text-sm text-stone-500 dark:text-stone-400">
              Fornecedor e chave usados no chat, no agente, na ficha dos documentos e na área de pesquisa.
              {state.source === "env" && " Por agora vale a configuração do ficheiro .env; ao guardar aqui, passa a valer esta."}
            </p>

            <Field id="llm-provider" label="Fornecedor" help={provider.hint}>
              <select id="llm-provider" value={selected} disabled={busy} onChange={(e) => select(state, e.target.value)} className={inputClass}>
                {state.providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                    {p.id === state.active ? " (em uso)" : ""}
                  </option>
                ))}
              </select>
            </Field>

            <Field id="llm-key" label={provider.needs_key ? "Chave de API" : "Chave de API (opcional)"}>
              <input
                id="llm-key"
                type="password"
                autoComplete="off"
                value={draft.api_key}
                onChange={update("api_key")}
                placeholder={provider.has_key ? `Guardada (${provider.key_hint}). Deixa vazio para manter.` : "Cola aqui a chave"}
                disabled={busy}
                className={inputClass}
              />
            </Field>

            <Field id="llm-url" label="URL da API" help={provider.default_base_url && `Vazio usa ${provider.default_base_url}`}>
              <input
                id="llm-url"
                value={draft.base_url}
                onChange={update("base_url")}
                placeholder={provider.default_base_url || "https://…/v1"}
                disabled={busy}
                className={inputClass}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="llm-chat" label="Modelo de chat" help="Responde às perguntas e conduz o agente.">
                <input
                  id="llm-chat"
                  value={draft.chat_model}
                  onChange={update("chat_model")}
                  placeholder={provider.default_chat_model || "nome do modelo"}
                  disabled={busy}
                  className={inputClass}
                />
              </Field>
              <Field
                id="llm-utility"
                label="Modelo utilitário"
                help="Mais pequeno e barato: filtro de âmbito, ficha e pesquisa. Vazio usa o de chat."
              >
                <input
                  id="llm-utility"
                  value={draft.utility_model}
                  onChange={update("utility_model")}
                  placeholder={provider.default_utility_model || "igual ao de chat"}
                  disabled={busy}
                  className={inputClass}
                />
              </Field>
            </div>

            {testResult && (
              <ul className="space-y-1 text-sm">
                {Object.entries(testResult.results).map(([role, r]) => (
                  <li
                    key={role}
                    className={`flex items-start gap-2 ${r.ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}
                  >
                    {r.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <AlertCircle className="mt-0.5 size-4 shrink-0" />}
                    <span className="min-w-0 break-words">
                      {r.model}: {r.ok ? "responde" : r.error}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex flex-wrap justify-end gap-2">
              <Button icon={PlugZap} busy={working === "test"} disabled={busy} onClick={handleTest}>
                Testar
              </Button>
              <Button variant="primary" icon={Save} busy={working === "save"} disabled={busy} onClick={handleSave}>
                Guardar e usar
              </Button>
            </div>
          </>
        )}

        <ErrorText>{error}</ErrorText>
      </div>
    </section>
  );
}
