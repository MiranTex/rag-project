import { useEffect, useState } from "react";
import { MessageSquare, Trash2 } from "lucide-react";
import { research } from "../../api";
import { Badge, Button, EmptyState, ErrorText, IconButton, Spinner, useConfirm } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";

// Conversas do chat guardadas no projeto (de todos os membros). Abrir uma leva ao chat para a continuar.
export default function Conversations({ projectId, currentUserId, isOwner, canChat }) {
  const { openConversation, chatInProject } = useResearch();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const confirm = useConfirm();

  const load = () => research.conversations(projectId).then(setItems, (err) => setError(err.message));
  useEffect(() => {
    load();
  }, [projectId]);

  async function remove(conversation) {
    if (!(await confirm({ title: "Apagar conversa?", message: `"${conversation.title}" deixa de estar no projeto para todos os membros.` }))) return;
    try {
      await research.deleteConversation(projectId, conversation.conversation_id);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-sm text-stone-500 dark:text-stone-400">
          As perguntas feitas no chat dentro deste projeto ficam aqui, para toda a equipa as ver e continuar.
        </p>
        {canChat && (
          <Button variant="primary" icon={MessageSquare} onClick={() => chatInProject(projectId)}>
            Nova conversa
          </Button>
        )}
      </div>
      <ErrorText>{error}</ErrorText>
      {!items && !error && <Spinner label="A carregar as conversas…" />}
      {items && items.length === 0 && (
        <EmptyState icon={MessageSquare} title="Ainda não há conversas">
          O que perguntares ao assistente dentro deste projeto fica guardado aqui.
        </EmptyState>
      )}
      {items && items.length > 0 && (
        <ul className="divide-y divide-stone-200 overflow-hidden rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
          {items.map((c) => (
            <li key={c.conversation_id} className="flex items-center gap-3 px-4 py-3">
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => openConversation(projectId, c.conversation_id).catch((err) => setError(err.message))}
              >
                <span className="block truncate font-medium hover:underline">{c.title}</span>
                <span className="text-xs text-stone-500 dark:text-stone-400">
                  {c.author} · {c.message_count} {c.message_count === 1 ? "pergunta" : "perguntas"} ·{" "}
                  {new Date(c.updated_at).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" })}
                </span>
              </button>
              {c.pending_proposals > 0 && (
                <Badge tone="accent">
                  {c.pending_proposals} {c.pending_proposals === 1 ? "proposta" : "propostas"} por decidir
                </Badge>
              )}
              {(c.created_by === currentUserId || isOwner) && (
                <IconButton icon={Trash2} label="Apagar conversa" variant="danger" onClick={() => remove(c)} />
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
