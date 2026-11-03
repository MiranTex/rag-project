import { FileText, Loader2 } from "lucide-react";

// Peças de interface partilhadas pelas páginas da área de pesquisa.

export const inputClass =
  "w-full rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 px-3 py-1.5 text-sm outline-none focus:border-stone-500 disabled:opacity-60";

const buttonStyles = {
  primary: "bg-accent-500 text-white hover:bg-accent-600 disabled:bg-stone-300 dark:disabled:bg-stone-700",
  secondary:
    "border border-stone-300 text-stone-700 hover:bg-stone-100 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800 disabled:opacity-50",
  ghost: "text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800 disabled:opacity-50",
  danger: "text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40 disabled:opacity-50",
};

export function Button({ variant = "secondary", busy = false, icon: Icon, children, className = "", ...props }) {
  return (
    <button
      type="button"
      disabled={busy || props.disabled}
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ${buttonStyles[variant]} ${className}`}
    >
      {busy ? <Loader2 className="size-4 animate-spin" /> : Icon && <Icon className="size-4" />}
      {children}
    </button>
  );
}

export function Spinner({ label }) {
  return (
    <p className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
      <Loader2 className="size-4 animate-spin" />
      {label}
    </p>
  );
}

export function ErrorText({ children }) {
  if (!children) return null;
  return <p className="text-sm text-red-700 dark:text-red-300">{children}</p>;
}

export function Empty({ children }) {
  return <p className="rounded-xl border border-dashed border-stone-300 p-6 text-center text-sm text-stone-500 dark:border-stone-700 dark:text-stone-400">{children}</p>;
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="mb-5 flex gap-1 overflow-x-auto border-b border-stone-200 dark:border-stone-800" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={value === tab.value}
          onClick={() => onChange(tab.value)}
          className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm ${
            value === tab.value
              ? "border-accent-500 font-medium text-stone-900 dark:text-stone-100"
              : "border-transparent text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function Section({ title, description, actions, children }) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-medium text-stone-800 dark:text-stone-200">{title}</h2>
          {description && <p className="text-sm text-stone-500 dark:text-stone-400">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export const documentLabel = (doc) => doc.title || (doc.filename || "").replace(/\.pdf$/i, "");

// Excerto de um documento com a página; clicar abre o leitor.
export function ExcerptCard({ excerpt, onOpen, actions, children }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-3 text-sm dark:border-stone-800 dark:bg-stone-900">
      <button
        type="button"
        onClick={onOpen}
        className="mb-1 flex max-w-full items-center gap-1.5 text-left text-xs font-medium text-accent-700 hover:underline dark:text-accent-400"
      >
        <FileText className="size-3.5 shrink-0" />
        <span className="truncate">
          {documentLabel(excerpt)}
          {excerpt.year ? ` (${excerpt.year})` : ""} · p. {excerpt.page}
        </span>
      </button>
      <p className="line-clamp-5 whitespace-pre-line text-stone-700 dark:text-stone-300">{excerpt.text}</p>
      {children}
      {actions && <div className="mt-2 flex flex-wrap gap-1">{actions}</div>}
    </div>
  );
}
