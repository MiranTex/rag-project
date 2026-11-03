import { useState } from "react";
import { AlertTriangle, BookmarkPlus, CheckCircle2, CircleHelp, Compass, FileUp, Pin, ScanSearch, XCircle } from "lucide-react";
import { research } from "../api";
import PageShell from "../components/PageShell";
import { Button, Empty, ErrorText, ExcerptCard, Section, Spinner, Tabs, documentLabel, inputClass } from "../components/ui";
import { useResearch } from "../research/ResearchContext";

const TABS = [
  { value: "map", label: "Mapa do tema" },
  { value: "gaps", label: "Lacunas" },
  { value: "text", label: "O meu texto" },
];

function ScopeSelect({ value, onChange }) {
  const { projects } = useResearch();
  return (
    <select className={`${inputClass} sm:max-w-64`} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Onde procurar">
      <option value="">Em toda a base</option>
      {projects.map(({ project, document_count }) => (
        <option key={project.project_id} value={project.project_id} disabled={!document_count}>
          Só no projeto: {project.title}
          {document_count ? "" : " (sem documentos)"}
        </option>
      ))}
    </select>
  );
}

function DocumentLink({ doc }) {
  const { openReader, pinDocument } = useResearch();
  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <button type="button" className="truncate text-left hover:underline" onClick={() => openReader({ document_id: doc.document_id, page: 1 })}>
        {documentLabel(doc)}
        {doc.year ? ` (${doc.year})` : ""}
      </button>
      <button type="button" title="Fixar no projeto" aria-label="Fixar no projeto" onClick={() => pinDocument(doc.document_id)} className="shrink-0 rounded p-0.5 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200">
        <Pin className="size-3.5" />
      </button>
    </span>
  );
}

function Bars({ values }) {
  const entries = Object.entries(values);
  if (!entries.length) return null;
  const max = Math.max(...entries.map(([, v]) => v));
  return (
    <div className="flex h-24 items-end gap-1" role="img" aria-label="Documentos por ano">
      {entries.map(([year, count]) => (
        <div key={year} className="flex flex-1 flex-col items-center gap-1" title={`${year}: ${count}`}>
          <div className="w-full rounded-t bg-accent-400/80" style={{ height: `${(count / max) * 72}px` }} />
          <span className="text-[10px] text-stone-500">{year}</span>
        </div>
      ))}
    </div>
  );
}

