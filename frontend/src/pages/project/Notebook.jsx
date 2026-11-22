import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BookOpen,
  MessageCircle,
  MessageSquareQuote,
  MessagesSquare,
  NotebookPen,
  Pencil,
  Plus,
  Quote,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { research } from "../../api";
import Markdown from "../../components/Markdown";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  Menu,
  Modal,
  Spinner,
  documentLabel,
  inputClass,
  statusTone,
  useConfirm,
  controlBase,
} from "../../components/ui";
import { BASIS } from "../../research/basis";
import { useResearch } from "../../research/ResearchContext";
import Comments from "./Comments";

const KINDS = {
  note: { label: "Nota", plural: "Notas", icon: NotebookPen },
  excerpt: { label: "Destaque", plural: "Destaques", icon: Quote },
  answer: { label: "Resposta", plural: "Respostas do chat", icon: MessageSquareQuote },
  draft: { label: "Rascunho", plural: "Rascunhos", icon: Sparkles },
};

const NO_SECTION = "__none__";

// Ordem natural das referências (R-2 antes de R-10).
const byRef = (a, b) => (a.ref || "").localeCompare(b.ref || "", "pt", { numeric: true }) || a.created_at.localeCompare(b.created_at);
const splitTags = (text) => text.split(",").map((t) => t.trim()).filter(Boolean);

