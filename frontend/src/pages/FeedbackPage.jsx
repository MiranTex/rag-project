import { useEffect, useState } from "react";
import { MessageSquareText, ThumbsDown, ThumbsUp } from "lucide-react";
import { listFeedback } from "../api";
import Markdown from "../components/Markdown";
import PageShell from "../components/PageShell";
import { Badge, Card, EmptyState, ErrorText, Spinner, Tabs } from "../components/ui";

// Avaliações das respostas do chat: ajudam a perceber onde a pesquisa ou o modelo falham.
export default function FeedbackPage({ onOpenSidebar }) {
  const [rating, setRating] = useState("-1");
  const [data, setData] = useState(null);
  // Os totais mantêm-se enquanto se carrega outro separador, para as contagens não piscarem.
  const [totals, setTotals] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setError("");
    listFeedback(rating).then(
      (result) => {
        setData(result);
        setTotals({ positive: result.positive, negative: result.negative });
      },
      (err) => setError(err.message),
    );
  }, [rating]);

  const tabs = [
    { value: "-1", label: "Negativas", icon: ThumbsDown, count: totals?.negative },
    { value: "1", label: "Positivas", icon: ThumbsUp, count: totals?.positive },
    { value: "", label: "Todas", count: totals ? totals.positive + totals.negative : undefined },
  ];

  return (
    <PageShell
      title="Avaliações"
      subtitle="O que as pessoas acharam das respostas do chat, com a pergunta, a resposta e as fontes usadas."
      width="wide"
      tabs={<Tabs inHeader tabs={tabs} value={rating} onChange={setRating} label="Filtrar avaliações" />}
      onOpenSidebar={onOpenSidebar}
    >
      <ErrorText>{error}</ErrorText>
      {!data && !error && <Spinner label="A carregar…" />}
      {data && data.items.length === 0 && (
        <EmptyState icon={MessageSquareText} title="Sem avaliações">
          Quando alguém avaliar uma resposta do chat (polegar para cima ou para baixo), aparece aqui.
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <ul className="space-y-3">
          {data.items.map((item) => (
            <li key={item.feedback_id}>
              <Card className="p-4 text-sm">
                <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
                  {item.rating > 0 ? (
                    <Badge tone="success">
                      <ThumbsUp className="size-3" /> Positiva
                    </Badge>
                  ) : (
                    <Badge className="bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300">
                      <ThumbsDown className="size-3" /> Negativa
                    </Badge>
                  )}
                  <span>{item.user}</span>
                  <span>·</span>
                  <span>{new Date(item.created_at).toLocaleString("pt-PT")}</span>
                  {item.mode && <Badge tone="outline">{item.mode}</Badge>}
                </p>
                <p className="font-medium text-stone-900 dark:text-stone-100">{item.question}</p>
                {item.reason && <p className="mt-1 border-l-2 border-stone-300 pl-3 text-stone-700 dark:border-stone-700 dark:text-stone-300">“{item.reason}”</p>}
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-medium text-accent-700 hover:underline dark:text-accent-400">Resposta e fontes</summary>
                  <div className="mt-2 rounded-lg bg-stone-50 p-3 dark:bg-stone-800/50">
                    <Markdown>{item.answer}</Markdown>
                    {item.sources.length > 0 && (
                      <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">
                        Fontes: {item.sources.map((s) => `${s.filename} p.${s.page}`).join("; ")}
                      </p>
                    )}
                  </div>
                </details>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
