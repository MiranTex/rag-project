import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FolderPlus } from "lucide-react";
import { research } from "../api";
import PageShell from "../components/PageShell";
import { Button, Empty, ErrorText, inputClass } from "../components/ui";
import { useResearch } from "../research/ResearchContext";

const ROLE_LABELS = { owner: "teu", editor: "editas", viewer: "só leitura" };

export default function ProjectsPage({ onOpenSidebar }) {
  const { projects, refreshProjects } = useResearch();
  const navigate = useNavigate();
  const [draft, setDraft] = useState({ title: "", question: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const detail = await research.createProject({ title: draft.title.trim(), question: draft.question.trim() });
      await refreshProjects();
      navigate(`/projetos/${detail.project.project_id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <PageShell
      title="Projetos"
      description="Um projeto junta a tua pergunta de investigação, os documentos que escolheste, as notas e as conversas. O chat de um projeto pesquisa só nos documentos dele."
      onOpenSidebar={onOpenSidebar}
    >
      <form onSubmit={create} className="mb-8 space-y-2 rounded-xl border border-stone-200 p-4 dark:border-stone-800">
        <input
          className={inputClass}
          placeholder="Título do projeto (ex.: Dissertação sobre recomendação de livros)"
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          required
        />
        <textarea
          className={inputClass}
          rows={2}
          placeholder="Pergunta de investigação (opcional, podes mudar depois)"
          value={draft.question}
          onChange={(e) => setDraft({ ...draft, question: e.target.value })}
        />
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" icon={FolderPlus} busy={busy}>
            Criar projeto
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </form>

      {projects.length === 0 ? (
        <Empty>Ainda não tens projetos.</Empty>
      ) : (
        <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {projects.map(({ project, my_role, document_count, item_count }) => (
            <li key={project.project_id}>
              <Link to={`/projetos/${project.project_id}`} className="block px-4 py-3 hover:bg-stone-50 dark:hover:bg-stone-800/50">
                <span className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate font-medium">{project.title}</span>
                  <span className="text-xs text-stone-500">{ROLE_LABELS[my_role]}</span>
                </span>
                {project.question && <span className="mt-0.5 block truncate text-sm text-stone-500 dark:text-stone-400">{project.question}</span>}
                <span className="mt-1 block text-xs text-stone-500">
                  {document_count} documento{document_count === 1 ? "" : "s"} · {item_count} entrada{item_count === 1 ? "" : "s"} no caderno
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
