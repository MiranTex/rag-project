import { useEffect, useRef, useState } from "react";
import { Download, Menu, Trash2 } from "lucide-react";
import Composer from "./Composer";
import Message from "./Message";

function EmptyState({ documentCount, pendingCount }) {
  if (documentCount === 0) {
    return (
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Ainda não há documentos</h1>
        <p className="mt-2 text-stone-500 dark:text-stone-400">
          {pendingCount > 0
            ? `Tens ${pendingCount} documento${pendingCount > 1 ? "s" : ""} à espera de revisão na barra lateral.`
            : "Adiciona um PDF na barra lateral. Depois de rever o texto, podes fazer perguntas sobre ele."}
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
  selectedDocument,
  ...composerProps
}) {
  const streamRef = useRef(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const scope = documents.find((d) => d.document_id === selectedDocument);

  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!confirmClear) return undefined;
    const timer = setTimeout(() => setConfirmClear(false), 3000);
    return () => clearTimeout(timer);
  }, [confirmClear]);

  const empty = messages.length === 0;
  const composer = (
    <Composer asking={asking} documents={documents} selectedDocument={selectedDocument} {...composerProps} />
  );

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col bg-white dark:bg-stone-900">
      <header className="flex h-14 shrink-0 items-center gap-2 px-3 md:px-5">
        <button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Abrir documentos"
          className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 md:hidden"
        >
          <Menu className="size-5" />
        </button>
        <p className="min-w-0 truncate text-sm text-stone-500 dark:text-stone-400">
          {scope ? (
            <>
              A pesquisar em <span className="font-medium text-stone-800 dark:text-stone-200">{scope.filename}</span>
            </>
          ) : (
            "A pesquisar em todos os documentos"
          )}
        </p>
        {!empty && (
          <div className="ml-auto flex items-center gap-1">
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
              onClick={() => {
                if (confirmClear) {
                  setConfirmClear(false);
                  onClear();
                } else {
                  setConfirmClear(true);
                }
              }}
              aria-label="Apagar conversa"
              className={`flex items-center gap-1.5 rounded-md p-1.5 text-sm ${
                confirmClear ? "bg-red-50 dark:bg-red-950/40 px-2.5 text-red-700 dark:text-red-300" : "text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-800 dark:hover:text-stone-200"
              }`}
            >
              <Trash2 className="size-[18px]" />
              {confirmClear && "Apagar conversa?"}
            </button>
          </div>
        )}
      </header>

      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center px-4 pb-[12vh]">
          <div className="w-full max-w-2xl space-y-6">
            <EmptyState documentCount={documents.length} pendingCount={pendingCount} />
            {composer}
          </div>
        </div>
      ) : (
        <>
          <div ref={streamRef} className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-10 px-4 py-6">
              {messages.map((msg, i) => (
                <Message key={msg.id} msg={msg} pending={asking && i === messages.length - 1} />
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
    </main>
  );
}
