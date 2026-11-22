import { useRef, useState } from "react";
import { AlertTriangle, BookmarkPlus, CheckCircle2, CircleHelp, Compass, FileText, FileUp, Map as MapIcon, Pin, ScanSearch, Telescope, X, XCircle } from "lucide-react";
import { research } from "../api";
import PageShell from "../components/PageShell";
import { Badge, Button, Card, EmptyState, ErrorText, ExcerptCard, Field, IconButton, Section, Spinner, Tabs, documentLabel, inputClass } from "../components/ui";
import { useResearch } from "../research/ResearchContext";

const TABS = [
  { value: "map", label: "Mapa do tema", icon: MapIcon },
  { value: "gaps", label: "Lacunas", icon: Telescope },
  { value: "text", label: "O meu texto", icon: FileText },
];

const TAB_HINTS = {
  map: "Um panorama do tema: subtemas, pessoas, anos, palavras-chave e as referências que mais se repetem.",
  gaps: "O que os trabalhos sobre o tema deixaram em aberto: trabalho futuro, limitações e recomendações.",
  text: "Cola ou carrega o teu texto: vês o que na base é parecido, parágrafo a parágrafo, e podes verificar as afirmações.",
};

function ScopeSelect({ value, onChange }) {
  const { projects } = useResearch();
  return (
    <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
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
      <IconButton icon={Pin} label={`Fixar “${documentLabel(doc)}” no projeto`} onClick={() => pinDocument(doc.document_id)} className="size-6" />
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
          <span className="text-[10px] text-stone-500 dark:text-stone-400">{year}</span>
        </div>
      ))}
    </div>
  );
}

