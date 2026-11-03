import { useEffect, useState } from "react";
import { Save, Send, Trash2, UserPlus, X } from "lucide-react";
import { research } from "../../api";
import { Button, Empty, ErrorText, Section, documentLabel, inputClass } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";

const ROLE_LABELS = { owner: "Dono", editor: "Edita", viewer: "Lê e comenta" };

export function Comments({ projectId, itemId = null, currentUserId, isOwner }) {
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  const load = () => research.comments(projectId).then((all) => setComments(all.filter((c) => (c.item_id || null) === itemId)));
  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [projectId, itemId]);

  async function send(event) {
    event.preventDefault();
    try {
      await research.addComment(projectId, { text: text.trim(), item_id: itemId });
      setText("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="space-y-2">
      {comments.map((c) => (
        <div key={c.comment_id} className="group flex gap-2 text-sm">
          <p className="min-w-0 flex-1">
            <span className="font-medium">{c.author}</span>{" "}
            <span className="text-xs text-stone-500">{new Date(c.created_at).toLocaleString("pt-PT")}</span>
            <span className="block whitespace-pre-line text-stone-700 dark:text-stone-300">{c.text}</span>
          </p>
          {(c.author_id === currentUserId || isOwner) && (
            <button
              type="button"
              aria-label="Apagar comentário"
              onClick={() => research.deleteComment(projectId, c.comment_id).then(load, (err) => setError(err.message))}
              className="self-start rounded p-1 text-stone-400 opacity-0 hover:text-red-600 group-hover:opacity-100"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ))}
      <form onSubmit={send} className="flex gap-2">
        <input className={inputClass} placeholder="Escreve um comentário" value={text} onChange={(e) => setText(e.target.value)} required />
        <Button type="submit" icon={Send} aria-label="Enviar comentário" />
      </form>
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

export default function Overview({ detail, canEdit, currentUserId, onChange, onDeleted }) {
  const { openReader } = useResearch();
  const { project } = detail;
  const [draft, setDraft] = useState({ title: project.title, question: project.question, description: project.description, work_type: project.work_type });
  const [workTypes, setWorkTypes] = useState([]);
  const [member, setMember] = useState({ username: "", role: "viewer" });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const isOwner = detail.my_role === "owner";

  useEffect(() => {
    research.workTypes().then(setWorkTypes).catch(() => {});
  }, []);

  const dirty = ["title", "question", "description", "work_type"].some((key) => draft[key] !== project[key]);

  async function act(action) {
    setError("");
    try {
      const next = await action();
      if (next) onChange(next);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <Section title="Pergunta de investigação" description="Orienta o chat do projeto, o esqueleto e o estado da arte.">
        <div className="space-y-2">
          <input className={inputClass} value={draft.title} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, title: e.target.value })} aria-label="Título" />
          <textarea
            className={inputClass}
            rows={2}
            placeholder="Qual é a pergunta a que o teu trabalho quer responder?"
            value={draft.question}
            disabled={!canEdit}
            onChange={(e) => setDraft({ ...draft, question: e.target.value })}
          />
          <textarea
            className={inputClass}
            rows={2}
            placeholder="Notas sobre o projeto (âmbito, prazos, orientação…)"
            value={draft.description}
            disabled={!canEdit}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />
          <div className="flex flex-wrap items-center gap-2">
            <select className={`${inputClass} sm:max-w-64`} value={draft.work_type} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, work_type: e.target.value })} aria-label="Tipo de trabalho">
              <option value="">Tipo de trabalho a escrever…</option>
              {workTypes.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
            {canEdit && (
              <Button
                variant="primary"
                icon={Save}
                busy={saving}
                disabled={!dirty || !draft.title.trim()}
                onClick={async () => {
                  setSaving(true);
                  await act(() => research.updateProject(project.project_id, draft));
                  setSaving(false);
                }}
              >
                Guardar
              </Button>
            )}
          </div>
        </div>
      </Section>

      <Section
        title={`Documentos (${detail.documents.length})`}
        description="Fixa documentos a partir da Pesquisa, do Descobrir ou do leitor. O chat do projeto pesquisa só nestes."
      >
        {detail.documents.length === 0 ? (
          <Empty>Ainda sem documentos fixados.</Empty>
        ) : (
          <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
            {detail.documents.map((doc) => (
              <li key={doc.document_id} className="flex items-center gap-2 px-3 py-2 text-sm">
                <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => openReader({ document_id: doc.document_id, page: 1 })}>
                  {documentLabel(doc)}
                  <span className="text-stone-500">
                    {doc.year ? ` · ${doc.year}` : ""}
                    {doc.authors.length ? ` · ${doc.authors.join(", ")}` : ""}
                  </span>
                </button>
                {canEdit && (
                  <Button
                    variant="ghost"
                    icon={X}
                    aria-label="Retirar do projeto"
                    onClick={() => act(() => research.unpin(project.project_id, doc.document_id))}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Pessoas" description={isOwner ? "Partilha o projeto, por exemplo com quem te orienta." : undefined}>
        <ul className="mb-3 space-y-1 text-sm">
          {detail.members.map((m) => (
            <li key={m.user_id} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate">
                {m.display_name || m.username} <span className="text-stone-500">({m.username})</span>
              </span>
              <span className="text-xs text-stone-500">{ROLE_LABELS[m.role]}</span>
              {m.role !== "owner" && (isOwner || m.user_id === currentUserId) && (
                <Button
                  variant="ghost"
                  icon={X}
                  aria-label={m.user_id === currentUserId ? "Sair do projeto" : "Remover"}
                  onClick={() =>
                    act(async () => {
                      const next = await research.removeMember(project.project_id, m.user_id);
                      if (!next) onDeleted();
                      return next;
                    })
                  }
                />
              )}
            </li>
          ))}
        </ul>
        {isOwner && (
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                const next = await research.addMember(project.project_id, { username: member.username.trim(), role: member.role });
                setMember({ username: "", role: member.role });
                return next;
              });
            }}
          >
            <input className={`${inputClass} flex-1`} placeholder="Utilizador" value={member.username} onChange={(e) => setMember({ ...member, username: e.target.value })} required />
            <select className={`${inputClass} w-auto`} value={member.role} onChange={(e) => setMember({ ...member, role: e.target.value })} aria-label="Papel">
              <option value="viewer">Lê e comenta</option>
              <option value="editor">Edita</option>
            </select>
            <Button type="submit" icon={UserPlus}>
              Partilhar
            </Button>
          </form>
        )}
      </Section>

      <Section title="Comentários">
        <Comments projectId={project.project_id} currentUserId={currentUserId} isOwner={isOwner} />
      </Section>

      <ErrorText>{error}</ErrorText>
      {isOwner && (
        <div className="mt-10 border-t border-stone-200 pt-4 dark:border-stone-800">
          <Button
            variant="danger"
            icon={Trash2}
            onClick={() => (confirmDelete ? research.deleteProject(project.project_id).then(onDeleted, (err) => setError(err.message)) : setConfirmDelete(true))}
          >
            {confirmDelete ? "Confirmar: apagar o projeto e o caderno" : "Apagar projeto"}
          </Button>
        </div>
      )}
    </>
  );
}
