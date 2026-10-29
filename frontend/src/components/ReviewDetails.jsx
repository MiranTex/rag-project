import { useState } from "react";
import { ChevronRight, FileSearch, Loader2 } from "lucide-react";

// Listas editam-se como texto separado por ";" (nomes como "Silva, J." levam vírgula).
export function toDraft(metadata) {
  return {
    title: metadata.title || "",
    authors: (metadata.authors || []).join("; "),
    advisors: (metadata.advisors || []).join("; "),
    year: metadata.year ?? "",
    course: metadata.course || "",
    institution: metadata.institution || "",
    keywords: (metadata.keywords || []).join("; "),
    abstract: metadata.abstract || "",
  };
}

export function fromDraft(draft) {
  const list = (text) => text.split(";").map((item) => item.trim()).filter(Boolean);
  const year = Number.parseInt(draft.year, 10);
  return {
    title: draft.title,
    authors: list(draft.authors),
    advisors: list(draft.advisors),
    year: Number.isFinite(year) ? year : null,
    course: draft.course,
    institution: draft.institution,
    keywords: list(draft.keywords),
    abstract: draft.abstract,
  };
}

const input =
  "w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm outline-none transition-colors placeholder:text-stone-400 focus:border-stone-400 dark:border-stone-700 dark:bg-stone-900 dark:placeholder:text-stone-500 dark:focus:border-stone-500";

