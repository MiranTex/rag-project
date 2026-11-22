import { useEffect, useRef, useState } from "react";
import { AlertCircle, FileText, Loader2, Pencil, RotateCcw, ScanText, Search, Trash2, Upload } from "lucide-react";
import { Badge, Button, Menu, inputClass, useConfirm } from "./ui";

// Botão "Carregar PDFs" (vários de cada vez) para o cabeçalho da página.
export function UploadButton({ uploading, onUpload, label = "Carregar PDFs", variant = "primary" }) {
  const inputRef = useRef(null);
  return (
    <>
      <Button variant={variant} icon={Upload} busy={uploading} onClick={() => inputRef.current?.click()}>
        {label}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        disabled={uploading}
        onChange={(e) => {
          if (e.target.files?.length) onUpload([...e.target.files]);
          // Permite voltar a escolher o mesmo ficheiro.
          e.target.value = "";
        }}
      />
    </>
  );
}

// Zona onde se podem largar PDFs: envolve a lista sem lhe ocupar espaço; só aparece um aviso enquanto se arrasta.
export function UploadDropTarget({ uploading, onUpload, children }) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  return (
    <div
      className="relative min-h-40"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current += 1;
        setDragging(true);
      }}
      onDragOver={(e) => hasFiles(e) && e.preventDefault()}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (!depth.current) setDragging(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current = 0;
        setDragging(false);
        const files = [...e.dataTransfer.files].filter((f) => f.type === "application/pdf" || /\.pdf$/i.test(f.name));
        if (!uploading && files.length) onUpload(files);
      }}
    >
      {children}
      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-accent-500 bg-accent-50/90 text-sm font-medium text-accent-700 dark:bg-accent-500/15 dark:text-accent-300">
          <Upload className="mr-2 size-4" />
          Larga os PDFs para os carregar
        </div>
      )}
    </div>
  );
}

// Aqui o que se renomeia é o nome do ficheiro, por isso a lista mostra-o (e não o título da ficha).
const displayName = (filename) => filename.replace(/\.pdf$/i, "");
const normalize = (text) =>
  (text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
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
    <div className="px-4 py-2.5">
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
        aria-label={`Nome novo para ${doc.filename}`}
        className={inputClass}
      />
      <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">Enter para guardar · Esc para cancelar</p>
    </div>
  );
}

function DocumentStatus({ doc, busy, failed, pending }) {
  if (busy) return <span>{doc.status === "extracting" ? "A extrair texto…" : "A indexar…"}</span>;
  if (failed)
    return (
      <span className="block truncate text-red-600 dark:text-red-400" title={doc.error || undefined}>
        Falhou · {doc.error || "erro desconhecido"}
      </span>
    );
  if (pending && doc.error)
    return (
      <Badge tone="warning" title={doc.error}>
        Indexação falhou · aprova de novo
      </Badge>
    );
  if (pending)
    return (
      <Badge tone="accent">
        Por rever{doc.alert_count > 0 && ` · ${doc.alert_count} alerta${doc.alert_count > 1 ? "s" : ""}`}
      </Badge>
    );
  return (
    <span>
      {doc.page_count > 0 && `${doc.page_count} pág. · `}
      {doc.chunk_count} excertos
    </span>
  );
}

function DocumentItem({ doc, canUpload, canReview, onReview, onRename, onReindex, onDelete }) {
  const confirm = useConfirm();
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

  async function remove() {
    const ok = await confirm({
      title: "Remover documento?",
      message: `“${displayName(doc.filename)}” sai da base de conhecimento e deixa de aparecer nas respostas. Não se pode desfazer.`,
      confirmLabel: "Remover",
    });
    if (ok) onDelete(doc.document_id);
  }

  // Enquanto há um trabalho em background, só se pode remover (cancela o que estiver em fila).
  const items = [
    {
      label: pending ? "Rever texto" : "Ver texto extraído",
      icon: ScanText,
      onSelect: () => onReview(doc.document_id),
      hidden: busy || failed,
    },
    { label: "Renomear", icon: Pencil, onSelect: () => setRenaming(true), hidden: busy || !canReview },
    { label: "Extrair de novo", icon: RotateCcw, onSelect: () => onReindex(doc.document_id), hidden: busy || !canUpload },
    { label: "Remover", icon: Trash2, onSelect: remove, danger: true, hidden: !canUpload },
  ];

  return (
    <li className="flex items-center gap-1 pr-2">
      <button
        type="button"
        onClick={() => onReview(doc.document_id)}
        disabled={busy || failed}
        className="flex min-w-0 flex-1 items-start gap-3 rounded-xl px-4 py-2.5 text-left enabled:hover:bg-stone-50 disabled:cursor-default dark:enabled:hover:bg-stone-800/60"
      >
        {busy ? (
          <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-stone-400 dark:text-stone-500" />
        ) : failed ? (
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400" />
        ) : (
          <FileText className={`mt-0.5 size-4 shrink-0 ${pending ? "text-accent-500" : "text-stone-400 dark:text-stone-500"}`} />
        )}
        <span className="min-w-0 flex-1">
          <span
            className="block truncate text-sm font-medium text-stone-800 dark:text-stone-200"
            title={[doc.filename, doc.title, doc.original_filename && `Original: ${doc.original_filename}`].filter(Boolean).join("\n")}
          >
            {displayName(doc.filename)}
          </span>
          <span className="mt-0.5 block text-xs text-stone-500 dark:text-stone-400">
            <DocumentStatus doc={doc} busy={busy} failed={failed} pending={pending} />
          </span>
        </span>
      </button>
      <Menu items={items} label={`Ações para ${doc.filename}`} />
    </li>
  );
}

function Group({ title, docs, itemProps }) {
  return (
    <section>
      <h2 className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">
        {title}
        <span className="tabular-nums">{docs.length}</span>
      </h2>
      {/* Como o ListCard, mas sem overflow-hidden: o menu de cada linha tem de poder sair do cartão. */}
      <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
        {docs.map((doc) => (
          <DocumentItem key={doc.document_id} doc={doc} {...itemProps} />
        ))}
      </ul>
    </section>
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
    <div className="space-y-6">
      {documents.length > 1 && (
        <label className="relative block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-stone-400 dark:text-stone-500" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Procurar por nome, título ou ficheiro original"
            aria-label="Procurar documento"
            className={`${inputClass} pl-8`}
          />
        </label>
      )}

      {uploadingName && (
        <div className="flex items-center gap-3 rounded-xl border border-stone-200 px-4 py-2.5 text-sm text-stone-600 dark:border-stone-800 dark:text-stone-400">
          <Loader2 className="size-4 shrink-0 animate-spin" />
          <span className="min-w-0">
            <span className="block truncate">{uploadingName}</span>
            <span className="block text-xs text-stone-500 dark:text-stone-400">A enviar…</span>
          </span>
        </div>
      )}

      {processing.length > 0 && <Group title="Em processamento" docs={processing} itemProps={itemProps} />}
      {pending.length > 0 && <Group title="Precisa de atenção" docs={pending} itemProps={itemProps} />}

      {indexed.length ? (
        <Group title="Indexados" docs={indexed} itemProps={itemProps} />
      ) : (
        <section>
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">Indexados</h2>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            {terms.length ? "Nenhum documento corresponde à pesquisa." : "Nenhum documento indexado."}
          </p>
        </section>
      )}
    </div>
  );
}
