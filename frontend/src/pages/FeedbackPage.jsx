import { useEffect, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { listFeedback } from "../api";
import Markdown from "../components/Markdown";
import PageShell from "../components/PageShell";
import { Empty, ErrorText, Spinner, Tabs } from "../components/ui";

const TABS = [
  { value: "-1", label: "Negativas" },
  { value: "1", label: "Positivas" },
  { value: "", label: "Todas" },
];

// Avaliações das respostas do chat: ajudam a perceber onde a pesquisa ou o modelo falham.
export default function FeedbackPage({ onOpenSidebar }) {
  const [rating, setRating] = useState("-1");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    listFeedback(rating).then(setData, (err) => setError(err.message));
  }, [rating]);

  return (
    <PageShell title="Avaliações" description="O que as pessoas acharam das respostas do chat, com a pergunta, a resposta e as fontes usadas." onOpenSidebar={onOpenSidebar}>
      {data && (
        <p className="mb-4 flex gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
            <ThumbsUp className="size-4" /> {data.positive}
          </span>
          <span className="flex items-center gap-1.5 text-red-700 dark:text-red-400">
            <ThumbsDown className="size-4" /> {data.negative}
          </span>
        </p>
      )}
      <Tabs tabs={TABS} value={rating} onChange={setRating} />
      <ErrorText>{error}</ErrorText>
      {!data && !error && <Spinner label="A carregar…" />}
      {data && data.items.length === 0 && <Empty>Sem avaliações.</Empty>}
      {data && (
        <ul className="space-y-3">
          {data.items.map((item) => (
            <li key={item.feedback_id} className="rounded-xl border border-stone-200 p-4 text-sm dark:border-stone-800">
              <p className="mb-1 flex items-center gap-2 text-xs text-stone-500">
                {item.rating > 0 ? <ThumbsUp className="size-3.5 text-emerald-600" /> : <ThumbsDown className="size-3.5 text-red-600" />}
                {item.user} · {new Date(item.created_at).toLocaleString("pt-PT")} · {item.mode}
              </p>
              {item.reason && <p className="mb-2 font-medium">“{item.reason}”</p>}
              <p className="font-medium">{item.question}</p>
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-accent-700 dark:text-accent-400">Resposta e fontes</summary>
                <div className="mt-2">
                  <Markdown>{item.answer}</Markdown>
                  {item.sources.length > 0 && (
                    <p className="mt-2 text-xs text-stone-500">
                      Fontes: {item.sources.map((s) => `${s.filename} p.${s.page}`).join("; ")}
                    </p>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
