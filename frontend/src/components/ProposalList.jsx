import { useState } from "react";
import { Check, FilePen, FilePlus2, X } from "lucide-react";
import { research } from "../api";
import { BASIS } from "../research/basis";
import { useResearch } from "../research/ResearchContext";
import Markdown from "./Markdown";
import { Badge, Button } from "./ui";

// Propostas do agente para o caderno do projeto. Nada é gravado até a pessoa aceitar; a decisão sobre cada
// proposta (aceite/rejeitada) fica na própria mensagem, e por isso também no histórico da conversa do projeto.

const FIELD_LABELS = { section: "secção", ref: "referência", title: "título", text: "texto", status: "estado" };

// Numa alteração: o que muda, campo a campo (o texto antigo riscado por cima do novo).
function Diff({ field, before, after, sectionTitle }) {
  const show = (value) => (field === "section" ? sectionTitle || value : value) || "—";
  if (field === "text") {
    return (
      <div className="mt-2 text-sm">
        {before && <p className="whitespace-pre-line text-stone-400 line-through decoration-stone-300 dark:text-stone-500 dark:decoration-stone-600">{before}</p>}
        <div className="mt-1 text-stone-800 dark:text-stone-200">
          <Markdown size="sm">{after}</Markdown>
        </div>
      </div>
    );
  }
  return (
    <p className="mt-1 text-sm">
      <span className="text-stone-500 dark:text-stone-400">{FIELD_LABELS[field] || field}: </span>
      <span className="text-stone-400 line-through dark:text-stone-500">{show(before)}</span>
      {" → "}
      <span className="font-medium">{show(after)}</span>
    </p>
  );
}

function Proposal({ proposal, projectId, canApply, question, onDecided }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { changes, before = {} } = proposal;
  const isNew = proposal.action === "create";
  const decided = proposal.decision;

  async function accept() {
    setBusy(true);
    setError("");
    try {
      const { basis, via } = proposal;
      // via: a proposta veio de um agente externo (MCP); fica na entrada para se saber de onde veio.
      const origin = { ...(basis && { basis }), ...(via && { via }) };
      if (isNew) await research.addItem(projectId, { kind: "note", ...changes, source: { origin: via ? "mcp" : "chat", question, ...origin } });
      else await research.updateItem(projectId, proposal.item_id, { ...changes, ...origin });
      onDecided("accepted");
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  const Icon = isNew ? FilePlus2 : FilePen;
  const ref = isNew ? changes.ref : before.ref;
  const title = isNew ? changes.title : before.title;
  const basis = BASIS[proposal.basis];

  return (
    <li
      className={`rounded-xl border p-3 ${
        decided ? "border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-900/50" : "border-accent-200 bg-white dark:border-accent-500/30 dark:bg-stone-900"
      }`}
    >
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 size-4 shrink-0 ${decided ? "text-stone-400" : "text-accent-600 dark:text-accent-400"}`} />
        <div className={`min-w-0 flex-1 ${decided ? "opacity-70" : ""}`}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">{isNew ? "Nova entrada" : "Alterar"}</span>
            {ref && <span className="font-mono text-xs font-medium text-stone-600 dark:text-stone-300">{ref}</span>}
            {title && <span className="text-sm font-medium">{title}</span>}
            {isNew && proposal.section_title && <Badge tone="outline">{proposal.section_title}</Badge>}
            {isNew && changes.status && <Badge>{changes.status}</Badge>}
            {basis && (
              <Badge tone={basis.tone} title={basis.title}>
                {basis.label}
              </Badge>
            )}
            {proposal.via && (
              <Badge tone="outline" title="Proposta feita por um agente externo ligado por MCP">
                via {proposal.via}
              </Badge>
            )}
          </div>
          {proposal.reason && <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">{proposal.reason}</p>}
          {isNew ? (
            changes.text && (
              <div className="mt-2 text-sm text-stone-800 dark:text-stone-200">
                <Markdown size="sm">{changes.text}</Markdown>
              </div>
            )
          ) : (
            Object.keys(changes).map((field) => <Diff key={field} field={field} before={before[field]} after={changes[field]} sectionTitle={proposal.section_title} />)
          )}
          {error && <p className="mt-1 text-sm text-red-700 dark:text-red-300">{error}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {decided ? (
            <Badge tone={decided === "accepted" ? "success" : "neutral"}>{decided === "accepted" ? "Aceite" : "Rejeitada"}</Badge>
          ) : canApply ? (
            <>
              <Button size="sm" variant="ghost" icon={X} disabled={busy} onClick={() => onDecided("rejected")}>
                Rejeitar
              </Button>
              <Button size="sm" variant="primary" icon={Check} busy={busy} onClick={accept}>
                Aceitar
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export default function ProposalList({ msg, onChange }) {
  const { projects } = useResearch();
  const proposals = msg.proposals || [];
  if (!proposals.length || !msg.projectId) return null;
  const project = projects.find((p) => p.project.project_id === msg.projectId);
  const canApply = !!project && project.my_role !== "viewer" && !!onChange;
  const pending = proposals.filter((p) => !p.decision);

  // Atualização funcional: duas decisões seguidas não se sobrepõem.
  function decide(ids, decision) {
    onChange((current) => ({ proposals: (current.proposals || []).map((p) => (ids.includes(p.proposal_id) ? { ...p, decision } : p)) }));
  }

  return (
    <section className="mt-4 rounded-2xl bg-accent-50/60 p-3 dark:bg-accent-500/5">
      <div className="mb-2 flex flex-wrap items-center gap-2 px-1">
        <h3 className="text-sm font-semibold">Propostas para o caderno</h3>
        <span className="text-xs text-stone-500 dark:text-stone-400">{pending.length ? `${pending.length} por decidir` : "todas decididas"}</span>
        {!canApply && pending.length > 0 && <span className="text-xs text-stone-500 dark:text-stone-400">· só quem edita o projeto as pode aplicar</span>}
        {canApply && pending.length > 1 && (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => decide(pending.map((p) => p.proposal_id), "rejected")}>
            Rejeitar todas
          </Button>
        )}
      </div>
      <ul className="space-y-2">
        {proposals.map((proposal) => (
          <Proposal
            key={proposal.proposal_id}
            proposal={proposal}
            projectId={msg.projectId}
            canApply={canApply}
            question={msg.question}
            onDecided={(decision) => decide([proposal.proposal_id], decision)}
          />
        ))}
      </ul>
    </section>
  );
}
