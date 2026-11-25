import { useEffect, useState } from "react";
import { Check, Copy, Plus, Trash2 } from "lucide-react";
import { accessTokens, mcpUrl } from "../api";
import { Button, ErrorText, Field, IconButton, inputClass, Spinner, useConfirm } from "./ui";

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

// A minha conta → Ligar agentes: tokens pessoais para Claude Code, Codex e outros clientes MCP.
export default function AgentConnections({ onSaved }) {
  const confirm = useConfirm();
  const [tokens, setTokens] = useState(null);
  const [name, setName] = useState("");
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
      const token = await accessTokens.create(name.trim());
      setCreated(token);
      setName("");
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
        Por agora o acesso é só de leitura.
      </p>

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
      </form>

      {created && <Instructions token={created.token} />}

      {!tokens && !error && <Spinner label="A carregar…" />}
      {tokens?.length > 0 && (
        <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {tokens.map((t) => (
            <li key={t.token_id} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{t.name}</p>
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
