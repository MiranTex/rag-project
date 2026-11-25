import { useEffect, useState } from "react";
import { Send, Trash2 } from "lucide-react";
import { research } from "../../api";
import { ErrorText, IconButton, inputClass, useConfirm } from "../../components/ui";

// Comentários do projeto (itemId null) ou de uma entrada do caderno. Qualquer membro comenta; apaga quem
// escreveu ou o dono do projeto.
export default function Comments({ projectId, itemId = null, currentUserId, isOwner, onCountChange }) {
  const confirm = useConfirm();
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  const load = () =>
    research.comments(projectId).then((all) => {
      const mine = all.filter((c) => (c.item_id || null) === itemId);
      setComments(mine);
      onCountChange?.(mine.length);
    });
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

  async function remove(comment) {
    if (!(await confirm({ title: "Apagar comentário?", message: `"${comment.text.slice(0, 120)}"` }))) return;
    research.deleteComment(projectId, comment.comment_id).then(load, (err) => setError(err.message));
  }

  return (
    <div className="space-y-3">
      {comments.length > 0 && (
        <ul className="space-y-3">
          {comments.map((c) => (
            <li key={c.comment_id} className="flex gap-2 text-sm">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold uppercase text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                {(c.author || "?").slice(0, 1)}
              </span>
              <div className="min-w-0 flex-1">
                <p>
                  <span className="font-medium">{c.author}</span>{" "}
                  <span className="text-xs text-stone-500 dark:text-stone-400">
                    {new Date(c.created_at).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" })}
                    {c.via && ` · via ${c.via}`}
                  </span>
                </p>
                <p className="whitespace-pre-line text-stone-700 dark:text-stone-300">{c.text}</p>
              </div>
              {(c.author_id === currentUserId || isOwner) && <IconButton icon={Trash2} label="Apagar comentário" variant="danger" onClick={() => remove(c)} />}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={send} className="flex gap-2">
        <input
          className={inputClass}
          placeholder="Escreve um comentário"
          aria-label="Novo comentário"
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <IconButton icon={Send} label="Enviar comentário" variant="secondary" type="submit" />
      </form>
      <ErrorText>{error}</ErrorText>
    </div>
  );
}
