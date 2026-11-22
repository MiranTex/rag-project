import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, FolderPlus, NotebookPen, Plus } from "lucide-react";
import { research } from "../api";
import PageShell from "../components/PageShell";
import { Badge, Button, EmptyState, ErrorText, Field, Modal, ROLE_LABELS, inputClass } from "../components/ui";
import { useResearch } from "../research/ResearchContext";

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const formatDate = (value) => (value ? new Date(value).toLocaleDateString("pt-PT", { day: "numeric", month: "short", year: "numeric" }) : "");

function NewProjectModal({ onClose }) {
  const { refreshProjects } = useResearch();
  const navigate = useNavigate();
  const [draft, setDraft] = useState({ title: "", question: "", description: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setDraft({ ...draft, [field]: e.target.value });

  async function create(event) {
    event.preventDefault();
    if (!draft.title.trim()) return;
    setBusy(true);
    setError("");
    try {
      const detail = await research.createProject({
        title: draft.title.trim(),
        question: draft.question.trim(),
        description: draft.description.trim(),
      });
      await refreshProjects();
      navigate(`/projetos/${detail.project.project_id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Novo projeto"
      description="Podes mudar tudo isto depois."
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="new-project" variant="primary" icon={FolderPlus} busy={busy} disabled={!draft.title.trim()}>
            Criar projeto
          </Button>
        </>
      }
    >
      <form id="new-project" onSubmit={create} className="space-y-4">
        <Field label="Título">
          <input className={inputClass} placeholder="ex.: Dissertação sobre recomendação de livros" value={draft.title} onChange={set("title")} required />
        </Field>
        <Field label="Objetivo (opcional)" hint="A pergunta de investigação ou o que queres alcançar com o projeto.">
          <textarea className={inputClass} rows={2} value={draft.question} onChange={set("question")} />
        </Field>
        <Field label="Descrição (opcional)">
          <textarea className={inputClass} rows={3} value={draft.description} onChange={set("description")} />
        </Field>
        <ErrorText>{error}</ErrorText>
      </form>
    </Modal>
  );
}

function ProjectCard({ project, my_role, document_count, item_count }) {
  return (
    <li>
      <Link
        to={`/projetos/${project.project_id}`}
        className="flex h-full flex-col rounded-xl border border-stone-200 bg-white p-4 transition-colors hover:border-stone-300 hover:bg-stone-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50 dark:border-stone-800 dark:bg-stone-900 dark:hover:border-stone-700 dark:hover:bg-stone-800/60"
      >
        <span className="flex items-start gap-2">
          <span className="line-clamp-2 min-w-0 flex-1 font-medium text-stone-900 dark:text-stone-100">{project.title}</span>
          {my_role && (
            <Badge tone={my_role === "owner" ? "accent" : "neutral"} className="shrink-0">
              {ROLE_LABELS[my_role] || my_role}
            </Badge>
          )}
        </span>
        {(project.question || project.description) && (
          <span className="mt-1 line-clamp-2 text-sm text-stone-600 dark:text-stone-400">{project.question || project.description}</span>
        )}
        <span className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-3 text-xs text-stone-500 dark:text-stone-400">
          <span className="inline-flex items-center gap-1">
            <FileText className="size-3.5" />
            {plural(document_count, "documento", "documentos")}
          </span>
          <span className="inline-flex items-center gap-1">
            <NotebookPen className="size-3.5" />
            {plural(item_count, "entrada", "entradas")}
          </span>
          {project.updated_at && <span className="ml-auto">Atualizado a {formatDate(project.updated_at)}</span>}
        </span>
      </Link>
    </li>
  );
}

export default function ProjectsPage({ onOpenSidebar }) {
  const { projects } = useResearch();
  const [creating, setCreating] = useState(false);

  return (
    <PageShell
      title="Projetos"
      subtitle="Um projeto junta o teu objetivo, os documentos que escolheste, as notas e as conversas. O chat de um projeto pesquisa só nos documentos dele."
      width="wide"
      actions={
        projects.length > 0 && (
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Novo projeto
          </Button>
        )
      }
      onOpenSidebar={onOpenSidebar}
    >
      {projects.length === 0 ? (
        <EmptyState
          icon={FolderPlus}
          title="Ainda não tens projetos"
          action={
            <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
              Novo projeto
            </Button>
          }
        >
          Cria um aqui, ou a partir de uma conversa no chat com o botão “Criar projeto” no topo da conversa.
        </EmptyState>
      ) : (
        <>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((entry) => (
              <ProjectCard key={entry.project.project_id} {...entry} />
            ))}
          </ul>
          <p className="mt-6 text-sm text-stone-500 dark:text-stone-400">
            Dica: também podes criar um projeto a partir de uma conversa, com o botão “Criar projeto” no topo do chat.
          </p>
        </>
      )}
      {creating && <NewProjectModal onClose={() => setCreating(false)} />}
    </PageShell>
  );
}
