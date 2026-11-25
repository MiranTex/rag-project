import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, PlugZap, Save, Trash2 } from "lucide-react";
import { Badge, Button, ErrorText, Field, inputClass, Spinner, useConfirm } from "./ui";

// Quem paga as perguntas: a chave do projeto, senão a da pessoa, senão a da plataforma.
const PAYER = {
  project: "a chave deste projeto",
  user: "a tua chave",
  platform: "a chave da plataforma",
};

function draftFrom(state) {
  const key = state.key;
  return {
    provider: key?.provider || state.providers[0]?.id || "",
    api_key: "",
    chat_model: key?.chat_model || "",
    utility_model: key?.utility_model || "",
  };
}

// Chave de API própria, da pessoa (scope="user") ou de um projeto (scope="project"). `api` vem de
// myLlmKey / projectLlmKey(id) em api.js. Num projeto, só o dono edita; os outros membros veem quem paga.
export default function OwnLlmKey({ api, scope, onSaved }) {
  const confirm = useConfirm();
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(null);
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState(null);

  function load(data) {
    setState(data);
    setDraft(draftFrom(data));
    setTestResult(null);
  }

  useEffect(() => {
    api.get().then(load, (err) => setError(err.message));
  }, []);

  if (!state) return error ? <ErrorText>{error}</ErrorText> : <Spinner label="A carregar…" />;

  const editable = scope === "user" || state.can_edit;
  const provider = state.providers.find((p) => p.id === draft.provider);
  const key = state.key;
  const sameProvider = key && key.provider === draft.provider;
  const update = (field) => (e) => setDraft({ ...draft, [field]: e.target.value });

  const payload = () => ({
    provider: draft.provider,
    // Campo vazio mantém a chave guardada (só para o mesmo fornecedor).
    api_key: draft.api_key.trim() || null,
    chat_model: draft.chat_model,
    utility_model: draft.utility_model,
  });

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
      setTestResult(await api.test(payload()));
    });

  const handleSave = () =>
    run("save", async () => {
      load(await api.save(payload()));
      onSaved?.(scope === "project" ? "Chave do projeto guardada." : "A tua chave de API foi guardada.");
    });

  async function handleRemove() {
    const ok = await confirm({
      title: "Remover a chave?",
      message:
        scope === "project"
          ? "As conversas do projeto passam a usar a chave de cada membro ou, sem ela, a da plataforma."
          : "As tuas perguntas passam a usar a chave da plataforma (ou a do projeto, onde houver).",
      confirmLabel: "Remover chave",
    });
    if (!ok) return;
    run("remove", async () => {
      load(await api.remove());
      onSaved?.("Chave removida.");
    });
  }

  const busy = !!working;
  const intro =
    scope === "project"
      ? "Com uma chave própria, o assistente, a matriz e o estado da arte deste projeto são pagos por esta conta, para todos os membros."
      : "Com a tua chave, as tuas perguntas deixam de gastar a da plataforma. Num projeto com chave própria, vale a do projeto.";

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-500 dark:text-stone-400">{intro}</p>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-stone-600 dark:text-stone-300">{scope === "project" ? "Aqui, as tuas perguntas usam" : "Agora usas"}</span>
        <Badge tone={state.effective === "platform" ? "neutral" : "success"}>{PAYER[state.effective]}</Badge>
      </p>

      {!state.enabled && (
        <p className="text-sm text-amber-700 dark:text-amber-400">
          As chaves próprias estão desligadas neste servidor (falta CREDENTIALS_SECRET_KEY). Fala com o administrador.
        </p>
      )}

      {key && !key.readable && (
        <p className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          A chave guardada já não se consegue ler (a configuração do servidor mudou). Cola-a de novo.
        </p>
      )}

      {!editable && (
        <p className="text-sm text-stone-600 dark:text-stone-300">
          {key ? `Este projeto tem chave própria (${key.provider_label}).` : "Este projeto não tem chave própria."} Só o dono a pode mudar.
        </p>
      )}

      {editable && state.enabled && (
        <>
          <Field label="Fornecedor" hint={provider?.hint}>
            <select className={inputClass} value={draft.provider} disabled={busy} onChange={(e) => setDraft({ ...draft, provider: e.target.value })}>
              {state.providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Chave de API">
            <input
              className={inputClass}
              type="password"
              autoComplete="off"
              value={draft.api_key}
              onChange={update("api_key")}
              disabled={busy}
              placeholder={sameProvider && key.readable ? `Guardada (${key.key_hint}). Deixa vazio para manter.` : "Cola aqui a chave"}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Modelo de chat" hint="Responde às perguntas e conduz o assistente.">
              <input
                className={inputClass}
                value={draft.chat_model}
                onChange={update("chat_model")}
                disabled={busy}
                placeholder={provider?.default_chat_model || "nome do modelo"}
              />
            </Field>
            <Field label="Modelo utilitário" hint="Mais barato, para tarefas curtas. Vazio usa o de chat.">
              <input
                className={inputClass}
                value={draft.utility_model}
                onChange={update("utility_model")}
                disabled={busy}
                placeholder={provider?.default_utility_model || "igual ao de chat"}
              />
            </Field>
          </div>

          {testResult && (
            <ul className="space-y-1 text-sm">
              {Object.entries(testResult.results).map(([role, r]) => (
                <li key={role} className={`flex items-start gap-2 ${r.ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                  {r.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <AlertCircle className="mt-0.5 size-4 shrink-0" />}
                  <span className="min-w-0 break-words">
                    {r.model}: {r.ok ? "responde" : r.error}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            {key && (
              <Button variant="ghost" icon={Trash2} busy={working === "remove"} disabled={busy} onClick={handleRemove}>
                Remover
              </Button>
            )}
            <Button icon={PlugZap} busy={working === "test"} disabled={busy} onClick={handleTest}>
              Testar
            </Button>
            <Button variant="primary" icon={Save} busy={working === "save"} disabled={busy} onClick={handleSave}>
              Guardar
            </Button>
          </div>
        </>
      )}

      <ErrorText>{error}</ErrorText>
    </div>
  );
}
