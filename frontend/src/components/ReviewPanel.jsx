import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, X } from "lucide-react";
import { approveDocument, getExtraction, rerunPageOcr, suggestMetadata, updateMetadata, updatePage } from "../api";
import { MetadataCard, StructureCard, fromDraft, toDraft } from "./ReviewDetails";

const SOURCE_LABELS = {
  text: "Texto do PDF",
  ocr: "OCR",
  manual: "Editado à mão",
  none: "Sem texto",
};

function ReviewPage({ page, readOnly, busy, onSave, onToggleExcluded, onRerunOcr }) {
  const [draft, setDraft] = useState(page.text);
  const [dpi, setDpi] = useState(400);

  useEffect(() => setDraft(page.text), [page.text]);

  const dirty = draft !== page.text;
  const hasAlerts = page.alerts.length > 0;

  return (
    <article
      id={`review-page-${page.page}`}
      className={`scroll-mt-4 rounded-xl border bg-white dark:bg-stone-900 transition-opacity ${
        hasAlerts && !page.excluded ? "border-amber-300 dark:border-amber-700/60" : "border-stone-200 dark:border-stone-800"
      } ${page.excluded ? "opacity-50" : ""}`}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-stone-100 dark:border-stone-800 px-4 py-2.5">
        <span className="font-medium">Página {page.page}</span>
        <span className="text-xs text-stone-500 dark:text-stone-400">
          {SOURCE_LABELS[page.source]}
          {page.ocr_confidence != null && ` · confiança ${page.ocr_confidence.toFixed(0)}%`}
          {` · ${page.text.length} caracteres`}
        </span>
        {!readOnly && (
          <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-stone-600 dark:text-stone-400">
            <input
              type="checkbox"
              checked={page.excluded}
              disabled={busy}
              onChange={(e) => onToggleExcluded(page.page, e.target.checked)}
              className="accent-accent-500"
            />
            Não indexar esta página
          </label>
        )}
      </header>

      {hasAlerts && (
        <ul className="space-y-1 bg-amber-50 dark:bg-amber-950/30 px-4 py-2 text-sm text-amber-900 dark:text-amber-200">
          {page.alerts.map((alert) => (
            <li key={alert.code} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {alert.message}
            </li>
          ))}
        </ul>
      )}

      <textarea
        value={draft}
        readOnly={readOnly}
        rows={Math.min(14, Math.max(4, draft.split("\n").length, Math.ceil(draft.length / 95)))}
        placeholder={readOnly ? "" : "Nenhum texto extraído. Podes escrever aqui o texto da página."}
        onChange={(e) => setDraft(e.target.value)}
        className="block w-full resize-y bg-transparent px-4 py-3 font-mono text-[13px] leading-relaxed text-stone-800 dark:text-stone-200 outline-none placeholder:font-sans placeholder:text-stone-400 dark:placeholder:text-stone-500"
      />

      {!readOnly && (
        <footer className="flex flex-wrap items-center gap-2 border-t border-stone-100 dark:border-stone-800 px-4 py-2">
          {dirty && (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => onSave(page.page, draft)}
                className="rounded-md bg-stone-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
              >
                Guardar alterações
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setDraft(page.text)}
                className="rounded-md px-2 py-1.5 text-xs text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                Desfazer
              </button>
            </>
          )}
          <span className="ml-auto flex items-center gap-1.5 text-xs text-stone-600 dark:text-stone-400">
            <button
              type="button"
              disabled={busy}
              onClick={() => onRerunOcr(page.page, dpi)}
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-50"
            >
              <RotateCcw className="size-3.5" />
              Repetir OCR a
            </button>
            <select
              value={dpi}
              disabled={busy}
              onChange={(e) => setDpi(Number(e.target.value))}
              className="rounded border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 px-1 py-0.5"
            >
              {[200, 300, 400, 500].map((value) => (
                <option key={value} value={value}>
                  {value} dpi
                </option>
              ))}
            </select>
          </span>
        </footer>
      )}
    </article>
  );
}

