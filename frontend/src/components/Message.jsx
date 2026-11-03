import { useState } from "react";
import { AlertCircle, BookmarkPlus, Check, ChevronRight, Copy, FileText, ThumbsDown, ThumbsUp } from "lucide-react";
import { sendFeedback } from "../api";
import { useResearch } from "../research/ResearchContext";
import AgentSteps from "./AgentSteps";
import ExportLinks from "./ExportLinks";
import Markdown from "./Markdown";

function uniqueSources(sources = []) {
  const seen = new Map();
  for (const source of sources) {
    const key = `${source.filename}#${source.page}`;
    if (!seen.has(key)) seen.set(key, source);
  }
  return [...seen.values()];
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-2" aria-label="A responder">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-1.5 animate-bounce rounded-full bg-stone-400"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={copied ? "Copiado" : "Copiar resposta"}
      aria-label="Copiar resposta"
      className="rounded-md p-1.5 text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-700 dark:hover:text-stone-300"
    >
      {copied ? <Check className="size-4 text-emerald-600 dark:text-emerald-400" /> : <Copy className="size-4" />}
    </button>
  );
}

// 👍/👎 na resposta; o 👎 pede o motivo (opcional), que é o que mais ajuda a perceber o que falhou.
function Feedback({ msg, sources }) {
  const [given, setGiven] = useState(msg.feedback || 0);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");

  async function send(rating, why = "") {
    setGiven(rating);
    setAsking(false);
    try {
      await sendFeedback({
        rating,
        reason: why,
        question: msg.question,
        answer: msg.answer,
        mode: msg.mode || "agent",
        sources: sources.map(({ document_id, filename, page }) => ({ document_id, filename, page })),
        project_id: msg.projectId || null,
      });
    } catch {
      setGiven(0);
    }
  }

  const button = "rounded-md p-1.5 hover:bg-stone-100 dark:hover:bg-stone-800";
  return (
    <>
      <button
        type="button"
        aria-label="Boa resposta"
        title="Boa resposta"
        disabled={!!given}
        onClick={() => send(1)}
        className={`${button} ${given === 1 ? "text-emerald-600" : "text-stone-400 dark:text-stone-500"}`}
      >
        <ThumbsUp className="size-4" />
      </button>
      <button
        type="button"
        aria-label="Má resposta"
        title="Má resposta"
        disabled={!!given}
        onClick={() => setAsking(true)}
        className={`${button} ${given === -1 ? "text-red-600" : "text-stone-400 dark:text-stone-500"}`}
      >
        <ThumbsDown className="size-4" />
      </button>
      {asking && (
        <form
          className="flex w-full gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(-1, reason.trim());
          }}
        >
          <input
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="O que falhou? (opcional: resposta errada, fonte errada, incompleta…)"
            className="flex-1 rounded-lg border border-stone-300 bg-white px-2.5 py-1 text-xs outline-none dark:border-stone-700 dark:bg-stone-900"
          />
          <button type="submit" className="rounded-lg bg-stone-800 px-2.5 py-1 text-xs text-white dark:bg-stone-200 dark:text-stone-900">
            Enviar
          </button>
        </form>
      )}
    </>
  );
}

