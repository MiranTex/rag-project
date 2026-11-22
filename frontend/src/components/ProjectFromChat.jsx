import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, FolderPlus, Plus, Sparkles, Trash2, UserPlus, X } from "lucide-react";
import { research } from "../api";
import { useResearch } from "../research/ResearchContext";
import { Button, ErrorText, Modal, ROLE_LABELS, Spinner, inputClass, uniqueKey, controlBase } from "./ui";

// Criar um projeto a partir da conversa do chat: o LLM propõe a estrutura (secções, estados, entradas) e a pessoa
// revê tudo antes de criar. Nada aqui assume um assunto: as secções são as que vierem na proposta ou forem escritas.

const ROLES = { editor: ROLE_LABELS.editor, viewer: ROLE_LABELS.viewer };

// Só as respostas completas entram (sem erros, respostas interrompidas ou bloqueadas).
export function conversationTurns(messages) {
  return messages
    .filter((msg) => msg.answer && !msg.stopped && !msg.blocked && !msg.answer.startsWith("Erro:"))
    .map((msg) => ({
      question: msg.question || "",
      answer: msg.answer,
      sources: (msg.sources || [])
        .filter((s) => s.document_id || s.filename)
        .map((s) => ({ document_id: s.document_id || "", filename: s.filename || "", page: Number.isInteger(s.page) ? s.page : null })),
    }));
}

function GoalStep({ turnCount, goal, onGoalChange, onPropose, busy, error }) {
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onPropose();
      }}
    >
      <p className="text-sm text-stone-600 dark:text-stone-400">
        A partir {turnCount === 1 ? "da resposta" : `das ${turnCount} respostas`} desta conversa, é proposta uma estrutura de projeto com
        secções e entradas. Revês tudo antes de criar.
      </p>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">O que queres construir? (opcional)</span>
        <textarea
          className={inputClass}
          rows={3}
          placeholder="Ex.: a documentação de um software, um parecer, um plano de formação…"
          value={goal}
          onChange={(e) => onGoalChange(e.target.value)}
        />
      </label>
      <ErrorText>{error}</ErrorText>
      {busy ? (
        <Spinner label="A analisar a conversa…" />
      ) : (
        <Button type="submit" variant="primary" icon={Sparkles}>
          Propor estrutura
        </Button>
      )}
    </form>
  );
}

function ItemEditor({ item, sections, statuses, documentNames, onChange, onRemove }) {
  return (
    <li className={`rounded-lg border p-3 ${item.include ? "border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900" : "border-dashed border-stone-300 opacity-60 dark:border-stone-700"}`}>
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-2"
          checked={item.include}
          onChange={(e) => onChange({ include: e.target.checked })}
          aria-label="Incluir esta entrada"
        />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex gap-2">
            <input className={`${controlBase} w-24 shrink-0`} placeholder="Ref." value={item.ref} onChange={(e) => onChange({ ref: e.target.value })} aria-label="Referência" />
            <input className={inputClass} placeholder="Título" value={item.title} onChange={(e) => onChange({ title: e.target.value })} aria-label="Título" />
          </div>
          <textarea className={inputClass} rows={3} value={item.text} onChange={(e) => onChange({ text: e.target.value })} aria-label="Texto" />
          <div className="flex flex-wrap items-center gap-2 text-xs text-stone-500">
            <select className={`${controlBase} w-auto py-1 text-xs`} value={item.section} onChange={(e) => onChange({ section: e.target.value })} aria-label="Secção">
              <option value="">Sem secção</option>
              {sections.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.title}
                </option>
              ))}
            </select>
            {statuses.length > 0 && (
              <select className={`${controlBase} w-auto py-1 text-xs`} value={item.status} onChange={(e) => onChange({ status: e.target.value })} aria-label="Estado">
                <option value="">Sem estado</option>
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            )}
            {item.sources.map((s) => (
              <span key={`${s.document_id}-${s.page}`} className="rounded-full border border-stone-200 px-2 py-0.5 dark:border-stone-700">
                {(documentNames[s.document_id] || s.filename || "").replace(/\.pdf$/i, "")} p.{s.page}
              </span>
            ))}
            <button type="button" onClick={onRemove} className="ml-auto rounded p-1 hover:text-red-600" aria-label="Apagar entrada">
              <Trash2 className="size-3.5" />
            </button>
          </div>
        </div>
      </div>
    </li>
  );
}

