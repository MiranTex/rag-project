import { useEffect, useState } from "react";
import { Check, Copy, Plus, Trash2 } from "lucide-react";
import { accessTokens, mcpUrl, oauth } from "../api";
import { Badge, Button, ErrorText, Field, IconButton, inputClass, Spinner, useConfirm } from "./ui";

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" }) : "nunca");

function CopyBlock({ label, text }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Sem acesso à área de transferência: o texto continua visível para copiar à mão.
    }
  }
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-stone-600 dark:text-stone-300">{label}</span>
        <IconButton icon={copied ? Check : Copy} label={copied ? "Copiado" : `Copiar: ${label}`} onClick={copy} />
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg bg-stone-100 p-3 font-mono text-xs text-stone-800 dark:bg-stone-800 dark:text-stone-200">
        {text}
      </pre>
    </div>
  );
}

// Instruções prontas a copiar, com o token acabado de criar (só se vê esta vez).
function Instructions({ token }) {
  const url = mcpUrl();
  return (
    <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 dark:border-emerald-900/60 dark:bg-emerald-500/5">
      <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
        Copia o token agora: por segurança, não volta a ser mostrado.
      </p>
      <CopyBlock label="Token" text={token} />
      <CopyBlock
        label="Claude Code (no terminal)"
        text={`claude mcp add --transport http base-conhecimento ${url} --header "Authorization: Bearer ${token}"`}
      />
      <CopyBlock
        label="Codex (~/.codex/config.toml; o token fica na variável RAG_MCP_TOKEN)"
        text={`[mcp_servers.base-conhecimento]\nurl = "${url}"\nbearer_token_env_var = "RAG_MCP_TOKEN"\n\n# e no terminal, antes de abrir o Codex:\nexport RAG_MCP_TOKEN="${token}"`}
      />
      <p className="text-xs text-stone-500 dark:text-stone-400">
        Outros clientes MCP: servidor HTTP em {url}, com o cabeçalho Authorization: Bearer e o token.
      </p>
    </div>
  );
}

