import { useEffect, useState } from "react";
import { Bell, Bookmark, BookmarkPlus, Pin, Save, Search, Trash2 } from "lucide-react";
import { research } from "../api";
import PageShell from "../components/PageShell";
import { Badge, Button, EmptyState, ErrorText, ExcerptCard, Field, IconButton, ListCard, Modal, Section, Spinner, documentLabel, inputClass, useConfirm } from "../components/ui";
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
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Field label="Tipo">
        <select className={inputClass} value={filters.document_type} onChange={(e) => set({ document_type: e.target.value })}>
          <option value="">Todos os tipos</option>
          {facets.types.filter((t) => t.count > 0).map((t) => (
            <option key={t.key} value={t.key}>
              {t.label} ({t.count})
            </option>
          ))}
        </select>
      </Field>
      <Field label="Desde o ano">
        <input
          className={inputClass}
          type="number"
          placeholder={facets.years ? String(facets.years.min) : ""}
          value={filters.year_from}
          onChange={(e) => set({ year_from: e.target.value })}
        />
      </Field>
      <Field label="Até ao ano">
        <input
          className={inputClass}
          type="number"
          placeholder={facets.years ? String(facets.years.max) : ""}
          value={filters.year_to}
          onChange={(e) => set({ year_to: e.target.value })}
        />
      </Field>
      <Field label="Secção">
        <select className={inputClass} value={filters.sections[0] || ""} onChange={(e) => set({ sections: e.target.value ? [e.target.value] : [] })}>
          <option value="">Qualquer secção</option>
          {facets.sections.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
      </Field>
      {facets.fields.map((field) => (
        <Field key={field.key} label={field.label}>
          <select
            className={inputClass}
            value={filters.fields[field.key] || ""}
            onChange={(e) => set({ fields: { ...filters.fields, [field.key]: e.target.value } })}
          >
            <option value="">Todos</option>
            {field.values.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
      ))}
    </div>
  );
}

// Pesquisas guardadas numa janela, para não empurrarem os resultados para baixo.
function SavedSearchesModal({ searches, onRun, onDelete, onOpenNew, onClose }) {
  return (
    <Modal
      title="Pesquisas guardadas"
      description="Avisam quando entram documentos novos que correspondem. Clica numa para a voltar a correr."
      onClose={onClose}
    >
      {searches.length === 0 ? (
        <EmptyState icon={Bookmark} title="Nenhuma pesquisa guardada">
          Depois de pesquisar, usa “Guardar pesquisa” por cima dos resultados.
        </EmptyState>
      ) : (
        <ListCard>
          {searches.map((s) => (
            <li key={s.search_id} className="flex items-center gap-2 py-1.5 pl-3 pr-1.5 text-sm">
              <button
                type="button"
                className="min-w-0 flex-1 rounded-md py-1 text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50"
                onClick={() => onRun(s)}
              >
                <span className="block truncate font-medium text-stone-800 dark:text-stone-200">{s.name}</span>
                <span className="block truncate text-xs text-stone-500 dark:text-stone-400">“{s.query}”</span>
              </button>
              {s.new_count > 0 && (
                <Button variant="ghost" size="sm" icon={Bell} onClick={() => onOpenNew(s)} className="text-accent-700 dark:text-accent-400">
                  {s.new_count} novo{s.new_count > 1 ? "s" : ""}
                </Button>
              )}
              <IconButton icon={Trash2} label={`Apagar a pesquisa “${s.name}”`} variant="danger" onClick={() => onDelete(s)} />
            </li>
          ))}
        </ListCard>
      )}
    </Modal>
  );
}

export default function SearchPage({ onOpenSidebar }) {
  const { openReader, saveItem, pinDocument, notify } = useResearch();
  const confirm = useConfirm();
  const [showSaved, setShowSaved] = useState(false);
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
    setShowSaved(false);
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

  const newTotal = searches.reduce((sum, s) => sum + (s.new_count || 0), 0);

  async function deleteSearch(search) {
    const ok = await confirm({ title: "Apagar pesquisa guardada?", message: `“${search.name}” deixa de avisar quando entram documentos novos.` });
    if (ok) research.deleteSearch(search.search_id).then(loadSearches, (err) => setError(err.message));
  }

  return (
    <PageShell
      title="Pesquisa"
      subtitle="Pesquisa direta na base, sem chat: encontra os excertos mais relevantes, com o documento e a página."
      actions={
        <Button icon={Bookmark} onClick={() => setShowSaved(true)}>
          Pesquisas guardadas
          {newTotal > 0 ? (
            <Badge tone="accent" title={`${newTotal} documento${newTotal > 1 ? "s" : ""} novo${newTotal > 1 ? "s" : ""}`}>
              {newTotal}
            </Badge>
          ) : (
            searches.length > 0 && <span className="tabular-nums text-stone-500 dark:text-stone-400">{searches.length}</span>
          )}
        </Button>
      }
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
          type="search"
          aria-label="O que procuras?"
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

      {showSaved && (
        <SavedSearchesModal
          searches={searches}
          onRun={(s) => {
            const restored = { ...EMPTY_FILTERS, ...s.filters, fields: s.filters.fields || {}, sections: s.filters.sections || [] };
            setShowSaved(false);
            setQueryText(s.query);
            setFilters(restored);
            run(s.query, restored);
          }}
          onDelete={deleteSearch}
          onOpenNew={openNew}
          onClose={() => setShowSaved(false)}
        />
      )}

      {newDocs && (
        <Section
          title={`Novos em “${newDocs.search.name}”`}
          actions={
            <Button variant="ghost" size="sm" onClick={() => setNewDocs(null)}>
              Fechar
            </Button>
          }
        >
          <ListCard>
            {newDocs.documents.map((doc) => (
              <li key={doc.document_id} className="flex items-center gap-2 py-2 pl-4 pr-2 text-sm">
                <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => openReader({ document_id: doc.document_id, page: 1 })}>
                  {documentLabel(doc)} {doc.year ? `(${doc.year})` : ""}
                </button>
                <Button variant="ghost" icon={Pin} onClick={() => pinDocument(doc.document_id)}>
                  Fixar
                </Button>
              </li>
            ))}
          </ListCard>
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
            <EmptyState icon={Search} title="Nada encontrado">Experimenta outras palavras ou menos filtros.</EmptyState>
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