function ReviewStep({ draft, setDraft, documentNames, onBack, onCreate, busy, error }) {
  const [newSection, setNewSection] = useState("");
  const [member, setMember] = useState({ username: "", role: "editor" });
  const { sections, statuses } = draft.structure;
  const statusText = statuses.join(", ");

  const setStructure = (structure) => setDraft({ ...draft, structure: { ...draft.structure, ...structure } });
  const setItem = (index, changes) => setDraft({ ...draft, items: draft.items.map((it, i) => (i === index ? { ...it, ...changes } : it)) });

  function removeSection(key) {
    const rest = sections.filter((s) => s.key !== key);
    // As entradas da secção apagada passam para a primeira que sobrar (ou ficam sem secção).
    const fallback = rest[0]?.key || "";
    setDraft({
      ...draft,
      structure: { ...draft.structure, sections: rest },
      items: draft.items.map((it) => (it.section === key ? { ...it, section: fallback } : it)),
    });
  }

  function addSection(event) {
    event.preventDefault();
    const title = newSection.trim();
    if (!title) return;
    setStructure({ sections: [...sections, { key: uniqueKey(title, sections), title, description: "" }] });
    setNewSection("");
  }

  function addItem(sectionKey) {
    setDraft({ ...draft, items: [...draft.items, { section: sectionKey, ref: "", title: "", text: "", status: statuses[0] || "", fields: {}, sources: [], include: true }] });
  }

  const included = draft.items.filter((it) => it.include && (it.title.trim() || it.text.trim())).length;
  const grouped = [...sections, { key: "", title: "Sem secção" }].map((section) => ({
    section,
    entries: draft.items.map((item, index) => ({ item, index })).filter(({ item }) => item.section === section.key),
  }));

  return (
    <div className="space-y-6">
      {!draft.generated && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          O modelo não conseguiu propor uma estrutura. Fica a conversa numa secção; podes acrescentar secções e entradas à mão.
        </p>
      )}

      <div className="space-y-2">
        <input className={inputClass} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} aria-label="Título do projeto" placeholder="Título" />
        <textarea className={inputClass} rows={2} value={draft.question} onChange={(e) => setDraft({ ...draft, question: e.target.value })} placeholder="Objetivo do projeto" aria-label="Objetivo" />
        <textarea className={inputClass} rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="Descrição" aria-label="Descrição" />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Secções</h3>
        <ul className="mb-2 space-y-1">
          {sections.map((s) => (
            <li key={s.key} className="flex items-center gap-2">
              <input
                className={inputClass}
                value={s.title}
                onChange={(e) => setStructure({ sections: sections.map((x) => (x.key === s.key ? { ...x, title: e.target.value } : x)) })}
                aria-label="Título da secção"
              />
              <Button variant="ghost" icon={X} aria-label={`Apagar a secção ${s.title}`} onClick={() => removeSection(s.key)} />
            </li>
          ))}
        </ul>
        <form onSubmit={addSection} className="flex gap-2">
          <input className={inputClass} placeholder="Nova secção" value={newSection} onChange={(e) => setNewSection(e.target.value)} />
          <Button type="submit" icon={Plus}>
            Secção
          </Button>
        </form>
        <label className="mt-3 block text-sm">
          <span className="mb-1 block font-medium">Estados das entradas</span>
          <input
            className={inputClass}
            placeholder="Ex.: proposto, aprovado (vazio: sem estados)"
            defaultValue={statusText}
            onBlur={(e) => {
              const next = [...new Set(e.target.value.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean))];
              setDraft({
                ...draft,
                structure: { ...draft.structure, statuses: next },
                items: draft.items.map((it) => (next.includes(it.status) ? it : { ...it, status: next[0] || "" })),
              });
            }}
          />
        </label>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Entradas ({included} incluídas)</h3>
        <div className="space-y-4">
          {grouped
            .filter(({ section, entries }) => section.key || entries.length)
            .map(({ section, entries }) => (
              <div key={section.key || "_none"}>
                <div className="mb-1.5 flex items-center gap-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">{section.title}</h4>
                  {section.key && (
                    <button type="button" onClick={() => addItem(section.key)} className="text-xs text-accent-700 hover:underline dark:text-accent-400">
                      + entrada
                    </button>
                  )}
                </div>
                <ul className="space-y-2">
                  {entries.map(({ item, index }) => (
                    <ItemEditor
                      key={index}
                      item={item}
                      sections={sections}
                      statuses={statuses}
                      documentNames={documentNames}
                      onChange={(changes) => setItem(index, changes)}
                      onRemove={() => setDraft({ ...draft, items: draft.items.filter((_, i) => i !== index) })}
                    />
                  ))}
                </ul>
              </div>
            ))}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Documentos a fixar</h3>
        {Object.keys(documentNames).length === 0 ? (
          <p className="text-sm text-stone-500">A conversa não usou documentos indexados.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {Object.entries(documentNames).map(([id, name]) => (
              <li key={id}>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.document_ids.includes(id)}
                    onChange={(e) =>
                      setDraft({ ...draft, document_ids: e.target.checked ? [...draft.document_ids, id] : draft.document_ids.filter((d) => d !== id) })
                    }
                  />
                  <span className="truncate">{name.replace(/\.pdf$/i, "")}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.keepConversation} onChange={(e) => setDraft({ ...draft, keepConversation: e.target.checked })} />
          Guardar também a conversa no caderno
        </label>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Convidar pessoas</h3>
        {draft.members.length > 0 && (
          <ul className="mb-2 space-y-1 text-sm">
            {draft.members.map((m) => (
              <li key={m.username} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate">{m.username}</span>
                <span className="text-xs text-stone-500">{ROLES[m.role]}</span>
                <Button variant="ghost" icon={X} aria-label="Retirar" onClick={() => setDraft({ ...draft, members: draft.members.filter((x) => x.username !== m.username) })} />
              </li>
            ))}
          </ul>
        )}
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const username = member.username.trim();
            if (!username || draft.members.some((m) => m.username === username)) return;
            setDraft({ ...draft, members: [...draft.members, { username, role: member.role }] });
            setMember({ ...member, username: "" });
          }}
        >
          <input className={`${controlBase} min-w-40 flex-1`} placeholder="Nome de utilizador" value={member.username} onChange={(e) => setMember({ ...member, username: e.target.value })} />
          <select className={`${controlBase} w-auto`} value={member.role} onChange={(e) => setMember({ ...member, role: e.target.value })} aria-label="Papel">
            {Object.entries(ROLES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <Button type="submit" icon={UserPlus} aria-label="Adicionar pessoa" />
        </form>
      </div>

      <ErrorText>{error}</ErrorText>
      <div className="flex flex-wrap gap-2 border-t border-stone-200 pt-4 dark:border-stone-800">
        <Button variant="ghost" icon={ArrowLeft} onClick={onBack} disabled={busy}>
          Propor de novo
        </Button>
        <Button variant="primary" icon={FolderPlus} className="ml-auto" busy={busy} disabled={!draft.title.trim()} onClick={onCreate}>
          Criar projeto
        </Button>
      </div>
    </div>
  );
}

export default function ProjectFromChat({ messages, onClose }) {
  const navigate = useNavigate();
  const { notify, refreshProjects } = useResearch();
  const turns = useMemo(() => conversationTurns(messages), [messages]);
  const [goal, setGoal] = useState("");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Nomes dos documentos citados na conversa, só para os que o servidor confirmou estarem indexados.
  const documentNames = useMemo(() => {
    const names = {};
    for (const turn of turns) for (const s of turn.sources) if (s.document_id && draft?.allDocumentIds.includes(s.document_id)) names[s.document_id] = s.filename || s.document_id;
    return names;
  }, [turns, draft?.allDocumentIds]);

  async function propose() {
    setBusy(true);
    setError("");
    try {
      const result = await research.draftFromConversation({ turns, goal });
      setDraft({
        ...result,
        items: result.items.map((item) => ({ ...item, include: true })),
        allDocumentIds: result.document_ids,
        keepConversation: true,
        members: [],
      });
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  async function create() {
    setBusy(true);
    setError("");
    try {
      const { detail, warnings } = await research.createFromDraft({
        title: draft.title.trim(),
        question: draft.question,
        description: draft.description,
        structure: draft.structure,
        items: draft.items.filter((it) => it.include && (it.title.trim() || it.text.trim())).map(({ include, ...item }) => item),
        document_ids: draft.document_ids,
        conversation: draft.keepConversation ? turns : [],
        members: draft.members,
      });
      refreshProjects();
      notify(warnings.length ? `Projeto criado. ${warnings.join(" ")}` : "Projeto criado.");
      onClose();
      navigate(`/projetos/${detail.project.project_id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Criar projeto a partir da conversa" onClose={busy ? () => {} : onClose} wide>
      {turns.length === 0 ? (
        <p className="text-sm text-stone-500">Ainda não há respostas completas nesta conversa.</p>
      ) : draft ? (
        <ReviewStep draft={draft} setDraft={setDraft} documentNames={documentNames} onBack={() => setDraft(null)} onCreate={create} busy={busy} error={error} />
      ) : (
        <GoalStep turnCount={turns.length} goal={goal} onGoalChange={setGoal} onPropose={propose} busy={busy} error={error} />
      )}
    </Modal>
  );
}
