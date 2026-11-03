import { useEffect, useState } from "react";
import { Bell, BookmarkPlus, Pin, Save, Search, Trash2 } from "lucide-react";
import { research } from "../api";
import PageShell from "../components/PageShell";
import { Button, Empty, ErrorText, ExcerptCard, Section, Spinner, documentLabel, inputClass } from "../components/ui";
import { useResearch } from "../research/ResearchContext";

const EMPTY_FILTERS = { document_type: "", year_from: "", year_to: "", fields: {}, sections: [] };

// Só os filtros preenchidos seguem para a API (os anos vazios não podem ir como "").
function cleanFilters(filters) {
  const clean = {};
  if (filters.document_type) clean.document_type = filters.document_type;
  if (filters.year_from) clean.year_from = Number(filters.year_from);
  if (filters.year_to) clean.year_to = Number(filters.year_to);
  const fields = Object.fromEntries(Object.entries(filters.fields).filter(([, v]) => v));
  if (Object.keys(fields).length) clean.fields = fields;
  if (filters.sections.length) clean.sections = filters.sections;
  return clean;
}

function Filters({ facets, filters, onChange }) {
  if (!facets) return null;
  const set = (changes) => onChange({ ...filters, ...changes });
  return (
    <div className="grid gap-2 sm:grid-cols-4">
      <select className={inputClass} value={filters.document_type} onChange={(e) => set({ document_type: e.target.value })} aria-label="Tipo">
        <option value="">Todos os tipos</option>
        {facets.types.filter((t) => t.count > 0).map((t) => (
          <option key={t.key} value={t.key}>
            {t.label} ({t.count})
          </option>
        ))}
      </select>
      <input
        className={inputClass}
        type="number"
        placeholder={facets.years ? `Desde ${facets.years.min}` : "Desde (ano)"}
        value={filters.year_from}
        onChange={(e) => set({ year_from: e.target.value })}
        aria-label="Desde o ano"
      />
      <input
        className={inputClass}
        type="number"
        placeholder={facets.years ? `Até ${facets.years.max}` : "Até (ano)"}
        value={filters.year_to}
        onChange={(e) => set({ year_to: e.target.value })}
        aria-label="Até ao ano"
      />
      <select
        className={inputClass}
        value={filters.sections[0] || ""}
        onChange={(e) => set({ sections: e.target.value ? [e.target.value] : [] })}
        aria-label="Secção"
      >
        <option value="">Qualquer secção</option>
        {facets.sections.map((s) => (
          <option key={s.key} value={s.key}>
            {s.label}
          </option>
        ))}
      </select>
      {facets.fields.map((field) => (
        <select
          key={field.key}
          className={inputClass}
          value={filters.fields[field.key] || ""}
          onChange={(e) => set({ fields: { ...filters.fields, [field.key]: e.target.value } })}
          aria-label={field.label}
        >
          <option value="">{field.label}: todos</option>
          {field.values.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      ))}
    </div>
  );
}

function SavedSearches({ searches, onRun, onDelete, onOpenNew }) {
  if (!searches.length) return null;
  return (
    <Section title="Pesquisas guardadas" description="Avisam quando entram documentos novos que correspondem.">
      <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
        {searches.map((s) => (
          <li key={s.search_id} className="flex items-center gap-2 px-3 py-2 text-sm">
            <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => onRun(s)}>
              {s.name}
              <span className="ml-2 text-stone-500 dark:text-stone-400">“{s.query}”</span>
            </button>
            {s.new_count > 0 && (
              <Button variant="ghost" icon={Bell} onClick={() => onOpenNew(s)} className="text-accent-700 dark:text-accent-400">
                {s.new_count} novo{s.new_count > 1 ? "s" : ""}
              </Button>
            )}
            <Button variant="ghost" icon={Trash2} aria-label="Apagar pesquisa" onClick={() => onDelete(s)} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

export default function SearchPage({ onOpenSidebar }) {
  const { openReader, saveItem, pinDocument, notify } = useResearch();
  const [facets, setFacets] = useState(null);
  const [queryText, setQueryText] = useState("");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [results, setResults] = useState(null);
  const [searches, setSearches] = useState([]);
  const [newDocs, setNewDocs] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadSearches = () => research.searches().then(setSearches).catch(() => {});
  useEffect(() => {
    research.facets().then(setFacets).catch((err) => setError(err.message));
    loadSearches();
  }, []);

  async function run(text = queryText, activeFilters = filters) {
    if (text.trim().length < 2) return;
    setBusy(true);
    setError("");
    setNewDocs(null);
    try {
      setResults(await research.search({ query: text.trim(), filters: cleanFilters(activeFilters), top_k: 20 }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    try {
      await research.saveSearch({ name: queryText.trim().slice(0, 80), query: queryText.trim(), filters: cleanFilters(filters) });
      notify("Pesquisa guardada. Vais ver aqui quando entrarem documentos novos.");
      loadSearches();
    } catch (err) {
      setError(err.message);
    }
  }

  async function openNew(search) {
    try {
      setNewDocs({ search, documents: await research.newForSearch(search.search_id) });
      await research.markSearchSeen(search.search_id);
      loadSearches();
    } catch (err) {
      setError(err.message);
    }
  }

  // Resultados agrupados por documento, pela ordem do melhor excerto de cada um.
  const groups = [];
  for (const hit of results || []) {
    let group = groups.find((g) => g.document_id === hit.document_id);
    if (!group) groups.push((group = { document_id: hit.document_id, doc: hit, hits: [] }));
    group.hits.push(hit);
  }

  return (
    <PageShell
      title="Pesquisa"
      description="Pesquisa direta na base, sem chat: encontra os excertos mais relevantes, com o documento e a página."
      onOpenSidebar={onOpenSidebar}
    >
      <form
        className="mb-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <input
          className={inputClass}
          placeholder="O que procuras? (ex.: métodos de recomendação em bibliotecas)"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          autoFocus
        />
        <Button type="submit" variant="primary" icon={Search} busy={busy}>
          Pesquisar
        </Button>
      </form>
      <div className="mb-6">
        <Filters facets={facets} filters={filters} onChange={setFilters} />
      </div>
      <ErrorText>{error}</ErrorText>

      <SavedSearches
        searches={searches}
        onRun={(s) => {
          const restored = { ...EMPTY_FILTERS, ...s.filters, fields: s.filters.fields || {}, sections: s.filters.sections || [] };
          setQueryText(s.query);
          setFilters(restored);
          run(s.query, restored);
        }}
        onDelete={(s) => research.deleteSearch(s.search_id).then(loadSearches, (err) => setError(err.message))}
        onOpenNew={openNew}
      />

      {newDocs && (
        <Section title={`Novos em “${newDocs.search.name}”`}>
          <ul className="space-y-2">
            {newDocs.documents.map((doc) => (
              <li key={doc.document_id} className="flex items-center gap-2 rounded-lg border border-stone-200 p-3 text-sm dark:border-stone-800">
                <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => openReader({ document_id: doc.document_id, page: 1 })}>
                  {documentLabel(doc)} {doc.year ? `(${doc.year})` : ""}
                </button>
                <Button variant="ghost" icon={Pin} onClick={() => pinDocument(doc.document_id)}>
                  Fixar
                </Button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {busy && <Spinner label="A pesquisar…" />}
      {results && !busy && (
        <Section
          title={`${groups.length} documento${groups.length === 1 ? "" : "s"}, ${results.length} excerto${results.length === 1 ? "" : "s"}`}
          actions={
            <Button variant="ghost" icon={Save} onClick={save}>
              Guardar pesquisa
            </Button>
          }
        >
          {groups.length === 0 ? (
            <Empty>Nada encontrado. Experimenta outras palavras ou menos filtros.</Empty>
          ) : (
            <div className="space-y-5">
              {groups.map((group) => (
                <div key={group.document_id}>
                  <div className="mb-2 flex items-center gap-2">
                    <h3 className="min-w-0 flex-1 truncate text-sm font-medium">
                      {documentLabel(group.doc)} {group.doc.year ? `(${group.doc.year})` : ""}
                    </h3>
                    <Button variant="ghost" icon={Pin} onClick={() => pinDocument(group.document_id)}>
                      Fixar no projeto
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {group.hits.map((hit) => (
                      <ExcerptCard
                        key={`${hit.page}-${hit.text.slice(0, 20)}`}
                        excerpt={hit}
                        onOpen={() => openReader(hit)}
                        actions={
                          <Button
                            variant="ghost"
                            icon={BookmarkPlus}
                            onClick={() =>
                              saveItem({
                                kind: "excerpt",
                                title: documentLabel(hit),
                                text: hit.text,
                                source: { document_id: hit.document_id, filename: hit.filename, page: hit.page, title: hit.title },
                              })
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
          )}
        </Section>
      )}
    </PageShell>
  );
}
