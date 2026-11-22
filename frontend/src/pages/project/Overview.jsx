import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, MessagesSquare, Settings2 } from "lucide-react";
import { research } from "../../api";
import { Badge, Button, Card, ROLE_LABELS, Section, Stat, statusTone } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";
import Comments from "./Comments";

// Quantas entradas há em cada secção e em que estado estão: o "onde estamos" do projeto.
function SectionProgress({ projectId, structure, items, canEdit, onOpenSettings }) {
  const { sections, statuses } = structure;
  if (!sections.length) {
    return (
      <Card className="p-4 text-sm text-stone-600 dark:text-stone-400">
        O caderno não tem secções.{" "}
        {canEdit && (
          <button type="button" className="font-medium text-accent-700 hover:underline dark:text-accent-400" onClick={onOpenSettings}>
            Definir a estrutura
          </button>
        )}
      </Card>
    );
  }
  const known = new Set(sections.map((s) => s.key));
  const rows = [...sections, { key: "", title: "Outras entradas" }]
    .map((s) => ({ ...s, entries: items.filter((i) => (s.key ? i.section === s.key : !known.has(i.section))) }))
    .filter((s) => s.key || s.entries.length);

  return (
    <ul className="divide-y divide-stone-200 overflow-hidden rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
      {rows.map((s) => {
        const byStatus = statuses.map((status) => [status, s.entries.filter((i) => i.status === status).length]).filter(([, n]) => n);
        return (
          <li key={s.key || "_outras"}>
            <Link
              to={`/projetos/${projectId}/caderno${s.key ? `?seccao=${encodeURIComponent(s.key)}` : ""}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-stone-50 dark:hover:bg-stone-800/50"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{s.title}</p>
                {s.description && <p className="truncate text-xs text-stone-500 dark:text-stone-400">{s.description}</p>}
              </div>
              <div className="hidden flex-wrap justify-end gap-1 sm:flex">
                {byStatus.map(([status, n]) => (
                  <Badge key={status} tone={statusTone(status, statuses)}>
                    {n} {status}
                  </Badge>
                ))}
              </div>
              <span className="w-8 text-right text-sm tabular-nums text-stone-500 dark:text-stone-400">{s.entries.length}</span>
              <ChevronRight className="size-4 text-stone-400" />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

// Visão geral: o que é o projeto, em que ponto está e quem participa. Editar fica nas Definições.
export default function Overview({ detail, currentUserId, onOpenSettings, onShare }) {
  const { chatInProject } = useResearch();
  const { project } = detail;
  const canEdit = detail.my_role !== "viewer";
  const [items, setItems] = useState([]);
  const [conversations, setConversations] = useState(null);

  useEffect(() => {
    research.items(project.project_id).then(setItems, () => setItems([]));
    research.conversations(project.project_id).then(setConversations, () => setConversations([]));
  }, [project.project_id, project.updated_at]);

  const pendingProposals = (conversations || []).reduce((n, c) => n + c.pending_proposals, 0);

  return (
    <>
      {(project.description || !project.question) && (
        <Section>
          <Card className="p-4">
            {project.description ? (
              <p className="whitespace-pre-line text-sm text-stone-700 dark:text-stone-300">{project.description}</p>
            ) : (
              <p className="text-sm text-stone-500 dark:text-stone-400">
                Sem objetivo nem descrição.{" "}
                {canEdit && (
                  <button type="button" className="font-medium text-accent-700 hover:underline dark:text-accent-400" onClick={onOpenSettings}>
                    Acrescentar
                  </button>
                )}
              </p>
            )}
          </Card>
        </Section>
      )}

      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Entradas" value={items.length} />
        <Stat label="Documentos" value={detail.documents.length} />
        <Stat label="Conversas" value={conversations ? conversations.length : "…"} hint={pendingProposals ? `${pendingProposals} propostas por decidir` : undefined} />
        <Stat label="Pessoas" value={detail.members.length} />
      </div>

      <Section
        title="Caderno por secção"
        actions={
          canEdit && (
            <Button size="sm" variant="ghost" icon={Settings2} onClick={onOpenSettings}>
              Estrutura
            </Button>
          )
        }
      >
        <SectionProgress projectId={project.project_id} structure={project.structure} items={items} canEdit={canEdit} onOpenSettings={onOpenSettings} />
      </Section>

      <Section>
        <Card className="flex flex-wrap items-center gap-3 border-accent-200 bg-accent-50/50 p-4 dark:border-accent-500/30 dark:bg-accent-500/5">
          <MessagesSquare className="size-5 shrink-0 text-accent-600 dark:text-accent-400" />
          <p className="min-w-0 flex-1 text-sm text-stone-700 dark:text-stone-300">
            O assistente conhece o caderno e {detail.documents.length ? "pesquisa nos documentos do projeto" : "o objetivo do projeto"}. Pede-lhe para
            completar, rever ou organizar; o que propuser só entra quando aceitares.
          </p>
          <Button variant="primary" icon={MessagesSquare} onClick={() => chatInProject(project.project_id)}>
            Conversar
          </Button>
        </Card>
      </Section>

      <Section
        title="Pessoas"
        actions={
          <Button size="sm" variant="ghost" onClick={onShare}>
            {detail.my_role === "owner" ? "Gerir" : "Ver"}
          </Button>
        }
      >
        <div className="flex flex-wrap gap-2">
          {detail.members.map((m) => (
            <span key={m.user_id} className="inline-flex items-center gap-2 rounded-full border border-stone-200 py-1 pl-1 pr-3 text-sm dark:border-stone-800">
              <span className="flex size-6 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold uppercase text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                {(m.display_name || m.username).slice(0, 1)}
              </span>
              {m.display_name || m.username}
              <span className="text-xs text-stone-500 dark:text-stone-400">{ROLE_LABELS[m.role]}</span>
            </span>
          ))}
        </div>
      </Section>

      <Section title="Comentários do projeto">
        <Comments projectId={project.project_id} currentUserId={currentUserId} isOwner={detail.my_role === "owner"} />
      </Section>
    </>
  );
}
