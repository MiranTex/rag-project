import { Link } from "react-router-dom";
import { ChevronLeft, Menu } from "lucide-react";

const WIDTHS = { default: "max-w-3xl", wide: "max-w-5xl", full: "max-w-7xl" };

// Moldura das páginas que não são o chat. O cabeçalho tem a hierarquia da página: de onde se veio (back), o
// título, uma linha de contexto (subtitle/meta) e as ações principais; `tabs` fica colado ao fundo do cabeçalho.
export default function PageShell({ title, subtitle, description, meta, back, onOpenSidebar, actions, tabs, width = "default", children }) {
  const widthClass = WIDTHS[width] || WIDTHS.default;
  return (
    <main className="flex h-full min-w-0 flex-1 flex-col bg-white dark:bg-stone-900">
      <header className="shrink-0 border-b border-stone-200 dark:border-stone-800">
        <div className={`mx-auto flex ${widthClass} flex-wrap items-start gap-x-2 gap-y-2 px-4 pt-3 ${tabs ? "pb-1" : "pb-3"}`}>
          <button
            type="button"
            onClick={onOpenSidebar}
            aria-label="Abrir menu"
            className="-ml-1 mt-0.5 rounded-md p-1.5 text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800 md:hidden"
          >
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 flex-1 basis-60">
            {back && (
              <Link
                to={back.to}
                className="mb-0.5 inline-flex items-center gap-0.5 text-xs font-medium text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
              >
                <ChevronLeft className="size-3.5" />
                {back.label}
              </Link>
            )}
            <h1 className="line-clamp-2 text-lg font-semibold leading-snug tracking-tight">{title}</h1>
            {subtitle && <p className="line-clamp-2 text-sm text-stone-600 dark:text-stone-400">{subtitle}</p>}
            {meta && <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500 dark:text-stone-400">{meta}</div>}
          </div>
          {/* No telemóvel as ações descem para baixo do título, em vez de o esmagarem. */}
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2 max-sm:w-full max-sm:pl-9">{actions}</div>}
        </div>
        {tabs && <div className={`mx-auto ${widthClass} px-3`}>{tabs}</div>}
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className={`mx-auto ${widthClass} px-4 pb-12 pt-5`}>
          {description && <p className="mb-5 text-sm text-stone-500 dark:text-stone-400">{description}</p>}
          {children}
        </div>
      </div>
    </main>
  );
}
