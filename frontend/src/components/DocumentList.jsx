import { useEffect, useRef, useState } from "react";
import { AlertCircle, FileText, Loader2, MoreHorizontal, Pencil, RotateCcw, ScanText, Search, Trash2, Upload } from "lucide-react";

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

export function UploadDropzone({ uploading, onUpload }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  function pick(files) {
    if (files?.length) onUpload([...files]);
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
        <span className="font-medium text-stone-800 dark:text-stone-200">Adicionar PDFs</span>
        <span className="block text-xs text-stone-500 dark:text-stone-400">ou arrasta os ficheiros para aqui</span>
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
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

function DocumentMenu({ doc, busy, canUpload, canReview, onReview, onRename, onReindex, onDelete, onClose }) {
  const ref = useRef(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useClickOutside(ref, onClose, true);

  const item = "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-stone-100 dark:hover:bg-stone-700";

  return (
    <div
      ref={ref}
      className="animate-fade-up absolute right-1 top-9 z-20 w-48 rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 p-1 shadow-lg dark:shadow-black/40"
    >
      {/* Enquanto há um trabalho em background, só se pode remover (cancela o que estiver em fila). */}
      {!busy && (
        <>
          {doc.status !== "failed" && (
            <button type="button" className={item} onClick={() => onReview(doc.document_id)}>
              <ScanText className="size-4 text-stone-500 dark:text-stone-400" />
              {doc.status === "pending_review" ? "Rever texto" : "Ver texto extraído"}
            </button>
          )}
          {canReview && (
            <button type="button" className={item} onClick={() => onRename(doc.document_id)}>
              <Pencil className="size-4 text-stone-500 dark:text-stone-400" />
              Renomear
            </button>
          )}
          {canUpload && (
            <>
              <button type="button" className={item} onClick={() => onReindex(doc.document_id)}>
                <RotateCcw className="size-4 text-stone-500 dark:text-stone-400" />
                Extrair de novo
              </button>
              <div className="my-1 h-px bg-stone-100 dark:bg-stone-800" />
            </>
          )}
        </>
      )}
      {!canUpload ? null : confirmDelete ? (
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

const displayName = (filename) => filename.replace(/\.pdf$/i, "");
const normalize = (text) =>
  (text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

function RenameInput({ doc, onRename, onDone }) {
  const [value, setValue] = useState(displayName(doc.filename));
  const [saving, setSaving] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.select();
  }, []);

  async function save() {
    const name = value.trim();
    if (!name || name === displayName(doc.filename)) {
      onDone();
      return;
    }
    setSaving(true);
    // Se falhar, o aviso vem do App; o campo fecha na mesma.
    await onRename(doc.document_id, name);
    onDone();
  }

  return (
    <div className="px-2.5 py-1.5">
      <input
        ref={inputRef}
        value={value}
        disabled={saving}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") onDone();
        }}
        onBlur={onDone}
        aria-label="Nome novo"
        className="w-full rounded-md border border-stone-300 bg-white px-2 py-1 text-sm outline-none focus:border-stone-500 dark:border-stone-600 dark:bg-stone-900 dark:focus:border-stone-400"
      />
      <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">Enter para guardar · Esc para cancelar</p>
    </div>
  );
}

function DocumentItem({ doc, canUpload, canReview, onReview, onRename, onReindex, onDelete }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const pending = doc.status === "pending_review";
  const busy = doc.status === "extracting" || doc.status === "indexing";
  const failed = doc.status === "failed";

  if (renaming) {
    return (
      <li>
        <RenameInput doc={doc} onRename={onRename} onDone={() => setRenaming(false)} />
      </li>
    );
  }

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
        disabled={busy || failed}
        className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 pr-9 text-left enabled:hover:bg-stone-100 disabled:cursor-default dark:enabled:hover:bg-stone-800"
      >
        {busy ? (
          <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-stone-400 dark:text-stone-500" />
        ) : failed ? (
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400" />
        ) : (
          <FileText className={`mt-0.5 size-4 shrink-0 ${pending ? "text-accent-500" : "text-stone-400 dark:text-stone-500"}`} />
        )}
        <span className="min-w-0">
          <span
            className="block truncate text-sm text-stone-800 dark:text-stone-200"
            title={[doc.filename, doc.title, doc.original_filename && `Original: ${doc.original_filename}`]
              .filter(Boolean)
              .join("\n")}
          >
            {displayName(doc.filename)}
          </span>
          <span className="block text-xs text-stone-500 dark:text-stone-400" title={doc.error || undefined}>
            {busy ? (
              doc.status === "extracting" ? "A extrair texto…" : "A indexar…"
            ) : failed ? (
              <span className="block truncate text-red-600 dark:text-red-400">Falhou · {doc.error || "erro desconhecido"}</span>
            ) : pending && doc.error ? (
              <span className="font-medium text-amber-700 dark:text-amber-400">Indexação falhou · aprova de novo</span>
            ) : pending ? (
              <span className="font-medium text-accent-600 dark:text-accent-400">
                Por rever{doc.alert_count > 0 && ` · ${doc.alert_count} alerta${doc.alert_count > 1 ? "s" : ""}`}
              </span>
            ) : (
              <>
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
          busy={busy}
          canUpload={canUpload}
          canReview={canReview}
          onReview={act(onReview)}
          onRename={() => {
            setMenuOpen(false);
            setRenaming(true);
          }}
          onReindex={act(onReindex)}
          onDelete={act(onDelete)}
          onClose={() => setMenuOpen(false)}
        />
      )}
    </li>
  );
}

export default function DocumentList({ documents, uploadingName, canUpload, canReview, onReview, onRename, onReindex, onDelete }) {
  const [query, setQuery] = useState("");
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  // Procura no nome, no título e no nome original, sem acentos; a lista fica por ordem de nome.
  const visible = documents
    .filter((d) => {
      const haystack = normalize([d.filename, d.title, d.original_filename].join(" "));
      return terms.every((term) => haystack.includes(term));
    })
    .sort((a, b) => a.filename.localeCompare(b.filename, "pt", { numeric: true }));
  const processing = visible.filter((d) => d.status === "extracting" || d.status === "indexing");
  const pending = visible.filter((d) => d.status === "pending_review" || d.status === "failed");
  const indexed = visible.filter((d) => d.status === "indexed");
  const itemProps = { canUpload, canReview, onReview, onRename, onReindex, onDelete };

  return (
    <div className="space-y-5">
      {documents.length > 1 && (
        <label className="relative block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Procurar documento"
            aria-label="Procurar documento"
            className="w-full rounded-lg border border-stone-200 bg-white py-1.5 pl-8 pr-2.5 text-sm outline-none placeholder:text-stone-400 focus:border-stone-400 dark:border-stone-800 dark:bg-stone-900 dark:placeholder:text-stone-500 dark:focus:border-stone-600"
          />
        </label>
      )}

      {uploadingName && (
        <div className="flex items-center gap-2.5 px-2.5 text-sm text-stone-600 dark:text-stone-400">
          <Loader2 className="size-4 shrink-0 animate-spin" />
          <span className="min-w-0">
            <span className="block truncate">{uploadingName}</span>
            <span className="block text-xs text-stone-500 dark:text-stone-400">A enviar…</span>
          </span>
        </div>
      )}

      {processing.length > 0 && (
        <section>
          <h2 className="px-2.5 pb-1 text-xs font-medium text-stone-500 dark:text-stone-400">Em processamento</h2>
          <ul>
            {processing.map((doc) => (
              <DocumentItem key={doc.document_id} doc={doc} {...itemProps} />
            ))}
          </ul>
        </section>
      )}

      {pending.length > 0 && (
        <section>
          <h2 className="px-2.5 pb-1 text-xs font-medium text-stone-500 dark:text-stone-400">Precisa de atenção</h2>
          <ul>
            {pending.map((doc) => (
              <DocumentItem key={doc.document_id} doc={doc} {...itemProps} />
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="px-2.5 pb-1 text-xs font-medium text-stone-500 dark:text-stone-400">Indexados</h2>
        {indexed.length ? (
          <ul>
            {indexed.map((doc) => (
              <DocumentItem key={doc.document_id} doc={doc} {...itemProps} />
            ))}
          </ul>
        ) : (
          <p className="px-2.5 text-sm text-stone-500 dark:text-stone-400">
            {terms.length ? "Nenhum documento corresponde à pesquisa." : "Nenhum documento indexado."}
          </p>
        )}
      </section>
    </div>
  );
}
