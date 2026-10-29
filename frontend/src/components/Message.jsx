import { useState } from "react";
import { AlertCircle, Check, ChevronRight, Copy, FileText } from "lucide-react";
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
      className="rounded-md p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
    >
      {copied ? <Check className="size-4 text-emerald-600" /> : <Copy className="size-4" />}
    </button>
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
        className="flex items-center gap-1 text-xs text-stone-500 hover:text-stone-800"
      >
        Detalhes da pesquisa
        <ChevronRight className={`size-3 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="animate-fade-up mt-2 space-y-3 rounded-lg border border-stone-200 bg-white p-3 text-xs">
          {queries.length > 0 && (
            <div>
              <p className="mb-1 font-medium text-stone-700">Variantes da pergunta</p>
              <ol className="list-decimal space-y-0.5 pl-4 text-stone-600">
                {queries.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            </div>
          )}
          {diagnostics.length > 0 && (
            <div className="overflow-x-auto">
              <p className="mb-1 font-medium text-stone-700">Ranking</p>
              <table className="w-full font-mono text-stone-600">
                <thead className="text-left text-stone-400">
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
                    <tr key={i} className="border-t border-stone-100">
                      <td className="max-w-48 truncate py-1 pr-3" title={d.filename}>
                        {d.filename} p.{d.page}
                      </td>
                      <td className="pr-3 font-medium text-stone-800">{d.final_score.toFixed(3)}</td>
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
  const isAgent = msg.mode === "agent";
  const isError = msg.answer?.startsWith("Erro:");
  const sources = uniqueSources(msg.sources);
  const done = !!msg.answer || !pending;

  return (
    <article className="animate-fade-up space-y-4">
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-stone-200/70 px-4 py-2.5 text-stone-900">
          {msg.question}
        </div>
      </div>

      <div className="group">
        {isAgent && <AgentSteps steps={msg.steps} done={done} />}

        {isError ? (
          <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {msg.answer.replace(/^Erro:\s*/, "")}
          </p>
        ) : msg.answer ? (
          <div className={msg.blocked ? "rounded-lg border border-stone-200 bg-white px-4 py-3" : ""}>
            <Markdown>{msg.answer}</Markdown>
          </div>
        ) : pending && !msg.steps?.length ? (
          <TypingDots />
        ) : null}

        {isAgent && <ExportLinks exports={msg.exports} />}

        {msg.answer && !isError && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <CopyButton text={msg.answer} />
            {sources.map((source) => (
              <span
                key={`${source.filename}#${source.page}`}
                title={source.text ? source.text.slice(0, 300) : undefined}
                className="inline-flex max-w-full items-center gap-1 rounded-full border border-stone-200 bg-white px-2.5 py-0.5 text-xs text-stone-600"
              >
                <FileText className="size-3 shrink-0 text-stone-400" />
                <span className="truncate">{source.filename}</span>
                <span className="shrink-0 text-stone-400">p. {source.page}</span>
              </span>
            ))}
          </div>
        )}

        {!isAgent && <RetrievalDetails msg={msg} />}
      </div>
    </article>
  );
}
