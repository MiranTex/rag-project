import { useEffect, useState } from "react";
import { BookOpen, MessageCircle, MessageSquareQuote, NotebookPen, Pencil, Plus, Quote, Search, Sparkles, Trash2 } from "lucide-react";
import { research } from "../../api";
import Markdown from "../../components/Markdown";
import { Button, Empty, ErrorText, Spinner, inputClass } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";
import { Comments } from "./Overview";

const KINDS = {
  note: { label: "Nota", icon: NotebookPen },
  excerpt: { label: "Destaque", icon: Quote },
  answer: { label: "Resposta", icon: MessageSquareQuote },
  draft: { label: "Rascunho", icon: Sparkles },
};

function Item({ item, projectId, canEdit, currentUserId, isOwner, onChanged }) {
  const { openReader } = useResearch();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ title: item.title, text: item.text, tags: item.tags.join(", ") });
  const [showComments, setShowComments] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const kind = KINDS[item.kind] || KINDS.note;
  const Icon = kind.icon;
  const source = item.source || {};

  async function save() {
    try {
      await research.updateItem(projectId, item.item_id, {
        title: draft.title,
        text: draft.text,
        tags: draft.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <li className="rounded-xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
      <div className="mb-1 flex items-center gap-2 text-xs text-stone-500">
        <Icon className="size-3.5" />
        {kind.label} · {item.author} · {new Date(item.created_at).toLocaleDateString("pt-PT")}
        <div className="ml-auto flex items-center gap-0.5">
          <Button variant="ghost" icon={MessageCircle} onClick={() => setShowComments(!showComments)} aria-label="Comentários">
            {item.comment_count || ""}
          </Button>
          {canEdit && <Button variant="ghost" icon={Pencil} aria-label="Editar" onClick={() => setEditing(!editing)} />}
          {canEdit && (
            <Button
              variant="danger"
              icon={Trash2}
              aria-label="Apagar"
              onClick={() => (confirmDelete ? research.deleteItem(projectId, item.item_id).then(onChanged, (err) => setError(err.message)) : setConfirmDelete(true))}
            >
              {confirmDelete ? "Apagar?" : ""}
            </Button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="space-y-2">
          <input className={inputClass} placeholder="Título" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          <textarea className={inputClass} rows={6} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
          <input className={inputClass} placeholder="Etiquetas, separadas por vírgulas" value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} />
          <div className="flex gap-2">
            <Button variant="primary" onClick={save}>
              Guardar
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      ) : (
        <>
          {item.title && <h3 className="font-medium">{item.title}</h3>}
          {source.question && <p className="mt-1 text-sm italic text-stone-500">Pergunta: {source.question}</p>}
          <div className={`mt-1 text-sm ${item.kind === "excerpt" ? "border-l-2 border-accent-400 pl-3 text-stone-700 dark:text-stone-300" : ""}`}>
            {item.kind === "answer" || item.kind === "draft" ? <Markdown>{item.text}</Markdown> : <p className="whitespace-pre-line">{item.text}</p>}
          </div>
          {source.document_id && (
            <button
              type="button"
              onClick={() => openReader({ document_id: source.document_id, page: source.page || 1, text: item.kind === "excerpt" ? item.text : "" })}
              className="mt-2 inline-flex items-center gap-1 text-xs text-accent-700 hover:underline dark:text-accent-400"
            >
              <BookOpen className="size-3.5" />
              {source.title || source.filename}
              {source.page ? `, p. ${source.page}` : ""}
            </button>
          )}
          {source.sources?.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-1.5">
              {source.sources.map((s) => (
                <button
                  key={`${s.document_id}-${s.page}`}
                  type="button"
                  onClick={() => openReader(s)}
                  className="rounded-full border border-stone-200 px-2 py-0.5 text-xs text-stone-600 hover:border-stone-400 dark:border-stone-700 dark:text-stone-400"
                >
                  {s.filename?.replace(/\.pdf$/i, "")} p.{s.page}
                </button>
              ))}
            </p>
          )}
          {item.tags.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-1">
              {item.tags.map((tag) => (
                <span key={tag} className="rounded-full bg-stone-200/70 px-2 py-0.5 text-xs dark:bg-stone-800">
                  #{tag}
                </span>
              ))}
            </p>
          )}
        </>
      )}
      <ErrorText>{error}</ErrorText>
      {showComments && (
        <div className="mt-3 border-t border-stone-200 pt-3 dark:border-stone-800">
          <Comments projectId={projectId} itemId={item.item_id} currentUserId={currentUserId} isOwner={isOwner} />
        </div>
      )}
    </li>
  );
}

export default function Notebook({ projectId, canEdit, currentUserId, isOwner }) {
  const [items, setItems] = useState(null);
  const [filters, setFilters] = useState({ q: "", kind: "", tag: "" });
  const [note, setNote] = useState({ title: "", text: "", tags: "" });
  const [error, setError] = useState("");

  const load = () => research.items(projectId, filters).then(setItems, (err) => setError(err.message));
  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [projectId, filters.q, filters.kind, filters.tag]);

  async function addNote(event) {
    event.preventDefault();
    try {
      await research.addItem(projectId, {
        kind: "note",
        title: note.title,
        text: note.text,
        tags: note.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setNote({ title: "", text: "", tags: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const tags = [...new Set((items || []).flatMap((i) => i.tags))].sort();

  return (
    <>
      {canEdit && (
        <form onSubmit={addNote} className="mb-6 space-y-2 rounded-xl border border-stone-200 p-4 dark:border-stone-800">
          <input className={inputClass} placeholder="Título da nota (opcional)" value={note.title} onChange={(e) => setNote({ ...note, title: e.target.value })} />
          <textarea className={inputClass} rows={3} placeholder="Escreve uma nota…" value={note.text} onChange={(e) => setNote({ ...note, text: e.target.value })} required />
          <div className="flex gap-2">
            <input className={inputClass} placeholder="Etiquetas, separadas por vírgulas" value={note.tags} onChange={(e) => setNote({ ...note, tags: e.target.value })} />
            <Button type="submit" variant="primary" icon={Plus}>
              Nota
            </Button>
          </div>
        </form>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <label className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
          <input
            type="search"
            className={`${inputClass} pl-8`}
            placeholder="Procurar nas notas e destaques"
            value={filters.q}
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
          />
        </label>
        <select className={`${inputClass} w-auto`} value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })} aria-label="Tipo de entrada">
          <option value="">Tudo</option>
          {Object.entries(KINDS).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}s
            </option>
          ))}
        </select>
        {tags.length > 0 && (
          <select className={`${inputClass} w-auto`} value={filters.tag} onChange={(e) => setFilters({ ...filters, tag: e.target.value })} aria-label="Etiqueta">
            <option value="">Todas as etiquetas</option>
            {tags.map((tag) => (
              <option key={tag} value={tag}>
                #{tag}
              </option>
            ))}
          </select>
        )}
      </div>

      <ErrorText>{error}</ErrorText>
      {!items && !error && <Spinner label="A carregar o caderno…" />}
      {items && items.length === 0 && (
        <Empty>
          {filters.q || filters.kind || filters.tag
            ? "Nada corresponde aos filtros."
            : "O caderno está vazio. Guarda aqui respostas do chat, excertos da pesquisa e as tuas notas."}
        </Empty>
      )}
      {items && items.length > 0 && (
        <ul className="space-y-3">
          {items.map((item) => (
            <Item key={item.item_id} item={item} projectId={projectId} canEdit={canEdit} currentUserId={currentUserId} isOwner={isOwner} onChanged={load} />
          ))}
        </ul>
      )}
    </>
  );
}
