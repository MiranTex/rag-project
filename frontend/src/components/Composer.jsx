import { useEffect, useRef } from "react";
import { ArrowUp, ChevronDown, FileText, Layers, Square, UserCog } from "lucide-react";

const MAX_TEXTAREA_HEIGHT = 200;

function PillSelect({ icon: Icon, value, onChange, title, children }) {
  return (
    <label
      title={title}
      className="relative inline-flex max-w-full items-center gap-1.5 rounded-full border border-stone-200 dark:border-stone-700 py-1 pl-2.5 pr-7 text-xs text-stone-600 dark:text-stone-400 hover:border-stone-300 dark:hover:border-stone-600 hover:bg-stone-50 dark:hover:bg-stone-700"
    >
      <Icon className="size-3.5 shrink-0" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-40 cursor-pointer appearance-none truncate bg-transparent outline-none sm:max-w-56"
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 size-3.5" />
    </label>
  );
}

function ModeSwitch({ mode, onModeChange }) {
  const options = [
    { value: "agent", label: "Agente", title: "Pesquisa, lê, calcula e exporta ficheiros" },
    { value: "rag", label: "Pesquisa direta", title: "Uma pesquisa e uma resposta, com detalhes do ranking" },
  ];
  return (
    <div className="inline-flex rounded-full bg-stone-100 dark:bg-stone-900 p-0.5 text-xs" role="group" aria-label="Modo">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          title={option.title}
          onClick={() => onModeChange(option.value)}
          className={`rounded-full px-2.5 py-1 transition-colors ${
            mode === option.value ? "bg-white dark:bg-stone-700 font-medium text-stone-900 dark:text-stone-100 shadow-sm" : "text-stone-500 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default function Composer({
  question,
  onQuestionChange,
  onAsk,
  onStop,
  asking,
  mode,
  onModeChange,
  documents,
  selectedDocument,
  onSelectDocument,
  canSelectDocument,
  profiles,
  profile,
  onProfileChange,
  multiQuery,
  onMultiQueryChange,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [question]);

  useEffect(() => {
    if (!asking) textareaRef.current?.focus();
  }, [asking]);

  const canSend = question.trim().length > 0 && !asking;

  function handleKeyDown(event) {
    if (event.key === "Escape" && asking) {
      event.preventDefault();
      onStop();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onAsk();
    }
  }

  return (
    <div className="rounded-2xl border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-sm dark:shadow-none transition-colors focus-within:border-stone-400 dark:focus-within:border-stone-600">
      <textarea
        ref={textareaRef}
        rows={1}
        value={question}
        onChange={(e) => onQuestionChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Escreve uma pergunta"
        className="block w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-[15px] leading-relaxed outline-none placeholder:text-stone-400 dark:placeholder:text-stone-500"
      />
      <div className="flex items-end gap-2 px-3 pb-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <ModeSwitch mode={mode} onModeChange={onModeChange} />

          {canSelectDocument && (
            <PillSelect icon={FileText} value={selectedDocument} onChange={onSelectDocument} title="Onde pesquisar">
              <option value="">Todos os documentos</option>
              {documents.map((doc) => (
                <option key={doc.document_id} value={doc.document_id}>
                  {doc.filename}
                </option>
              ))}
            </PillSelect>
          )}

          {mode === "agent" && profiles.length > 1 && (
            <PillSelect
              icon={UserCog}
              value={profile}
              onChange={onProfileChange}
              title={profiles.find((p) => p.name === profile)?.description}
            >
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </PillSelect>
          )}

          {mode === "rag" && (
            <button
              type="button"
              onClick={() => onMultiQueryChange(!multiQuery)}
              aria-pressed={multiQuery}
              title="Reescreve a pergunta de várias formas antes de pesquisar"
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                multiQuery
                  ? "border-accent-500 bg-accent-50 dark:bg-accent-500/15 text-accent-700 dark:text-accent-400"
                  : "border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-400 hover:border-stone-300 dark:hover:border-stone-600 hover:bg-stone-50 dark:hover:bg-stone-700"
              }`}
            >
              <Layers className="size-3.5" />
              Várias formulações
            </button>
          )}
        </div>

        {asking ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Parar resposta"
            title="Parar (Esc)"
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-stone-900 text-white transition-colors hover:bg-stone-700 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
          >
            <Square className="size-3" fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            onClick={onAsk}
            disabled={!canSend}
            aria-label="Enviar"
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-500 text-white transition-colors hover:bg-accent-600 disabled:bg-stone-200 dark:disabled:bg-stone-700 disabled:text-stone-400 dark:disabled:text-stone-500"
          >
            <ArrowUp className="size-4" strokeWidth={2.5} />
          </button>
        )}
      </div>
    </div>
  );
}
