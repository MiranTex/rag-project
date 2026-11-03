import { useEffect, useState } from "react";
import { AlertTriangle, BookmarkPlus, Copy, FileDown, ListTree, PenLine } from "lucide-react";
import { research } from "../../api";
import Markdown from "../../components/Markdown";
import { Button, Empty, ErrorText, ExcerptCard, Section, Spinner, Tabs, inputClass } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";

const TABS = [
  { value: "skeleton", label: "Esqueleto" },
  { value: "state", label: "Estado da arte" },
  { value: "bibliography", label: "Bibliografia" },
];

function ExportButtons({ title, markdown, projectId, canSave }) {
  const { notify, saveItem } = useResearch();
  const [error, setError] = useState("");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        icon={FileDown}
        onClick={() => research.export({ title, markdown, format: "docx" }).then((r) => notify(`Exportado: ${r.name} (em Ficheiros)`), (err) => setError(err.message))}
      >
        Word
      </Button>
      {canSave && (
        <Button
          icon={BookmarkPlus}
          onClick={() =>
            research
              .addItem(projectId, { kind: "draft", title, text: markdown })
              .then(() => notify("Guardado no caderno do projeto."), (err) => setError(err.message))
          }
        >
          Guardar no caderno
        </Button>
      )}
      {!canSave && (
        <Button icon={BookmarkPlus} onClick={() => saveItem({ kind: "draft", title, text: markdown })}>
          Guardar noutro projeto
        </Button>
      )}
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

function SkeletonTab({ detail, canSave }) {
  const { openReader } = useResearch();
  const [workTypes, setWorkTypes] = useState([]);
  const [topic, setTopic] = useState(detail.project.question || detail.project.title);
  const [workType, setWorkType] = useState(detail.project.work_type);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    research.workTypes().then(setWorkTypes).catch(() => {});
  }, []);

  async function generate() {
    setBusy(true);
    setError("");
    try {
      setResult(
        await research.skeleton({
          topic: topic.trim(),
          work_type: workType,
          project_id: detail.documents.length ? detail.project.project_id : null,
        }),
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="mb-3 text-sm text-stone-500 dark:text-stone-400">
        O índice do trabalho com as secções do tipo escolhido. Em cada secção: perguntas a responder, o que ler (dos documentos do projeto) e
        exemplos de como outros trabalhos da base escreveram essa secção.
      </p>
      <div className="mb-6 flex flex-wrap gap-2">
        <input className={`${inputClass} min-w-64 flex-1`} placeholder="Tema do trabalho" value={topic} onChange={(e) => setTopic(e.target.value)} />
        <select className={`${inputClass} w-auto`} value={workType} onChange={(e) => setWorkType(e.target.value)} aria-label="Tipo de trabalho">
          <option value="">Tipo por defeito</option>
          {workTypes.map((t) => (
            <option key={t.key} value={t.key}>
              {t.label}
            </option>
          ))}
        </select>
        <Button variant="primary" icon={ListTree} busy={busy} disabled={topic.trim().length < 3} onClick={generate}>
          Gerar esqueleto
        </Button>
      </div>
      <ErrorText>{error}</ErrorText>
      {busy && <Spinner label="A preparar o esqueleto…" />}
      {result && !busy && (
        <>
          <div className="mb-4">
            <ExportButtons title={`Esqueleto - ${result.topic}`.slice(0, 120)} markdown={result.markdown} projectId={detail.project.project_id} canSave={canSave} />
          </div>
          <ol className="space-y-6">
            {result.sections.map((section, i) => (
              <li key={section.key}>
                <h3 className="font-semibold">
                  {i + 1}. {section.label}
                </h3>
                {section.questions.length > 0 && (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-stone-700 dark:text-stone-300">
                    {section.questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                )}
                {section.relevant.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-sm text-accent-700 dark:text-accent-400">Para ler ({section.relevant.length})</summary>
                    <div className="mt-2 space-y-2">
                      {section.relevant.map((e, j) => (
                        <ExcerptCard key={j} excerpt={e} onOpen={() => openReader(e)} />
                      ))}
                    </div>
                  </details>
                )}
                {section.examples.length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-sm text-accent-700 dark:text-accent-400">Como outros escreveram esta secção</summary>
                    <div className="mt-2 space-y-2">
                      {section.examples.map((e, j) => (
                        <ExcerptCard key={j} excerpt={e} onOpen={() => openReader(e)} />
                      ))}
                    </div>
                  </details>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  );
}

function StateOfArtTab({ detail, canSave }) {
  const { openReader } = useResearch();
  const [topic, setTopic] = useState(detail.project.question || "");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!detail.documents.length) return <Empty>Fixa documentos no projeto: o estado da arte é escrito só a partir deles.</Empty>;

  async function generate() {
    setBusy(true);
    setError("");
    try {
      setResult(await research.stateOfArt(detail.project.project_id, { topic: topic.trim() }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const markdown = result
    ? `${result.markdown}\n\n## Fontes\n\n${result.sources.map((s) => `[${s.n}] ${s.title || s.filename}, p. ${s.page}`).join("\n\n")}\n\n## Referências\n\n${result.bibliography.join("\n\n")}`
    : "";

  return (
    <>
      <p className="mb-3 text-sm text-stone-500 dark:text-stone-400">
        Um rascunho escrito só com o que está nos documentos do projeto. Cada frase cita o excerto em que se apoia ([n]); as que não citam ficam
        assinaladas para reveres.
      </p>
      <div className="mb-6 flex flex-wrap gap-2">
        <input className={`${inputClass} min-w-64 flex-1`} placeholder="Foco (por defeito, a pergunta de investigação)" value={topic} onChange={(e) => setTopic(e.target.value)} />
        <Button variant="primary" icon={PenLine} busy={busy} onClick={generate}>
          Escrever rascunho
        </Button>
      </div>
      <ErrorText>{error}</ErrorText>
      {busy && <Spinner label="A escrever (pode demorar um pouco)…" />}
      {result && !busy && (
        <>
          <div className="mb-4">
            <ExportButtons title="Estado da arte" markdown={markdown} projectId={detail.project.project_id} canSave={canSave} />
          </div>
          {(result.unsupported.length > 0 || result.invalid_citations.length > 0) && (
            <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/30">
              <p className="mb-1 flex items-center gap-2 font-medium">
                <AlertTriangle className="size-4 text-amber-600" />
                Rever antes de usar
              </p>
              {result.unsupported.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-5">
                  {result.unsupported.map((s) => (
                    <li key={s}>Sem citação: “{s}”</li>
                  ))}
                </ul>
              )}
              {result.invalid_citations.length > 0 && <p>Citações a excertos que não existem: {result.invalid_citations.map((n) => `[${n}]`).join(", ")}</p>}
            </div>
          )}
          <div className="rounded-xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900">
            <Markdown>{result.markdown}</Markdown>
          </div>
          <Section title="Excertos citados">
            <div className="space-y-2">
              {result.sources.map((s) => (
                <ExcerptCard key={s.n} excerpt={s} onOpen={() => openReader(s)}>
                  <span className="text-xs font-medium text-stone-500">[{s.n}]</span>
                </ExcerptCard>
              ))}
            </div>
          </Section>
        </>
      )}
    </>
  );
}

function BibliographyTab({ detail }) {
  const { notify } = useResearch();
  const [style, setStyle] = useState("apa");
  const [references, setReferences] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    research.bibliography(detail.project.project_id, style).then((r) => setReferences(r.references), (err) => setError(err.message));
  }, [detail.project.project_id, style, detail.documents.length]);

  const text = (references || []).join("\n\n");
  return (
    <>
      <p className="mb-3 text-sm text-stone-500 dark:text-stone-400">
        Referências dos documentos do projeto, geradas da ficha de cada um. Confirma os dados antes de entregar (editora, local, etc.).
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <select className={`${inputClass} w-auto`} value={style} onChange={(e) => setStyle(e.target.value)} aria-label="Norma">
          <option value="apa">APA 7</option>
          <option value="iso690">NP 405 / ISO 690</option>
          <option value="bibtex">BibTeX</option>
        </select>
        <Button
          icon={Copy}
          disabled={!references?.length}
          onClick={() => navigator.clipboard.writeText(text).then(() => notify("Bibliografia copiada."), () => setError("Não foi possível copiar."))}
        >
          Copiar
        </Button>
        {style !== "bibtex" && <ExportButtons title="Bibliografia" markdown={text} projectId={detail.project.project_id} canSave={detail.my_role !== "viewer"} />}
      </div>
      <ErrorText>{error}</ErrorText>
      {references && references.length === 0 && <Empty>Fixa documentos no projeto para gerar a bibliografia.</Empty>}
      {references && references.length > 0 && (
        <div className={`space-y-3 rounded-xl border border-stone-200 bg-white p-5 text-sm dark:border-stone-800 dark:bg-stone-900 ${style === "bibtex" ? "font-mono text-xs whitespace-pre" : ""}`}>
          {references.map((r) => (
            <p key={r} className={style === "bibtex" ? "" : "pl-6 -indent-6"}>
              {r}
            </p>
          ))}
        </div>
      )}
    </>
  );
}

export default function Writing({ detail }) {
  const [tab, setTab] = useState("skeleton");
  const canSave = detail.my_role !== "viewer";
  return (
    <>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {tab === "skeleton" && <SkeletonTab detail={detail} canSave={canSave} />}
      {tab === "state" && <StateOfArtTab detail={detail} canSave={canSave} />}
      {tab === "bibliography" && <BibliographyTab detail={detail} />}
    </>
  );
}