// Ligar sem token: a aplicação abre esta plataforma no browser e a pessoa autoriza (OAuth). Mostra também as
// aplicações já autorizadas, para revogar. Só aparece se o servidor tiver o login OAuth ligado.
function ConnectedApps({ onSaved }) {
  const confirm = useConfirm();
  const [state, setState] = useState(null);
  const [error, setError] = useState("");

  const load = () => oauth.apps().then(setState, (err) => setError(err.message));
  useEffect(() => {
    load();
  }, []);

  async function revoke(app) {
    const ok = await confirm({
      title: "Revogar o acesso?",
      message: `"${app.name}" deixa de conseguir usar a tua conta. Para voltar a ligar, tens de a autorizar de novo.`,
      confirmLabel: "Revogar",
    });
    if (!ok) return;
    try {
      await oauth.revoke(app.grant_id);
      load();
      onSaved?.("Acesso revogado.");
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <ErrorText>{error}</ErrorText>;
  if (!state?.oauth_enabled) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Sem token (recomendado)</h3>
      <p className="text-sm text-stone-600 dark:text-stone-300">
        Na aplicação, adiciona este endereço. Ela abre esta página no browser, entras com a tua conta e autorizas.
      </p>
      <CopyBlock label="Endereço do servidor" text={state.mcp_url} />
      <ul className="list-disc space-y-1 pl-5 text-sm text-stone-600 dark:text-stone-300">
        <li>
          <strong>claude.ai ou Claude Desktop:</strong> Definições → Conectores → Adicionar conector personalizado, e cola o endereço.
        </li>
        <li>
          <strong>Claude Code:</strong> <code className="text-xs">claude mcp add --transport http base-conhecimento {state.mcp_url}</code> e
          depois <code className="text-xs">/mcp</code> para entrar.
        </li>
      </ul>
      {state.apps.length > 0 && (
        <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {state.apps.map((app) => (
            <li key={app.grant_id} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span className="truncate">{app.name}</span>
                  <Badge tone={app.scopes.includes("write") ? "warning" : "neutral"}>{app.scopes.includes("write") ? "lê e propõe" : "só lê"}</Badge>
                </p>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  autorizada {formatDate(app.created_at)} · último uso {formatDate(app.last_used_at)}
                </p>
              </div>
              <IconButton icon={Trash2} label={`Revogar ${app.name}`} onClick={() => revoke(app)} />
            </li>
          ))}
        </ul>
      )}
      <h3 className="pt-2 text-sm font-semibold">Com token (avançado)</h3>
    </div>
  );
}

// A minha conta → Ligar agentes: login OAuth (se ativo) e tokens pessoais para Claude Code, Codex e outros clientes MCP.
export default function AgentConnections({ onSaved }) {
  const confirm = useConfirm();
  const [tokens, setTokens] = useState(null);
  const [name, setName] = useState("");
  const [canWrite, setCanWrite] = useState(false);
  const [created, setCreated] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    accessTokens.list().then(setTokens, (err) => setError(err.message));
  }, []);

  async function create(event) {
    event.preventDefault();
    if (!name.trim()) return;
    setWorking(true);
    setError("");
    try {
      const token = await accessTokens.create(name.trim(), canWrite);
      setCreated(token);
      setName("");
      setCanWrite(false);
      setTokens(await accessTokens.list());
    } catch (err) {
      setError(err.message);
    } finally {
      setWorking(false);
    }
  }

  async function revoke(token) {
    const ok = await confirm({
      title: "Revogar o token?",
      message: `O agente que usa "${token.name}" deixa de conseguir ligar-se. Não se pode desfazer.`,
      confirmLabel: "Revogar",
    });
    if (!ok) return;
    try {
      await accessTokens.revoke(token.token_id);
      if (created?.token_id === token.token_id) setCreated(null);
      setTokens(await accessTokens.list());
      onSaved?.("Token revogado.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-500 dark:text-stone-400">
        Liga o teu Claude Code, Codex ou outro agente compatível com MCP à base de conhecimento e aos teus projetos. O agente
        pesquisa e lê os documentos com as tuas permissões, e é o teu agente que pensa e escreve: não gasta a chave da plataforma.
        Por defeito só lê; com escrita, o agente pode também propor alterações ao caderno (que alguém da equipa aceita ou
        rejeita) e comentar, sempre assinado com o nome da aplicação ou do token.
      </p>

      <ConnectedApps onSaved={onSaved} />

      <form onSubmit={create} className="flex flex-wrap items-end gap-2">
        <Field label="Nome do token" className="min-w-0 flex-1">
          <input
            className={inputClass}
            value={name}
            maxLength={120}
            placeholder="Para o reconheceres, ex.: Claude Code do portátil"
            onChange={(e) => setName(e.target.value)}
            disabled={working}
          />
        </Field>
        <Button type="submit" variant="primary" icon={Plus} busy={working} disabled={!name.trim()}>
          Criar token
        </Button>
        <label className="flex w-full items-center gap-2 text-sm text-stone-700 dark:text-stone-300">
          <input type="checkbox" checked={canWrite} onChange={(e) => setCanWrite(e.target.checked)} disabled={working} />
          Pode propor alterações ao caderno e comentar nos projetos
        </label>
      </form>

      {created && <Instructions token={created.token} />}

      {!tokens && !error && <Spinner label="A carregar…" />}
      {tokens?.length > 0 && (
        <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {tokens.map((t) => (
            <li key={t.token_id} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span className="truncate">{t.name}</span>
                  <Badge tone={t.scopes.includes("write") ? "warning" : "neutral"}>{t.scopes.includes("write") ? "lê e propõe" : "só lê"}</Badge>
                </p>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  <span className="font-mono">{t.prefix}…</span> · criado {formatDate(t.created_at)} · último uso {formatDate(t.last_used_at)}
                </p>
              </div>
              <IconButton icon={Trash2} label={`Revogar ${t.name}`} onClick={() => revoke(t)} />
            </li>
          ))}
        </ul>
      )}

      <ErrorText>{error}</ErrorText>
    </div>
  );
}