export default function ReviewPanel({ documentId, onClose, onApproved }) {
  const [extraction, setExtraction] = useState(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState("A carregar…");
  const [onlyAlerts, setOnlyAlerts] = useState(false);
  const [metaDraft, setMetaDraft] = useState(null);

  useEffect(() => {
    getExtraction(documentId)
      .then((data) => {
        setExtraction(data);
        setMetaDraft(toDraft(data.metadata));
        setOnlyAlerts(data.document.alert_count > 0 && data.pages.length > 5);
      })
      .catch((err) => setError(err.message))
      .finally(() => setWorking(""));
  }, [documentId]);

  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape" && !working) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, working]);

  // syncMeta: a resposta traz uma ficha nova (guardada ou sugerida) que substitui o rascunho.
  async function run(label, action, { syncMeta = false } = {}) {
    setWorking(label);
    setError("");
    try {
      const data = await action();
      setExtraction(data);
      if (syncMeta) setMetaDraft(toDraft(data.metadata));
    } catch (err) {
      setError(err.message);
    } finally {
      setWorking("");
    }
  }

  async function handleApprove() {
    setWorking("A indexar…");
    setError("");
    try {
      if (metaDirty) await updateMetadata(documentId, fromDraft(metaDraft));
      const result = await approveDocument(documentId);
      onApproved(result.message);
    } catch (err) {
      setError(err.message);
      setWorking("");
    }
  }

  function jumpToPage(pageNumber) {
    setOnlyAlerts(false);
    requestAnimationFrame(() =>
      document.getElementById(`review-page-${pageNumber}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  }

  const busy = !!working;
  const metaDirty =
    !!extraction &&
    !!metaDraft &&
    JSON.stringify(fromDraft(metaDraft)) !== JSON.stringify(fromDraft(toDraft(extraction.metadata)));
  const doc = extraction?.document;
  const pages = extraction?.pages || [];
  const readOnly = doc?.status !== "pending_review";
  const visiblePages = onlyAlerts ? pages.filter((p) => p.alerts.length) : pages;
  const includedWithText = pages.filter((p) => !p.excluded && p.text.trim()).length;
  const pagesWithAlerts = pages.filter((p) => p.alerts.length && !p.excluded).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-stone-900/40 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="review-title"
    >
      <section className="animate-fade-up flex h-full w-full max-w-4xl flex-col bg-stone-50 dark:bg-stone-950 sm:h-auto sm:max-h-full sm:rounded-2xl sm:shadow-xl">
        <header className="flex items-start gap-3 border-b border-stone-200 dark:border-stone-800 px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-stone-500 dark:text-stone-400">
              {readOnly ? "Texto indexado" : "Rever antes de indexar"}
            </p>
            <h2 id="review-title" className="truncate text-lg font-semibold" title={doc?.title || doc?.filename}>
              {doc?.title || doc?.filename || "…"}
            </h2>
            {doc && (
              <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">
                {doc.title && <span className="font-mono text-xs">{doc.filename} · </span>}
                {doc.page_count} página{doc.page_count !== 1 && "s"}
                {pagesWithAlerts > 0 ? (
                  <span className="text-amber-700 dark:text-amber-400"> · {pagesWithAlerts} com alertas</span>
                ) : (
                  " · sem alertas"
                )}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Fechar"
            className="rounded-md p-1.5 text-stone-500 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-900 dark:hover:text-stone-100"
          >
            <X className="size-5" />
          </button>
        </header>

        {pages.some((p) => p.alerts.length) && (
          <div className="flex items-center gap-2 px-5 pt-3 text-sm">
            <label className="flex cursor-pointer items-center gap-1.5 text-stone-600 dark:text-stone-400">
              <input
                type="checkbox"
                checked={onlyAlerts}
                onChange={(e) => setOnlyAlerts(e.target.checked)}
                className="accent-accent-500"
              />
              Mostrar só páginas com alertas
            </label>
          </div>
        )}

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {!extraction && working && (
            <p className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
              <Loader2 className="size-4 animate-spin" />
              {working}
            </p>
          )}
          {extraction && metaDraft && (
            <>
              <MetadataCard
                metadata={extraction.metadata}
                draft={metaDraft}
                onDraftChange={setMetaDraft}
                dirty={metaDirty}
                readOnly={readOnly}
                busy={busy}
                suggesting={working === "A preencher a ficha…"}
                onSave={() =>
                  run("A guardar a ficha…", () => updateMetadata(documentId, fromDraft(metaDraft)), { syncMeta: true })
                }
                onSuggest={() =>
                  run(
                    "A preencher a ficha…",
                    async () => {
                      // Guarda primeiro o que foi escrito: a sugestão só preenche campos vazios no servidor.
                      if (metaDirty) await updateMetadata(documentId, fromDraft(metaDraft));
                      return suggestMetadata(documentId);
                    },
                    { syncMeta: true },
                  )
                }
              />
              <StructureCard sections={extraction.sections} references={extraction.references} onJumpToPage={jumpToPage} />
            </>
          )}
          {visiblePages.map((page) => (
            <ReviewPage
              key={page.page}
              page={page}
              readOnly={readOnly}
              busy={busy}
              onSave={(n, text) => run("A guardar…", () => updatePage(documentId, n, { text }))}
              onToggleExcluded={(n, excluded) => run("A guardar…", () => updatePage(documentId, n, { excluded }))}
              onRerunOcr={(n, dpi) => run(`A repetir o OCR da página ${n}…`, () => rerunPageOcr(documentId, n, dpi))}
            />
          ))}
          {extraction && visiblePages.length === 0 && (
            <p className="text-sm text-stone-500 dark:text-stone-400">Nenhuma página com alertas.</p>
          )}
        </div>

        {(error || (!readOnly && doc)) && (
          <footer className="flex flex-wrap items-center gap-3 border-t border-stone-200 dark:border-stone-800 px-5 py-3">
            {error ? (
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            ) : working && extraction ? (
              <p className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
                <Loader2 className="size-4 animate-spin" />
                {working}
              </p>
            ) : (
              <p className="text-sm text-stone-500 dark:text-stone-400">
                {includedWithText === 1 ? "1 página vai ser indexada." : `${includedWithText} páginas vão ser indexadas.`}
              </p>
            )}
            {!readOnly && doc && (
              <button
                type="button"
                onClick={handleApprove}
                disabled={busy || includedWithText === 0}
                className="ml-auto flex items-center gap-2 rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:bg-stone-300 dark:disabled:bg-stone-700"
              >
                <CheckCircle2 className="size-4" />
                Aprovar e indexar
              </button>
            )}
          </footer>
        )}
      </section>
    </div>
  );
}
