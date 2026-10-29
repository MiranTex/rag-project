import { useEffect, useRef, useState } from "react";
import {
  FileText,
  Loader2,
  MoreHorizontal,
  RotateCcw,
  ScanText,
  SquarePen,
  Trash2,
  Upload,
  X,
  Monitor,
  Moon,
  Sun,
} from "lucide-react";

function useClickOutside(ref, onOutside, active) {
  useEffect(() => {
    if (!active) return undefined;
    function handle(event) {
      if (ref.current && !ref.current.contains(event.target)) onOutside();
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [ref, onOutside, active]);
}

function UploadDropzone({ uploading, onUpload }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  function pick(files) {
    const file = files?.[0];
    if (file) onUpload(file);
  }

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!uploading) pick(e.dataTransfer.files);
      }}
      className={`flex cursor-pointer items-center gap-3 rounded-lg border border-dashed px-3 py-2.5 text-sm transition-colors ${
        dragging
          ? "border-accent-500 bg-accent-50 dark:bg-accent-500/15 text-accent-700 dark:text-accent-400"
          : "border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-400 hover:border-stone-400 dark:hover:border-stone-600 hover:bg-stone-100 dark:hover:bg-stone-800"
      } ${uploading ? "pointer-events-none opacity-60" : ""}`}
    >
      <Upload className="size-4 shrink-0" />
      <span>
        <span className="font-medium text-stone-800 dark:text-stone-200">Adicionar PDF</span>
        <span className="block text-xs text-stone-500 dark:text-stone-400">ou arrasta o ficheiro para aqui</span>
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="sr-only"
        disabled={uploading}
        onChange={(e) => {
          pick(e.target.files);
          // Permite voltar a escolher o mesmo ficheiro.
          e.target.value = "";
        }}
      />
    </label>
  );
}

