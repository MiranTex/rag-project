import { Menu } from "lucide-react";

// Moldura das páginas que não são o chat: cabeçalho com o título e conteúdo com scroll próprio.
export default function PageShell({ title, description, onOpenSidebar, actions, children }) {
  return (
    <main className="flex h-full min-w-0 flex-1 flex-col bg-white dark:bg-stone-900">
      <header className="flex h-14 shrink-0 items-center gap-2 px-3 md:px-5">
        <button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Abrir menu"
          className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 md:hidden"
        >
          <Menu className="size-5" />
        </button>
        <h1 className="min-w-0 truncate font-semibold tracking-tight">{title}</h1>
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 pb-10 pt-2">
          {description && <p className="mb-5 text-sm text-stone-500 dark:text-stone-400">{description}</p>}
          {children}
        </div>
      </div>
    </main>
  );
}