function RetrievalDetails({ msg }) {
  const [open, setOpen] = useState(false);
  const diagnostics = msg.retrievalDiagnostics || [];
  const queries = msg.expandedQueries || [];
  if (!diagnostics.length && !queries.length) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-stone-500 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200"
      >
        Detalhes da pesquisa
        <ChevronRight className={`size-3 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="animate-fade-up mt-2 space-y-3 rounded-lg border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 p-3 text-xs">
          {queries.length > 0 && (
            <div>
              <p className="mb-1 font-medium text-stone-700 dark:text-stone-300">Variantes da pergunta</p>
              <ol className="list-decimal space-y-0.5 pl-4 text-stone-600 dark:text-stone-400">
                {queries.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            </div>
          )}
          {diagnostics.length > 0 && (
            <div className="overflow-x-auto">
              <p className="mb-1 font-medium text-stone-700 dark:text-stone-300">Ranking</p>
              <table className="w-full font-mono text-stone-600 dark:text-stone-400">
                <thead className="text-left text-stone-400 dark:text-stone-500">
                  <tr>
                    <th className="pr-3 font-normal">fonte</th>
                    <th className="pr-3 font-normal">final</th>
                    <th className="pr-3 font-normal">vetor</th>
                    <th className="pr-3 font-normal">palavras</th>
                    <th className="pr-3 font-normal">posição</th>
                    <th className="font-normal">densidade</th>
                  </tr>
                </thead>
                <tbody>
                  {diagnostics.map((d, i) => (
                    <tr key={i} className="border-t border-stone-100 dark:border-stone-800">
                      <td className="max-w-48 truncate py-1 pr-3" title={d.filename}>
                        {d.filename} p.{d.page}
                      </td>
                      <td className="pr-3 font-medium text-stone-800 dark:text-stone-200">{d.final_score.toFixed(3)}</td>
                      <td className="pr-3">{d.vector_score.toFixed(3)}</td>
                      <td className="pr-3">{d.keyword_overlap.toFixed(3)}</td>
                      <td className="pr-3">{d.position_penalty.toFixed(3)}</td>
                      <td>{d.density_score.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Message({ msg, pending }) {
  const { openReader, saveItem } = useResearch();
  const isAgent = msg.mode === "agent";
  const isError = msg.answer?.startsWith("Erro:");
  const sources = uniqueSources(msg.sources);
  const done = !!msg.answer || !pending;

  return (
    <article className="animate-fade-up space-y-4">
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-stone-200/70 dark:bg-stone-800 px-4 py-2.5 text-stone-900 dark:text-stone-100">
          {msg.question}
        </div>
      </div>

      <div className="group">
        {isAgent && <AgentSteps steps={msg.steps} done={done} stopped={msg.stopped} />}

        {isError ? (
          <p className="flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {msg.answer.replace(/^Erro:\s*/, "")}
          </p>
        ) : msg.answer ? (
          <div className={msg.blocked ? "rounded-lg border border-stone-200 bg-white px-4 py-3 dark:border-stone-700 dark:bg-stone-800" : ""}>
            <Markdown>{msg.answer}</Markdown>
          </div>
        ) : pending && !msg.steps?.length ? (
          <TypingDots />
        ) : null}

        {isAgent && <ExportLinks exports={msg.exports} />}

        {msg.stopped && !(isAgent && msg.steps?.length && !msg.answer) && (
          <p className="mt-2 text-sm text-stone-400 dark:text-stone-500">Resposta interrompida.</p>
        )}

        {msg.answer && !isError && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <CopyButton text={msg.answer} />
            {!msg.blocked && (
              <button
                type="button"
                title="Guardar no caderno de um projeto"
                aria-label="Guardar no projeto"
                onClick={() =>
                  saveItem({
                    kind: "answer",
                    title: msg.question.slice(0, 200),
                    text: msg.answer,
                    source: {
                      question: msg.question,
                      sources: sources.map(({ document_id, filename, page }) => ({ document_id, filename, page })),
                    },
                  })
                }
                className="rounded-md p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-300"
              >
                <BookmarkPlus className="size-4" />
              </button>
            )}
            {!msg.blocked && <Feedback msg={msg} sources={sources} />}
            {sources.map((source) => (
              <button
                type="button"
                key={`${source.filename}#${source.page}`}
                title={source.text ? source.text.slice(0, 300) : "Abrir no leitor"}
                onClick={() => source.document_id && openReader(source)}
                className="inline-flex max-w-full items-center gap-1 rounded-full border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 px-2.5 py-0.5 text-xs text-stone-600 dark:text-stone-400 hover:border-stone-400 dark:hover:border-stone-600"
              >
                <FileText className="size-3 shrink-0 text-stone-400 dark:text-stone-500" />
                <span className="truncate">{source.filename}</span>
                <span className="shrink-0 text-stone-400 dark:text-stone-500">p. {source.page}</span>
              </button>
            ))}
          </div>
        )}

        {!isAgent && <RetrievalDetails msg={msg} />}
      </div>
    </article>
  );
}