function DocumentMenu({ doc, onReview, onReindex, onDelete, onClose }) {
  const ref = useRef(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useClickOutside(ref, onClose, true);

  const item = "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-stone-100 dark:hover:bg-stone-700";

  return (
    <div
      ref={ref}
      className="animate-fade-up absolute right-1 top-9 z-20 w-48 rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 p-1 shadow-lg dark:shadow-black/40"
    >
      <button type="button" className={item} onClick={() => onReview(doc.document_id)}>
        <ScanText className="size-4 text-stone-500 dark:text-stone-400" />
        {doc.status === "pending_review" ? "Rever texto" : "Ver texto extraído"}
      </button>
      <button type="button" className={item} onClick={() => onReindex(doc.document_id)}>
        <RotateCcw className="size-4 text-stone-500 dark:text-stone-400" />
        Extrair de novo
      </button>
      <div className="my-1 h-px bg-stone-100 dark:bg-stone-800" />
      {confirmDelete ? (
        <button
          type="button"
          className={`${item} bg-red-50 dark:bg-red-950/40 font-medium text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-950/60`}
          onClick={() => onDelete(doc.document_id)}
        >
          <Trash2 className="size-4" />
          Confirmar remoção
        </button>
      ) : (
        <button type="button" className={`${item} text-red-700 dark:text-red-300`} onClick={() => setConfirmDelete(true)}>
          <Trash2 className="size-4" />
          Remover
        </button>
      )}
    </div>
  );
}

function DocumentItem({ doc, onReview, onReindex, onDelete }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pending = doc.status === "pending_review";

  function act(handler) {
    return (id) => {
      setMenuOpen(false);
      handler(id);
    };
  }

  return (
    <li className="group relative">
      <button
        type="button"
        onClick={() => onReview(doc.document_id)}
        className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 pr-9 text-left hover:bg-stone-100 dark:hover:bg-stone-800"
      >
        <FileText className={`mt-0.5 size-4 shrink-0 ${pending ? "text-accent-500" : "text-stone-400 dark:text-stone-500"}`} />
        <span className="min-w-0">
          <span
            className="block truncate text-sm text-stone-800 dark:text-stone-200"
            title={doc.title ? `${doc.title}\n${doc.filename}` : doc.filename}
          >
            {doc.title || doc.filename}
          </span>
          <span className="block text-xs text-stone-500 dark:text-stone-400">
            {pending ? (
              <span className="font-medium text-accent-600 dark:text-accent-400">
                Por rever{doc.alert_count > 0 && ` · ${doc.alert_count} alerta${doc.alert_count > 1 ? "s" : ""}`}
              </span>
            ) : (
              <>
                {doc.year && `${doc.year} · `}
                {doc.page_count > 0 && `${doc.page_count} pág. · `}
                {doc.chunk_count} excertos
              </>
            )}
          </span>
        </span>
      </button>
      <button
        type="button"
        aria-label={`Ações para ${doc.filename}`}
        onClick={() => setMenuOpen((open) => !open)}
        className={`absolute right-1.5 top-1.5 rounded-md p-1 text-stone-500 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-800 dark:hover:text-stone-200 ${
          menuOpen ? "bg-stone-200 dark:bg-stone-700 opacity-100" : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
        }`}
      >
        <MoreHorizontal className="size-4" />
      </button>
      {menuOpen && (
        <DocumentMenu
          doc={doc}
          onReview={act(onReview)}
          onReindex={act(onReindex)}
          onDelete={act(onDelete)}
          onClose={() => setMenuOpen(false)}
        />
      )}
    </li>
  );
}

function HealthDot({ label, ok }) {
  const color = ok === undefined ? "bg-stone-300 dark:bg-stone-600" : ok ? "bg-emerald-500" : "bg-red-500";
  return (
    <span className="flex items-center gap-1.5" title={ok === false ? `${label} indisponível` : label}>
      <span className={`size-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}

const THEME_OPTIONS = [
  { value: "system", label: "Tema do sistema", icon: Monitor },
  { value: "light", label: "Tema claro", icon: Sun },
  { value: "dark", label: "Tema escuro", icon: Moon },
];

function ThemeSwitch({ theme, onThemeChange }) {
  return (
    <div className="ml-auto flex rounded-md bg-stone-200/60 p-0.5 dark:bg-stone-800" role="group" aria-label="Tema">
      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          title={label}
          aria-label={label}
          aria-pressed={theme === value}
          onClick={() => onThemeChange(value)}
          className={`rounded p-1 ${
            theme === value
              ? "bg-white text-stone-900 shadow-sm dark:bg-stone-600 dark:text-stone-100"
              : "text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
          }`}
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  );
}

export default function Sidebar({
  open,
  onClose,
  documents,
  uploadingName,
  onUpload,
  onReview,
  onReindex,
  onDelete,
  onNewChat,
  health,
  theme,
  onThemeChange,
}) {
  const pending = documents.filter((d) => d.status === "pending_review");
  const indexed = documents.filter((d) => d.status !== "pending_review");
  const itemProps = { onReview, onReindex, onDelete };

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-stone-900/30 md:hidden" onClick={onClose} />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-950 transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center justify-between px-4">
          <span className="font-semibold tracking-tight">RAG Study</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onNewChat}
              title="Nova conversa"
              aria-label="Nova conversa"
              className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-900 dark:hover:text-stone-100"
            >
              <SquarePen className="size-[18px]" />
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Fechar barra lateral"
              className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 md:hidden"
            >
              <X className="size-[18px]" />
            </button>
          </div>
        </div>

        <div className="px-3">
          <UploadDropzone uploading={!!uploadingName} onUpload={onUpload} />
        </div>

        <nav className="mt-4 flex-1 space-y-5 overflow-y-auto px-2 pb-4">
          {uploadingName && (
            <div className="flex items-center gap-2.5 px-2.5 text-sm text-stone-600 dark:text-stone-400">
              <Loader2 className="size-4 shrink-0 animate-spin" />
              <span className="min-w-0">
                <span className="block truncate">{uploadingName}</span>
                <span className="block text-xs text-stone-500 dark:text-stone-400">A extrair texto…</span>
              </span>
            </div>
          )}

          {pending.length > 0 && (
            <section>
              <h2 className="px-2.5 pb-1 text-xs font-medium text-stone-500 dark:text-stone-400">À espera de revisão</h2>
              <ul>
                {pending.map((doc) => (
                  <DocumentItem key={doc.document_id} doc={doc} {...itemProps} />
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="px-2.5 pb-1 text-xs font-medium text-stone-500 dark:text-stone-400">Documentos</h2>
            {indexed.length ? (
              <ul>
                {indexed.map((doc) => (
                  <DocumentItem key={doc.document_id} doc={doc} {...itemProps} />
                ))}
              </ul>
            ) : (
              <p className="px-2.5 text-sm text-stone-500 dark:text-stone-400">Nenhum documento indexado.</p>
            )}
          </section>
        </nav>

        <footer className="flex items-center gap-4 border-t border-stone-200 dark:border-stone-800 px-4 py-3 text-xs text-stone-500 dark:text-stone-400">
          <HealthDot label="API" ok={health ? !health.offline : undefined} />
          <HealthDot label="Modelo" ok={health?.lmstudio} />
          <HealthDot label="Chroma" ok={health?.chroma} />
          <ThemeSwitch theme={theme} onThemeChange={onThemeChange} />
        </footer>
      </aside>
    </>
  );
}
