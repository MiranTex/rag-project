import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { BookmarkPlus, ChevronLeft, ChevronRight, ExternalLink, FolderPlus, Pin, X } from "lucide-react";
import { research } from "../api";
import { Button, ErrorText, Modal, Spinner, documentLabel, inputClass } from "../components/ui";

// Projetos da pessoa, o leitor de documentos e "guardar no projeto", disponíveis em todas as páginas.
const ResearchContext = createContext(null);

export function useResearch() {
  return useContext(ResearchContext);
}

// A janela vive em components/ui; reexportada para quem a importava daqui.
export { Modal };

// Escolher o projeto onde guardar (ou criar um novo). Só aparecem projetos onde a pessoa pode escrever.
function ProjectPicker({ request, projects, lastProjectId, onDone, onCreated }) {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const writable = projects.filter((p) => p.my_role !== "viewer");

  async function choose(projectId) {
    setBusy(projectId);
    setError("");
    try {
      await request.action(projectId);
      onDone(projectId);
    } catch (err) {
      setError(err.message);
      setBusy("");
    }
  }

  async function create(event) {
    event.preventDefault();
    setBusy("new");
    try {
      const detail = await research.createProject({ title: title.trim() });
      onCreated();
      await choose(detail.project.project_id);
    } catch (err) {
      setError(err.message);
      setBusy("");
    }
  }

  return (
    <Modal title={request.title} onClose={() => onDone(null)}>
      <ul className="space-y-1">
        {writable.map(({ project }) => (
          <li key={project.project_id}>
            <button
              type="button"
              disabled={!!busy}
              onClick={() => choose(project.project_id)}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-stone-200/70 dark:hover:bg-stone-800 ${
                project.project_id === lastProjectId ? "bg-stone-200/50 dark:bg-stone-800/60" : ""
              }`}
            >
              <span className="min-w-0 flex-1 truncate">{project.title}</span>
              {busy === project.project_id && <Spinner />}
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={create} className="mt-4 flex gap-2">
        <input className={inputClass} placeholder="Novo projeto" value={title} onChange={(e) => setTitle(e.target.value)} required />
        <Button type="submit" icon={FolderPlus} busy={busy === "new"}>
          Criar
        </Button>
      </form>
      <div className="mt-3">
        <ErrorText>{error}</ErrorText>
      </div>
    </Modal>
  );
}

function highlightIn(text, excerpt) {
  if (!excerpt) return [text];
  // Procura o início do excerto na página (os excertos podem ter espaços normalizados).
  const probe = excerpt.replace(/\s+/g, " ").trim().slice(0, 60);
  const normalized = text.replace(/\s+/g, " ");
  const start = probe ? normalized.indexOf(probe) : -1;
  if (start < 0) return [normalized];
  const end = Math.min(normalized.length, start + excerpt.replace(/\s+/g, " ").trim().length);
  return [normalized.slice(0, start), normalized.slice(start, end), normalized.slice(end)];
}

function Reader({ target, onClose, onSave, onPin }) {
  const [card, setCard] = useState(null);
  const [page, setPage] = useState(target.page || 1);
  const [pageData, setPageData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    research.document(target.document_id).then(setCard, (err) => setError(err.message));
  }, [target.document_id]);

  useEffect(() => {
    setPageData(null);
    research.page(target.document_id, page).then(setPageData, (err) => setError(err.message));
  }, [target.document_id, page]);

  const highlight = page === target.page ? target.text : "";
  const parts = pageData ? highlightIn(pageData.text, highlight) : [];

  function saveSelection() {
    const selected = window.getSelection()?.toString().trim();
    onSave({
      kind: "excerpt",
      title: documentLabel(card || target),
      text: selected || highlight || pageData?.text.slice(0, 1500) || "",
      source: { document_id: target.document_id, filename: card?.filename || target.filename, page, title: card?.title || "" },
    });
  }

  return (
    <Modal title={card ? documentLabel(card) : "…"} onClose={onClose} wide>
      {card && (
        <p className="mb-3 text-sm text-stone-500 dark:text-stone-400">
          {[card.authors.join(", "), card.year].filter(Boolean).join(" · ")}
        </p>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant="ghost" icon={ChevronLeft} disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Página anterior" />
        <span className="text-sm text-stone-600 dark:text-stone-400">
          Página {page}
          {pageData ? ` de ${pageData.page_count}` : ""}
        </span>
        <Button
          variant="ghost"
          icon={ChevronRight}
          disabled={!pageData || page >= pageData.page_count}
          onClick={() => setPage(page + 1)}
          aria-label="Página seguinte"
        />
        <div className="ml-auto flex flex-wrap gap-2">
          <Button icon={ExternalLink} onClick={() => research.openPdf(target.document_id, page).catch((err) => setError(err.message))}>
            PDF
          </Button>
          <Button icon={Pin} onClick={() => onPin(target.document_id)}>
            Fixar no projeto
          </Button>
          <Button variant="primary" icon={BookmarkPlus} onClick={saveSelection} title="Guarda o texto selecionado (ou o excerto destacado)">
            Guardar destaque
          </Button>
        </div>
      </div>
      <ErrorText>{error}</ErrorText>
      {!pageData && !error && <Spinner label="A carregar a página…" />}
      {pageData && (
        <div className="whitespace-pre-line rounded-lg border border-stone-200 bg-white p-4 text-sm leading-relaxed text-stone-800 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-200">
          {pageData.excluded ? (
            <span className="text-stone-500">Esta página foi excluída na revisão.</span>
          ) : parts.length === 3 ? (
            <>
              {parts[0]}
              <mark className="rounded bg-accent-100 px-0.5 text-inherit dark:bg-accent-500/30">{parts[1]}</mark>
              {parts[2]}
            </>
          ) : (
            parts[0] || <span className="text-stone-500">Página sem texto.</span>
          )}
        </div>
      )}
    </Modal>
  );
}

// O projeto ativo (onde o chat pesquisa) vem de fora: quem envia as perguntas precisa dele.
// `chat`: a conversa guardada no projeto e as ações para a abrir ou começar (vêm do App, que tem o chat).
export function ResearchProvider({ notify, activeProjectId, setActiveProjectId, chat = {}, children }) {
  const [projects, setProjects] = useState([]);
  const [lastProjectId, setLastProjectId] = useState("");
  const [reader, setReader] = useState(null);
  const [picker, setPicker] = useState(null);

  const refreshProjects = useCallback(
    () =>
      research
        .projects()
        .then((list) => {
          setProjects(list);
          return list;
        })
        .catch(() => setProjects([])),
    [],
  );
  useEffect(() => {
    // Projeto ativo guardado de outra sessão que já não existe (ou de que a pessoa saiu): volta a toda a base.
    refreshProjects().then((list) => {
      if (list && activeProjectId && !list.some((p) => p.project.project_id === activeProjectId)) setActiveProjectId("");
    });
  }, [refreshProjects]);

  const saveItem = useCallback(
    (item) =>
      setPicker({
        title: "Guardar no caderno de…",
        action: (projectId) => research.addItem(projectId, item),
        message: "Guardado no caderno do projeto.",
      }),
    [],
  );

  const pinDocument = useCallback(
    (documentId) =>
      setPicker({
        title: "Fixar o documento em…",
        action: (projectId) => research.pin(projectId, documentId),
        message: "Documento fixado no projeto.",
      }),
    [],
  );

  const value = {
    projects,
    refreshProjects,
    activeProjectId,
    setActiveProjectId,
    openReader: setReader,
    saveItem,
    pinDocument,
    notify,
    ...chat,
  };

  return (
    <ResearchContext.Provider value={value}>
      {children}
      {reader && <Reader target={reader} onClose={() => setReader(null)} onSave={saveItem} onPin={pinDocument} />}
      {picker && (
        <ProjectPicker
          request={picker}
          projects={projects}
          lastProjectId={lastProjectId}
          onCreated={refreshProjects}
          onDone={(projectId) => {
            if (projectId) {
              setLastProjectId(projectId);
              notify(picker.message);
              refreshProjects();
            }
            setPicker(null);
          }}
        />
      )}
    </ResearchContext.Provider>
  );
}
