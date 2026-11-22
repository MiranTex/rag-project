import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Download, FolderOpen, FolderPlus, Menu, Trash2, X } from "lucide-react";
import { useResearch } from "../research/ResearchContext";
import { useConfirm } from "./ui";
import Composer from "./Composer";
import Message from "./Message";
import ProjectFromChat from "./ProjectFromChat";

// Onde a conversa decorre: o projeto (com ligação para ele) e a conversa guardada nele.
function ProjectContext() {
  const { projects, activeProjectId, setActiveProjectId, conversation } = useResearch();
  if (!activeProjectId) return null;
  const project = projects.find((p) => p.project.project_id === activeProjectId)?.project;
  return (
    <div className="flex min-w-0 items-center gap-1 rounded-full border border-stone-200 py-0.5 pl-2.5 pr-1 text-sm dark:border-stone-700">
      <FolderOpen className="size-4 shrink-0 text-accent-600 dark:text-accent-400" />
      <Link to={`/projetos/${activeProjectId}`} className="truncate font-medium hover:underline" title="Abrir o projeto">
        {project?.title || "Projeto"}
      </Link>
      <span className="hidden truncate text-stone-500 dark:text-stone-400 sm:inline">
        · {conversation?.title || "nova conversa"}
        {conversation && !conversation.canEdit ? " (de outra pessoa: continuar cria uma cópia tua)" : ""}
      </span>
      <button
        type="button"
        onClick={() => setActiveProjectId("")}
        title="Sair do projeto (pesquisar em toda a base)"
        aria-label="Sair do projeto"
        className="rounded-full p-1 text-stone-500 hover:bg-stone-100 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}

function EmptyState({ documentCount, pendingCount, knowsDocuments }) {
  if (!knowsDocuments) {
    return (
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">O que queres saber?</h1>
        <p className="mt-2 text-stone-500 dark:text-stone-400">
          As respostas vêm dos documentos da base de conhecimento, com a página de onde saiu cada informação.
        </p>
      </div>
    );
  }
  if (documentCount === 0) {
    return (
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Ainda não há documentos</h1>
        <p className="mt-2 text-stone-500 dark:text-stone-400">
          {pendingCount > 0
            ? `Tens ${pendingCount} documento${pendingCount > 1 ? "s" : ""} à espera de revisão na página Documentos.`
            : "Adiciona um PDF na página Documentos. Depois de rever o texto, podes fazer perguntas sobre ele."}
        </p>
      </div>
    );
  }
  return (
    <div className="text-center">
      <h1 className="text-2xl font-semibold tracking-tight">O que queres saber?</h1>
      <p className="mt-2 text-stone-500 dark:text-stone-400">
        As respostas vêm de {documentCount === 1 ? "1 documento indexado" : `${documentCount} documentos indexados`}, com
        a página de onde saiu cada informação.
      </p>
    </div>
  );
}

export default function ChatPanel({
  messages,
  asking,
  onClear,
  onExport,
  onOpenSidebar,
  documents,
  pendingCount,
  knowsDocuments,
  canCreateProject = false,
  onMessageChange,
  ...composerProps
}) {
  const streamRef = useRef(null);
  const confirm = useConfirm();
  const { conversation, activeProjectId } = useResearch();
  const [creatingProject, setCreatingProject] = useState(false);

  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);


  const empty = messages.length === 0;
  const composer = (
    <Composer asking={asking} {...composerProps} />
  );

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col bg-white dark:bg-stone-900">
      <header className="flex h-14 shrink-0 items-center gap-2 px-3 md:px-5">
        <button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Abrir menu"
          className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 md:hidden"
        >
          <Menu className="size-5" />
        </button>
        <ProjectContext />
        {!empty && (
          <div className="ml-auto flex items-center gap-1">
            {canCreateProject && !activeProjectId && (
              <button
                type="button"
                onClick={() => setCreatingProject(true)}
                disabled={asking}
                title="Criar um projeto a partir desta conversa"
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-800 dark:hover:text-stone-200 disabled:opacity-50"
              >
                <FolderPlus className="size-[18px]" />
                <span className="hidden sm:inline">Criar projeto</span>
              </button>
            )}
            <button
              type="button"
              onClick={onExport}
              title="Exportar conversa (JSON)"
              aria-label="Exportar conversa"
              className="rounded-md p-1.5 text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-800 dark:hover:text-stone-200"
            >
              <Download className="size-[18px]" />
            </button>
            <button
              type="button"
              onClick={async () => {
                const saved = !!conversation;
                const ok = await confirm({
                  title: "Apagar a conversa?",
                  message: saved
                    ? "Sai do ecrã; a conversa continua guardada no projeto (no separador Conversas)."
                    : "Esta conversa não está guardada em nenhum projeto e não se pode recuperar.",
                  confirmLabel: saved ? "Limpar o ecrã" : "Apagar",
                });
                if (ok) onClear();
              }}
              title="Apagar conversa"
              aria-label="Apagar conversa"
              className="rounded-md p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
            >
              <Trash2 className="size-[18px]" />
            </button>
          </div>
        )}
      </header>

      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center px-4 pb-[12vh]">
          <div className="w-full max-w-2xl space-y-6">
            <EmptyState documentCount={documents.length} pendingCount={pendingCount} knowsDocuments={knowsDocuments} />
            {composer}
          </div>
        </div>
      ) : (
        <>
          <div ref={streamRef} className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-10 px-4 py-6">
              {messages.map((msg, i) => (
                <Message
                  key={msg.id}
                  msg={msg}
                  pending={asking && i === messages.length - 1}
                  onChange={onMessageChange ? (update) => onMessageChange(msg.id, update) : undefined}
                />
              ))}
            </div>
          </div>
          <div className="shrink-0 px-4 pb-4">
            <div className="mx-auto max-w-3xl">
              {composer}
              <p className="mt-2 text-center text-xs text-stone-400 dark:text-stone-500">
                As respostas podem ter erros. Confirma na página indicada.
              </p>
            </div>
          </div>
        </>
      )}
      {creatingProject && <ProjectFromChat messages={messages} onClose={() => setCreatingProject(false)} />}
    </main>
  );
}