function MapView({ data }) {
  if (!data.documents) return <EmptyState icon={MapIcon} title="Não há documentos sobre este tema">Experimenta descrever o tema de outra forma ou procurar em toda a base.</EmptyState>;
  return (
    <>
      <Section title={`${data.documents} documentos, ${data.clusters.length} subtema${data.clusters.length === 1 ? "" : "s"}`}>
        <div className="grid gap-3 sm:grid-cols-2">
          {data.clusters.map((cluster) => (
            <Card key={cluster.label} className="p-4">
              <h3 className="mb-2 text-sm font-semibold">{cluster.label}</h3>
              <ul className="space-y-1 text-sm">
                {cluster.documents.map((doc) => (
                  <li key={doc.document_id}>
                    <DocumentLink doc={doc} />
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      </Section>
      <div className="grid gap-6 sm:grid-cols-2">
        <Section title="Pessoas que mais aparecem">
          <ul className="space-y-1 text-sm">
            {data.people.map((p) => (
              <li key={`${p.name}-${p.role}`} className="flex gap-2">
                <span className="flex-1">{p.name}</span>
                <span className="text-stone-500 dark:text-stone-400">
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
              <Badge key={k.keyword}>
                {k.keyword} <span className="font-normal text-stone-500 dark:text-stone-400">{k.count}</span>
              </Badge>
            ))}
          </div>
        </Section>
      )}
      {data.references.length > 0 && (
        <Section title="Referências citadas por vários destes documentos" description="Leituras de base sobre o tema.">
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {data.references.map((r) => (
              <li key={r.reference}>
                {r.reference} <span className="text-stone-500 dark:text-stone-400">({r.cited_by} documentos)</span>
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
              <Card key={s.title} className="p-4">
                <h3 className="text-sm font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm text-stone-700 dark:text-stone-300">{s.description}</p>
                <p className="mt-2 flex flex-wrap items-center gap-x-3 text-xs text-stone-500 dark:text-stone-400">
                  Com base em:
                  {s.documents.map((d) => (
                    <DocumentLink key={d.document_id} doc={d} />
                  ))}
                </p>
              </Card>
            ))}
          </div>
        </Section>
      )}
      <Section title="O que ficou em aberto">
        {documents.length === 0 ? (
          <EmptyState icon={Telescope} title="Nada em aberto">Nenhum documento com trabalho futuro, limitações ou recomendações sobre este tema.</EmptyState>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) =>
              doc.open.map((open) => (
                <ExcerptCard
                  key={`${doc.document_id}-${open.section}`}
                  excerpt={{ ...doc, page: open.pages, text: open.text }}
                  onOpen={() => openReader({ document_id: doc.document_id, page: Number(String(open.pages).split("–")[0]), text: open.text })}
                >
                  {open.section && <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">{open.section}</p>}
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
  unchecked: { label: "Por verificar (modelo indisponível)", icon: CircleHelp, className: "text-stone-500 dark:text-stone-400" },
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
                  <AlertTriangle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <DocumentLink doc={doc} />
                  <span className="ml-auto text-xs text-stone-500 dark:text-stone-400">
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
              {doc.similarity != null && <span className="text-stone-500 dark:text-stone-400">{Math.round(doc.similarity * 100)}%</span>}
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
            {claims.length === 0 && <EmptyState title="Sem afirmações">Não encontrei afirmações para verificar.</EmptyState>}
            {claims.map((c, i) => {
              const verdict = VERDICTS[c.verdict] || VERDICTS.unchecked;
              const Icon = verdict.icon;
              return (
                <Card key={i} className="p-3 text-sm">
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
                </Card>
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
  const fileRef = useRef(null);
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
      subtitle="Por onde começar: um panorama do tema, o que ficou por estudar e o que na base se parece com o teu texto."
      width="wide"
      tabs={<Tabs inHeader tabs={TABS} value={tab} onChange={setTab} label="Tipo de análise" />}
      onOpenSidebar={onOpenSidebar}
    >
      <p className="mb-4 text-sm text-stone-500 dark:text-stone-400">{TAB_HINTS[tab]}</p>
      <Card className="mb-6 p-4">
        {tab !== "text" ? (
          <form
            className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_16rem]"
            onSubmit={(e) => {
              e.preventDefault();
              if (topic.trim().length < 3) return;
              run(tab, () => (tab === "map" ? research.map(topicRequest()) : research.gaps(topicRequest())));
            }}
          >
            <Field label="Tema" hint="Descreve-o numa frase.">
              <input
                className={inputClass}
                placeholder="ex.: sistemas de recomendação de livros em bibliotecas"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </Field>
            <Field label="Onde procurar">
              <ScopeSelect value={projectId} onChange={setProjectId} />
            </Field>
            <div className="flex justify-end sm:col-span-2">
              <Button type="submit" variant="primary" icon={Compass} busy={busy === tab} disabled={topic.trim().length < 3}>
                {tab === "map" ? "Ver mapa" : "Procurar lacunas"}
              </Button>
            </div>
          </form>
        ) : (
          <div className="space-y-3">
            <Field label="O teu texto" hint="Um resumo, uma proposta, um capítulo (mín. 50 caracteres). Não é guardado.">
              <textarea
                className={inputClass}
                rows={8}
                placeholder={file ? `A usar o ficheiro ${file.name}` : "Cola aqui o teu texto"}
                value={text}
                disabled={!!file}
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_16rem]">
              <div>
                <span className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">Ou um ficheiro</span>
                <div className="flex flex-wrap items-center gap-2">
                  <Button icon={FileUp} onClick={() => fileRef.current?.click()}>
                    {file ? "Escolher outro" : "Carregar ficheiro (PDF, Word, texto)"}
                  </Button>
                  {file && (
                    <Badge tone="accent">
                      <span className="truncate">{file.name}</span>
                      <button type="button" aria-label="Usar o texto colado em vez do ficheiro" title="Usar o texto colado" onClick={() => setFile(null)} className="-mr-0.5 shrink-0 rounded opacity-70 hover:opacity-100">
                        <X className="size-3" />
                      </button>
                    </Badge>
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx,.txt,.md"
                    className="sr-only"
                    tabIndex={-1}
                    aria-hidden="true"
                    onChange={(e) => {
                      setFile(e.target.files?.[0] || null);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
              <Field label="Onde procurar">
                <ScopeSelect value={projectId} onChange={setProjectId} />
              </Field>
            </div>
            <div className="flex justify-end">
              <Button
                variant="primary"
                icon={ScanSearch}
                busy={busy === "text"}
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
      </Card>

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