function MapView({ data }) {
  if (!data.documents) return <Empty>Não há documentos sobre este tema.</Empty>;
  return (
    <>
      <Section title={`${data.documents} documentos, ${data.clusters.length} subtema${data.clusters.length === 1 ? "" : "s"}`}>
        <div className="grid gap-3 sm:grid-cols-2">
          {data.clusters.map((cluster) => (
            <div key={cluster.label} className="rounded-xl border border-stone-200 p-4 dark:border-stone-800">
              <h3 className="mb-2 text-sm font-semibold">{cluster.label}</h3>
              <ul className="space-y-1 text-sm">
                {cluster.documents.map((doc) => (
                  <li key={doc.document_id}>
                    <DocumentLink doc={doc} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>
      <div className="grid gap-6 sm:grid-cols-2">
        <Section title="Pessoas que mais aparecem">
          <ul className="space-y-1 text-sm">
            {data.people.map((p) => (
              <li key={`${p.name}-${p.role}`} className="flex gap-2">
                <span className="flex-1">{p.name}</span>
                <span className="text-stone-500">
                  {p.role} · {p.count}
                </span>
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Documentos por ano">
          <Bars values={data.years} />
        </Section>
      </div>
      {data.keywords.length > 0 && (
        <Section title="Palavras-chave">
          <div className="flex flex-wrap gap-1.5">
            {data.keywords.map((k) => (
              <span key={k.keyword} className="rounded-full bg-stone-200/70 px-2.5 py-0.5 text-xs dark:bg-stone-800">
                {k.keyword} <span className="text-stone-500">{k.count}</span>
              </span>
            ))}
          </div>
        </Section>
      )}
      {data.references.length > 0 && (
        <Section title="Referências citadas por vários destes documentos" description="Leituras de base sobre o tema.">
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {data.references.map((r) => (
              <li key={r.reference}>
                {r.reference} <span className="text-stone-500">({r.cited_by} documentos)</span>
              </li>
            ))}
          </ol>
        </Section>
      )}
    </>
  );
}

function GapsView({ data }) {
  const { openReader } = useResearch();
  const documents = data.open_questions.documents || [];
  return (
    <>
      <p className="mb-6 text-sm text-stone-600 dark:text-stone-400">
        {data.coverage.related_documents} documento{data.coverage.related_documents === 1 ? "" : "s"} próximos deste tema
        {Object.keys(data.coverage.years).length > 0 && ` (${Object.keys(data.coverage.years).join(", ")})`}.
      </p>
      {data.suggestions.length > 0 && (
        <Section title="Temas por explorar" description="Sugestões a partir do que os trabalhos deixaram em aberto. Confirma nos documentos.">
          <div className="space-y-3">
            {data.suggestions.map((s) => (
              <div key={s.title} className="rounded-xl border border-stone-200 p-4 dark:border-stone-800">
                <h3 className="text-sm font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm text-stone-700 dark:text-stone-300">{s.description}</p>
                <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-stone-500">
                  Com base em:
                  {s.documents.map((d) => (
                    <DocumentLink key={d.document_id} doc={d} />
                  ))}
                </p>
              </div>
            ))}
          </div>
        </Section>
      )}
      <Section title="O que ficou em aberto">
        {documents.length === 0 ? (
          <Empty>Nenhum documento com trabalho futuro, limitações ou recomendações sobre este tema.</Empty>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) =>
              doc.open.map((open) => (
                <ExcerptCard
                  key={`${doc.document_id}-${open.section}`}
                  excerpt={{ ...doc, page: open.pages, text: open.text }}
                  onOpen={() => openReader({ document_id: doc.document_id, page: Number(String(open.pages).split("–")[0]), text: open.text })}
                >
                  {open.section && <p className="mt-1 text-xs text-stone-500">{open.section}</p>}
                </ExcerptCard>
              )),
            )}
          </div>
        )}
      </Section>
    </>
  );
}

const VERDICTS = {
  supported: { label: "Apoiada", icon: CheckCircle2, className: "text-emerald-700 dark:text-emerald-400" },
  contradicted: { label: "Contradita", icon: XCircle, className: "text-red-700 dark:text-red-400" },
  unsupported: { label: "Sem apoio na base", icon: CircleHelp, className: "text-amber-700 dark:text-amber-400" },
  unchecked: { label: "Por verificar (modelo indisponível)", icon: CircleHelp, className: "text-stone-500" },
};

function TextView({ data, onCheckClaims, checking, claims }) {
  const { openReader, saveItem } = useResearch();
  return (
    <>
      {data.overlap.length > 0 && (
        <Section title="Atenção: já existe trabalho muito parecido">
          <div className="space-y-3">
            {data.overlap.map((doc) => (
              <div key={doc.document_id} className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/30">
                <p className="flex items-center gap-2 font-medium">
                  <AlertTriangle className="size-4 text-amber-600" />
                  <DocumentLink doc={doc} />
                  <span className="ml-auto text-xs text-stone-500">
                    {doc.level === "high" ? "quase o mesmo" : "muito próximo"} · {Math.round(doc.similarity * 100)}%
                  </span>
                </p>
                {doc.difference && <p className="mt-2 text-stone-700 dark:text-stone-300">{doc.difference}</p>}
              </div>
            ))}
          </div>
        </Section>
      )}
      <Section title="Documentos mais parecidos com o teu texto">
        <ul className="space-y-1 text-sm">
          {data.similar_documents.map((doc) => (
            <li key={doc.document_id} className="flex gap-2">
              <span className="min-w-0 flex-1">
                <DocumentLink doc={doc} />
              </span>
              {doc.similarity != null && <span className="text-stone-500">{Math.round(doc.similarity * 100)}%</span>}
            </li>
          ))}
        </ul>
      </Section>
      <Section
        title="Parágrafo a parágrafo"
        description="O que na base está mais próximo de cada parágrafo teu: pode apoiar, completar ou contradizer."
        actions={
          <Button icon={ScanSearch} busy={checking} onClick={onCheckClaims}>
            Verificar afirmações
          </Button>
        }
      >
        {claims && (
          <div className="mb-6 space-y-3">
            {claims.length === 0 && <Empty>Não encontrei afirmações para verificar.</Empty>}
            {claims.map((c, i) => {
              const verdict = VERDICTS[c.verdict] || VERDICTS.unchecked;
              const Icon = verdict.icon;
              return (
                <div key={i} className="rounded-xl border border-stone-200 p-3 text-sm dark:border-stone-800">
                  <p className="font-medium">“{c.claim}”</p>
                  <p className={`mt-1 flex items-center gap-1.5 ${verdict.className}`}>
                    <Icon className="size-4" />
                    {verdict.label}
                    {c.explanation && <span className="text-stone-600 dark:text-stone-400">— {c.explanation}</span>}
                  </p>
                  <div className="mt-2 space-y-2">
                    {c.evidence.filter((e) => e.used || c.verdict === "unchecked").map((e) => (
                      <ExcerptCard key={`${e.document_id}-${e.page}`} excerpt={e} onOpen={() => openReader(e)} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <div className="space-y-5">
          {data.paragraphs.map((p) => (
            <div key={p.index} className="grid gap-3 lg:grid-cols-2">
              <p className="rounded-lg bg-stone-100 p-3 text-sm dark:bg-stone-800/60">{p.text}</p>
              <div className="space-y-2">
                {p.excerpts.map((e) => (
                  <ExcerptCard
                    key={`${e.document_id}-${e.page}-${e.text.slice(0, 15)}`}
                    excerpt={e}
                    onOpen={() => openReader(e)}
                    actions={
                      <Button
                        variant="ghost"
                        icon={BookmarkPlus}
                        onClick={() =>
                          saveItem({ kind: "excerpt", title: documentLabel(e), text: e.text, source: { document_id: e.document_id, filename: e.filename, page: e.page } })
                        }
                      >
                        Guardar
                      </Button>
                    }
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}

export default function DiscoverPage({ onOpenSidebar }) {
  const [tab, setTab] = useState("map");
  const [projectId, setProjectId] = useState("");
  const [topic, setTopic] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [results, setResults] = useState({});
  const [claims, setClaims] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function run(kind, action) {
    setBusy(kind);
    setError("");
    try {
      const data = await action();
      setResults((prev) => ({ ...prev, [kind]: data }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  const topicRequest = () => ({ topic: topic.trim(), project_id: projectId || null });

  async function checkClaims() {
    setBusy("claims");
    setError("");
    try {
      // Com um ficheiro, o texto vem dos parágrafos que o servidor leu.
      const source = file ? results.text.paragraphs.map((p) => p.text).join("\n\n") : text;
      setClaims((await research.checkClaims({ text: source.slice(0, 20000), project_id: projectId || null })).claims);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <PageShell
      title="Descobrir"
      description="Por onde começar: um panorama do tema, o que ficou por estudar e o que na base se parece com o teu texto."
      onOpenSidebar={onOpenSidebar}
    >
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      <div className="mb-3">
        <ScopeSelect value={projectId} onChange={setProjectId} />
      </div>

      {tab !== "text" ? (
        <form
          className="mb-6 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (topic.trim().length < 3) return;
            run(tab, () => (tab === "map" ? research.map(topicRequest()) : research.gaps(topicRequest())));
          }}
        >
          <input
            className={inputClass}
            placeholder="Descreve o tema numa frase (ex.: sistemas de recomendação de livros em bibliotecas)"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
          <Button type="submit" variant="primary" icon={Compass} busy={busy === tab}>
            {tab === "map" ? "Ver mapa" : "Procurar lacunas"}
          </Button>
        </form>
      ) : (
        <div className="mb-6 space-y-2">
          <textarea
            className={inputClass}
            rows={8}
            placeholder="Cola aqui o teu texto: um resumo, uma proposta, um capítulo. Não é guardado."
            value={text}
            disabled={!!file}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-stone-300 px-3 py-1.5 text-sm hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800">
              <FileUp className="size-4" />
              {file ? file.name : "Ou carrega um ficheiro (PDF, Word, texto)"}
              <input type="file" accept=".pdf,.docx,.txt,.md" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </label>
            {file && (
              <Button variant="ghost" onClick={() => setFile(null)}>
                Usar o texto colado
              </Button>
            )}
            <Button
              variant="primary"
              icon={ScanSearch}
              busy={busy === "text"}
              className="ml-auto"
              disabled={!file && text.trim().length < 50}
              onClick={() => {
                setClaims(null);
                run("text", () => research.analyzeText({ text, file, projectId }));
              }}
            >
              Comparar com a base
            </Button>
          </div>
        </div>
      )}

      <ErrorText>{error}</ErrorText>
      {busy && busy !== "claims" && <Spinner label="A analisar a base…" />}
      {!busy && tab === "map" && results.map && <MapView data={results.map} />}
      {!busy && tab === "gaps" && results.gaps && <GapsView data={results.gaps} />}
      {tab === "text" && results.text && busy !== "text" && (
        <TextView data={results.text} onCheckClaims={checkClaims} checking={busy === "claims"} claims={claims} />
      )}
    </PageShell>
  );
}