// Criar ou editar uma entrada. Fica numa janela, para a lista não ser empurrada por um formulário.
function EntryDialog({ projectId, structure, item, defaultSection, onClose, onSaved }) {
  const editing = !!item;
  const [draft, setDraft] = useState({
    title: item?.title || "",
    text: item?.text || "",
    ref: item?.ref || "",
    section: item?.section ?? defaultSection ?? "",
    status: item?.status ?? "",
    tags: (item?.tags || []).join(", "),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { sections, statuses } = structure;

  async function save(event) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    const body = {
      title: draft.title,
      text: draft.text,
      ref: draft.ref,
      section: draft.section,
      status: draft.status || (!editing && draft.section && statuses.length ? statuses[0] : draft.status),
      tags: splitTags(draft.tags),
    };
    try {
      if (editing) await research.updateItem(projectId, item.item_id, body);
      else await research.addItem(projectId, { kind: "note", ...body });
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal
      title={editing ? `Editar ${item.ref || "entrada"}` : "Nova entrada"}
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" busy={busy} disabled={!draft.title.trim() && !draft.text.trim()} onClick={save}>
            {editing ? "Guardar" : "Criar entrada"}
          </Button>
        </>
      }
    >
      <form onSubmit={save} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
          <Field label="Referência">
            <input className={`${inputClass} font-mono`} placeholder="RF-001" value={draft.ref} onChange={(e) => setDraft({ ...draft, ref: e.target.value })} />
          </Field>
          <Field label="Título">
            <input className={inputClass} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </Field>
        </div>
        <Field label="Texto" hint="Aceita markdown simples (listas, negrito, ligações).">
          <textarea className={inputClass} rows={8} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          {sections.length > 0 && (
            <Field label="Secção">
              <select className={inputClass} value={draft.section} onChange={(e) => setDraft({ ...draft, section: e.target.value })}>
                <option value="">Sem secção</option>
                {sections.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.title}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {statuses.length > 0 && (
            <Field label="Estado">
              <select className={inputClass} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                <option value="">{editing ? "Sem estado" : `Automático (${statuses[0]})`}</option>
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        <Field label="Etiquetas" hint="Separadas por vírgulas.">
          <input className={inputClass} value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} />
        </Field>
        <ErrorText>{error}</ErrorText>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

function StatusControl({ item, statuses, canEdit, onChange }) {
  if (!statuses.length) return null;
  const badge = (
    <Badge tone={statusTone(item.status, statuses)} className={canEdit ? "cursor-pointer hover:ring-1 hover:ring-stone-300 dark:hover:ring-stone-600" : ""}>
      {item.status || "sem estado"}
    </Badge>
  );
  if (!canEdit) return badge;
  return (
    <Menu
      align="left"
      items={[...statuses, ""].map((status) => ({ label: status || "sem estado", onSelect: () => onChange(status) }))}
      trigger={({ toggle, open }) => (
        <button type="button" onClick={toggle} aria-haspopup="menu" aria-expanded={open} aria-label={`Estado: ${item.status || "sem estado"}. Mudar`}>
          {badge}
        </button>
      )}
    />
  );
}

function Item({ item, projectId, structure, canEdit, currentUserId, isOwner, onEdit, onChanged }) {
  const { openReader, chatInProject } = useResearch();
  const confirm = useConfirm();
  const [showComments, setShowComments] = useState(false);
  const [commentCount, setCommentCount] = useState(item.comment_count);
  const [error, setError] = useState("");
  const kind = KINDS[item.kind] || KINDS.note;
  const KindIcon = kind.icon;
  const source = item.source || {};
  // Etiqueta só no que não vem (só) dos documentos: é o que quem lê o caderno tem de verificar.
  const basis = source.basis && source.basis !== "documents" ? BASIS[source.basis] : null;
  const when = new Date(item.updated_at || item.created_at).toLocaleDateString("pt-PT");

  async function remove() {
    const ok = await confirm({ title: "Apagar entrada?", message: `"${item.ref ? `${item.ref} ` : ""}${item.title || item.text.slice(0, 80)}" e os seus comentários.` });
    if (ok) research.deleteItem(projectId, item.item_id).then(onChanged, (err) => setError(err.message));
  }

  const chip =
    "inline-flex items-center gap-1 rounded-full border border-stone-200 px-2 py-0.5 text-xs hover:border-stone-400 dark:border-stone-700 dark:hover:border-stone-500";

  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-3">
        {/* A referência fica numa coluna própria, para a lista se ler como um índice. */}
        <span className="hidden w-16 shrink-0 pt-0.5 font-mono text-xs font-medium text-stone-500 sm:block dark:text-stone-400">{item.ref}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {item.ref && <span className="font-mono text-xs font-medium text-stone-500 sm:hidden dark:text-stone-400">{item.ref}</span>}
            {item.kind !== "note" && (
              <span className="inline-flex items-center gap-1 text-xs text-stone-500 dark:text-stone-400" title={kind.label}>
                <KindIcon className="size-3.5" />
              </span>
            )}
            {item.title && <h3 className="min-w-0 text-sm font-medium">{item.title}</h3>}
            {basis && (
              <Badge tone={basis.tone} title={basis.title}>
                {basis.label}
              </Badge>
            )}
            <StatusControl
              item={item}
              statuses={structure.statuses}
              canEdit={canEdit}
              onChange={(status) => research.updateItem(projectId, item.item_id, { status }).then(onChanged, (err) => setError(err.message))}
            />
          </div>
          {source.question && item.kind === "answer" && <p className="mt-1 text-sm italic text-stone-500 dark:text-stone-400">Pergunta: {source.question}</p>}
          {item.text && (
            <div
              className={`mt-1 text-sm text-stone-700 dark:text-stone-300 ${item.kind === "excerpt" ? "border-l-2 border-accent-400 pl-3" : ""} [&_.prose]:text-sm`}
            >
              {item.kind === "excerpt" ? <p className="whitespace-pre-line">{item.text}</p> : <Markdown size="sm">{item.text}</Markdown>}
            </div>
          )}
          {(source.document_id || source.sources?.length > 0 || item.tags.length > 0) && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {source.document_id && (
                <button
                  type="button"
                  onClick={() => openReader({ document_id: source.document_id, page: source.page || 1, text: item.kind === "excerpt" ? item.text : "" })}
                  className={`${chip} text-accent-700 dark:text-accent-400`}
                >
                  <BookOpen className="size-3" />
                  {source.title || documentLabel(source)}
                  {source.page ? `, p. ${source.page}` : ""}
                </button>
              )}
              {(source.sources || []).map((s) => (
                <button key={`${s.document_id}-${s.page}`} type="button" onClick={() => openReader(s)} className={`${chip} text-stone-600 dark:text-stone-400`}>
                  <BookOpen className="size-3" />
                  {documentLabel(s)} p.{s.page}
                </button>
              ))}
              {item.tags.map((tag) => (
                <Badge key={tag}>#{tag}</Badge>
              ))}
            </div>
          )}
          <ErrorText>{error}</ErrorText>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={() => setShowComments(!showComments)}
            aria-expanded={showComments}
            title={`${item.author} · ${when}`}
            aria-label={commentCount ? `${commentCount} comentários` : "Comentar"}
            className={`inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs hover:bg-stone-100 dark:hover:bg-stone-800 ${
              commentCount || showComments ? "text-stone-700 dark:text-stone-300" : "text-stone-400 dark:text-stone-500"
            }`}
          >
            <MessageCircle className="size-4" />
            {commentCount > 0 && commentCount}
          </button>
          <Menu
            items={[
              { label: "Discutir no chat", icon: MessagesSquare, onSelect: () => chatInProject(projectId, `Sobre ${item.ref || `"${item.title || item.text.slice(0, 60)}"`}: `) },
              { label: "Editar", icon: Pencil, onSelect: onEdit, hidden: !canEdit },
              { label: "Apagar", icon: Trash2, onSelect: remove, danger: true, hidden: !canEdit },
            ]}
          />
        </div>
      </div>
      {showComments && (
        <div className="mt-3 rounded-lg bg-stone-50 p-3 sm:ml-[4.75rem] dark:bg-stone-800/40">
          <p className="mb-2 text-xs text-stone-500 dark:text-stone-400">
            {kind.label} de {item.author}, {when}
          </p>
          <Comments projectId={projectId} itemId={item.item_id} currentUserId={currentUserId} isOwner={isOwner} onCountChange={setCommentCount} />
        </div>
      )}
    </li>
  );
}

export default function Notebook({ projectId, structure = { sections: [], statuses: [] }, canEdit, currentUserId, isOwner }) {
  const { chatInProject } = useResearch();
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState(null);
  const [filters, setFilters] = useState({ q: "", kind: "", tag: "", status: "" });
  const [dialog, setDialog] = useState(null);
  const [error, setError] = useState("");
  const section = params.get("seccao") || "";
  const setSection = (value) => setParams(value ? { seccao: value } : {}, { replace: true });
  const sectionKeys = new Set(structure.sections.map((s) => s.key));

  const load = () => research.items(projectId, { q: filters.q, kind: filters.kind, tag: filters.tag }).then(setItems, (err) => setError(err.message));
  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [projectId, filters.q, filters.kind, filters.tag]);

  const tags = [...new Set((items || []).flatMap((i) => i.tags))].sort();
  const inSection = (item, key) => (key === NO_SECTION ? !sectionKeys.has(item.section) : item.section === key);
  const visible = (items || []).filter((item) => (!section || inSection(item, section)) && (!filters.status || item.status === filters.status));
  // Com secções: um grupo por secção (pela referência), e no fim as entradas soltas (mais recentes primeiro).
  const groups =
    structure.sections.length === 0
      ? [{ key: "", title: "", entries: visible }]
      : [...structure.sections, { key: NO_SECTION, title: "Outras entradas" }]
          .map((s) => ({ ...s, entries: visible.filter((item) => inSection(item, s.key)) }))
          .map((g) => (g.key === NO_SECTION ? g : { ...g, entries: [...g.entries].sort(byRef) }))
          .filter((g) => g.entries.length);
  const filtering = filters.q || filters.kind || filters.tag || filters.status || section;
  const selectClass = `${controlBase} w-auto max-w-52 shrink-0`;

  return (
    <>
      <div className="mb-5 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
            <input
              type="search"
              className={`${inputClass} pl-8`}
              placeholder="Procurar no caderno"
              aria-label="Procurar no caderno"
              value={filters.q}
              onChange={(e) => setFilters({ ...filters, q: e.target.value })}
            />
          </label>
          <Button icon={MessagesSquare} onClick={() => chatInProject(projectId)} title="O assistente conhece o caderno e propõe alterações">
            Assistente
          </Button>
          {canEdit && (
            <Button variant="primary" icon={Plus} onClick={() => setDialog({ item: null })}>
              Nova entrada
            </Button>
          )}
        </div>
        {/* No telemóvel os filtros ficam numa linha que desliza, em vez de um por linha. */}
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0">
          {structure.sections.length > 0 && (
            <select className={selectClass} value={section} onChange={(e) => setSection(e.target.value)} aria-label="Secção">
              <option value="">Todas as secções</option>
              {structure.sections.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.title}
                </option>
              ))}
              <option value={NO_SECTION}>Outras entradas</option>
            </select>
          )}
          {structure.statuses.length > 0 && (
            <select className={selectClass} value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} aria-label="Estado">
              <option value="">Todos os estados</option>
              {structure.statuses.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          )}
          <select className={selectClass} value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })} aria-label="Tipo de entrada">
            <option value="">Todos os tipos</option>
            {Object.entries(KINDS).map(([value, { plural }]) => (
              <option key={value} value={value}>
                {plural}
              </option>
            ))}
          </select>
          {tags.length > 0 && (
            <select className={selectClass} value={filters.tag} onChange={(e) => setFilters({ ...filters, tag: e.target.value })} aria-label="Etiqueta">
              <option value="">Todas as etiquetas</option>
              {tags.map((tag) => (
                <option key={tag} value={tag}>
                  #{tag}
                </option>
              ))}
            </select>
          )}
          {filtering && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setFilters({ q: "", kind: "", tag: "", status: "" });
                setSection("");
              }}
            >
              Limpar filtros
            </Button>
          )}
        </div>
      </div>

      <ErrorText>{error}</ErrorText>
      {!items && !error && <Spinner label="A carregar o caderno…" />}
      {items && visible.length === 0 && (
        <EmptyState
          icon={NotebookPen}
          title={filtering ? "Nada corresponde aos filtros" : "O caderno está vazio"}
          action={
            !filtering &&
            canEdit && (
              <Button variant="primary" icon={Plus} onClick={() => setDialog({ item: null })}>
                Nova entrada
              </Button>
            )
          }
        >
          {!filtering && "Guarda aqui respostas do chat, destaques dos documentos e as tuas notas, ou pede ao assistente para propor entradas."}
        </EmptyState>
      )}
      {visible.length > 0 &&
        groups.map((group) => (
          <section key={group.key || "_all"} className="mb-6">
            {group.title && (
              <div className="mb-2 flex items-center gap-2">
                <h2 className="text-sm font-semibold">{group.title}</h2>
                <span className="text-xs tabular-nums text-stone-500 dark:text-stone-400">{group.entries.length}</span>
                {canEdit && group.key !== NO_SECTION && (
                  <Button variant="ghost" size="sm" icon={Plus} className="ml-auto" onClick={() => setDialog({ item: null, section: group.key })}>
                    Entrada
                  </Button>
                )}
              </div>
            )}
            <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
              {group.entries.map((item) => (
                <Item
                  key={`${item.item_id}-${item.updated_at}`}
                  item={item}
                  projectId={projectId}
                  structure={structure}
                  canEdit={canEdit}
                  currentUserId={currentUserId}
                  isOwner={isOwner}
                  onEdit={() => setDialog({ item })}
                  onChanged={load}
                />
              ))}
            </ul>
          </section>
        ))}

      {dialog && (
        <EntryDialog
          projectId={projectId}
          structure={structure}
          item={dialog.item}
          defaultSection={dialog.section ?? (section && section !== NO_SECTION ? section : "")}
          onClose={() => setDialog(null)}
          onSaved={load}
        />
      )}
    </>
  );
}