function Field({ label, hint, className = "", children }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 flex items-baseline gap-2 text-xs font-medium text-stone-600 dark:text-stone-400">
        {label}
        {hint && <span className="font-normal text-stone-400 dark:text-stone-500">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

function ReadOnlyValue({ label, value }) {
  return (
    <div>
      <dt className="text-xs font-medium text-stone-500 dark:text-stone-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-stone-800 dark:text-stone-200">{value || <span className="text-stone-400 dark:text-stone-500">—</span>}</dd>
    </div>
  );
}

export function MetadataCard({ metadata, draft, onDraftChange, dirty, readOnly, busy, suggesting, onSave, onSuggest }) {
  const set = (field) => (e) => onDraftChange({ ...draft, [field]: e.target.value });
  const empty = !metadata.title && !metadata.authors?.length && !metadata.year;

  return (
    <section className="rounded-xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
      <header className="flex flex-wrap items-center gap-2 border-b border-stone-100 px-4 py-2.5 dark:border-stone-800">
        <h3 className="font-medium">Ficha do trabalho</h3>
        {!readOnly && (
          <button
            type="button"
            onClick={onSuggest}
            disabled={busy}
            title="Pede ao modelo para preencher os campos vazios a partir da capa e do resumo"
            className="ml-auto flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-stone-600 hover:bg-stone-100 disabled:opacity-50 dark:text-stone-400 dark:hover:bg-stone-800"
          >
            {suggesting ? <Loader2 className="size-3.5 animate-spin" /> : <FileSearch className="size-3.5" />}
            Preencher campos vazios
          </button>
        )}
      </header>

      {!readOnly && empty && !metadata.auto_filled && (
        <p className="border-b border-stone-100 bg-stone-50 px-4 py-2 text-sm text-stone-600 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-400">
          O modelo não preencheu a ficha. Podes escrever os campos ou pedir de novo o preenchimento.
        </p>
      )}

      {readOnly ? (
        <dl className="grid gap-4 px-4 py-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <ReadOnlyValue label="Título" value={metadata.title} />
          </div>
          <ReadOnlyValue label="Autores" value={metadata.authors?.join("; ")} />
          <ReadOnlyValue label="Orientadores" value={metadata.advisors?.join("; ")} />
          <ReadOnlyValue label="Curso" value={metadata.course} />
          <ReadOnlyValue label="Instituição" value={metadata.institution} />
          <ReadOnlyValue label="Ano" value={metadata.year} />
          <ReadOnlyValue label="Palavras-chave" value={metadata.keywords?.join("; ")} />
          <div className="sm:col-span-2">
            <ReadOnlyValue label="Resumo" value={metadata.abstract} />
          </div>
        </dl>
      ) : (
        <div className="grid gap-3 px-4 py-3 sm:grid-cols-6">
          <Field label="Título" className="sm:col-span-6">
            <input className={input} value={draft.title} onChange={set("title")} placeholder="Não encontrado" />
          </Field>
          <Field label="Autores" hint="separados por ;" className="sm:col-span-3">
            <input className={input} value={draft.authors} onChange={set("authors")} />
          </Field>
          <Field label="Orientadores" hint="separados por ;" className="sm:col-span-3">
            <input className={input} value={draft.advisors} onChange={set("advisors")} />
          </Field>
          <Field label="Curso" className="sm:col-span-3">
            <input className={input} value={draft.course} onChange={set("course")} />
          </Field>
          <Field label="Instituição" className="sm:col-span-2">
            <input className={input} value={draft.institution} onChange={set("institution")} />
          </Field>
          <Field label="Ano" className="sm:col-span-1">
            <input className={input} value={draft.year} onChange={set("year")} inputMode="numeric" maxLength={4} />
          </Field>
          <Field label="Palavras-chave" hint="separadas por ;" className="sm:col-span-6">
            <input className={input} value={draft.keywords} onChange={set("keywords")} />
          </Field>
          <Field label="Resumo" className="sm:col-span-6">
            <textarea className={`${input} resize-y leading-relaxed`} rows={4} value={draft.abstract} onChange={set("abstract")} />
          </Field>
        </div>
      )}

      {!readOnly && dirty && (
        <footer className="flex items-center gap-2 border-t border-stone-100 px-4 py-2 dark:border-stone-800">
          <span className="text-xs text-stone-500 dark:text-stone-400">Alterações por guardar. Também são guardadas ao aprovar.</span>
          <button
            type="button"
            onClick={onSave}
            disabled={busy}
            className="ml-auto rounded-md bg-stone-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
          >
            Guardar ficha
          </button>
        </footer>
      )}
    </section>
  );
}

export function StructureCard({ sections, references, onJumpToPage }) {
  const [showReferences, setShowReferences] = useState(false);

  return (
    <section className="rounded-xl border border-stone-200 bg-white px-4 py-3 dark:border-stone-800 dark:bg-stone-900">
      <h3 className="font-medium">Estrutura</h3>
      {sections.length ? (
        <>
          <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
            Cada excerto fica marcado com a secção a que pertence. Se faltar uma secção, corrige o título na página.
          </p>
          <ol className="mt-2 flex flex-wrap gap-1.5">
            {sections.map((section, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => onJumpToPage(section.page)}
                  title={section.text}
                  className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 px-2.5 py-0.5 text-xs text-stone-700 hover:border-stone-300 hover:bg-stone-50 dark:border-stone-700 dark:text-stone-300 dark:hover:border-stone-600 dark:hover:bg-stone-800"
                >
                  {/* "Resumo" e "Abstract" têm a mesma etiqueta: aí mostra-se o título como está no documento. */}
                  {sections.filter((other) => other.label === section.label).length > 1 ? section.text : section.label}
                  <span className="text-stone-400 dark:text-stone-500">p. {section.page}</span>
                </button>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">
          Não foram detetadas secções. É normal em documentos que não são trabalhos académicos; os excertos ficam sem secção.
        </p>
      )}

      {references.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowReferences((v) => !v)}
            className="flex items-center gap-1 text-sm text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
          >
            {references.length} referência{references.length > 1 ? "s" : ""} na bibliografia
            <ChevronRight className={`size-3.5 transition-transform ${showReferences ? "rotate-90" : ""}`} />
          </button>
          {showReferences && (
            <ol className="animate-fade-up mt-2 max-h-64 list-decimal space-y-1 overflow-y-auto pl-6 text-xs text-stone-600 dark:text-stone-400">
              {references.map((reference, i) => (
                <li key={i}>{reference}</li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
