import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, FileText, Loader2, MoreHorizontal, X } from "lucide-react";

// Peças de interface partilhadas por todas as páginas. Uma só forma de fazer cada coisa: campos com etiqueta,
// janelas, gavetas, menus, etiquetas de estado e a confirmação de ações que não se desfazem.

// ---------------------------------------------------------------- utilitários

export function slug(text) {
  return (
    text
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "seccao"
  );
}

// Chave nova (para uma secção) que não colide com as que já existem.
export function uniqueKey(title, existing) {
  const base = slug(title);
  let key = base;
  for (let n = 2; existing.some((s) => s.key === key); n += 1) key = `${base}-${n}`;
  return key;
}

export const ROLE_LABELS = { owner: "Dono", editor: "Edita", viewer: "Lê e comenta" };

export const documentLabel = (doc) => doc.title || (doc.filename || "").replace(/\.pdf$/i, "");

const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50 focus-visible:ring-offset-1 dark:focus-visible:ring-offset-stone-900";

// ---------------------------------------------------------------- campos

// Sem largura: para listas de escolha e campos que devem ter a largura do conteúdo (w-auto, w-24…). O inputClass
// ocupa a linha toda; juntar-lhe w-auto não funciona (as duas classes chocam e ganha w-full).
export const controlBase =
  "rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm outline-none transition-colors placeholder:text-stone-400 focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 disabled:opacity-60 dark:border-stone-700 dark:bg-stone-900 dark:placeholder:text-stone-500";

export const inputClass = `${controlBase} w-full`;

// Etiqueta sempre visível (o placeholder não chega), com ajuda opcional por baixo.
export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`block text-sm ${className}`}>
      <span className="mb-1 block font-medium text-stone-700 dark:text-stone-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-stone-500 dark:text-stone-400">{hint}</span>}
    </label>
  );
}

// ---------------------------------------------------------------- botões

const buttonStyles = {
  primary: "bg-accent-500 text-white shadow-sm hover:bg-accent-600 disabled:bg-stone-300 disabled:shadow-none dark:disabled:bg-stone-700",
  secondary:
    "border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300 dark:hover:bg-stone-800 disabled:opacity-50",
  ghost: "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100 disabled:opacity-50",
  danger: "text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40 disabled:opacity-50",
  "danger-solid": "bg-red-600 text-white shadow-sm hover:bg-red-700 disabled:opacity-50",
};

const buttonSizes = { sm: "px-2 py-1 text-xs gap-1", md: "px-3 py-1.5 text-sm gap-1.5" };

export function Button({ variant = "secondary", size = "md", busy = false, icon: Icon, children, className = "", ...props }) {
  return (
    <button
      type="button"
      disabled={busy || props.disabled}
      {...props}
      className={`inline-flex shrink-0 items-center justify-center rounded-lg font-medium transition-colors ${buttonSizes[size]} ${buttonStyles[variant]} ${focusRing} ${className}`}
    >
      {busy ? <Loader2 className="size-4 animate-spin" /> : Icon && <Icon className={size === "sm" ? "size-3.5" : "size-4"} />}
      {children}
    </button>
  );
}

// Botão só com ícone: o nome acessível é obrigatório e serve também de dica.
export function IconButton({ icon: Icon, label, variant = "ghost", className = "", ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      className={`inline-flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors ${buttonStyles[variant]} ${focusRing} ${className}`}
    >
      <Icon className="size-4" />
    </button>
  );
}

// ---------------------------------------------------------------- estado e mensagens

export function Spinner({ label }) {
  return (
    <p className="flex items-center gap-2 py-2 text-sm text-stone-500 dark:text-stone-400">
      <Loader2 className="size-4 animate-spin" />
      {label}
    </p>
  );
}

export function ErrorText({ children }) {
  if (!children) return null;
  return (
    <p className="flex items-start gap-1.5 text-sm text-red-700 dark:text-red-300" role="alert">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      {children}
    </p>
  );
}

// Lista vazia: diz o que falta e, se fizer sentido, o que fazer a seguir.
export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-stone-300 px-6 py-10 text-center dark:border-stone-700">
      {Icon && <Icon className="mb-3 size-8 text-stone-300 dark:text-stone-600" />}
      {title && <p className="font-medium text-stone-800 dark:text-stone-200">{title}</p>}
      {children && <p className="mt-1 max-w-md text-sm text-stone-500 dark:text-stone-400">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Empty({ children }) {
  return <EmptyState>{children}</EmptyState>;
}

const badgeTones = {
  neutral: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
  accent: "bg-accent-100 text-accent-800 dark:bg-accent-500/20 dark:text-accent-300",
  success: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  danger: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  outline: "border border-stone-300 text-stone-600 dark:border-stone-700 dark:text-stone-400",
};

export function Badge({ tone = "neutral", mono = false, children, className = "", ...props }) {
  return (
    <span
      {...props}
      className={`inline-flex max-w-full items-center gap-1 truncate rounded-md px-1.5 py-0.5 text-xs font-medium ${mono ? "font-mono" : ""} ${badgeTones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

// Cor de um estado definido pelo projeto: o primeiro é "em aberto", o último "concluído", os outros intermédios.
export function statusTone(status, statuses) {
  const index = statuses.indexOf(status);
  if (index < 0) return "outline";
  if (statuses.length > 1 && index === statuses.length - 1) return "success";
  return index === 0 ? "neutral" : "warning";
}

// ---------------------------------------------------------------- contentores

export function Card({ children, className = "", ...props }) {
  return (
    <div {...props} className={`rounded-xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900 ${className}`}>
      {children}
    </div>
  );
}

// Lista com separadores, dentro de um cartão. Sem overflow-hidden, para os menus das linhas não serem cortados.
export function ListCard({ children, className = "" }) {
  return (
    <ul className={`divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900 [&>li:first-child]:rounded-t-xl [&>li:last-child]:rounded-b-xl ${className}`}>
      {children}
    </ul>
  );
}

export function Section({ title, description, actions, children, className = "mb-8" }) {
  return (
    <section className={className}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-sm font-semibold text-stone-900 dark:text-stone-100">{title}</h2>}
            {description && <p className="text-sm text-stone-500 dark:text-stone-400">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

// Número com etiqueta, para os resumos.
export function Stat({ label, value, hint }) {
  return (
    <Card className="px-3 py-2.5">
      <p className="text-xl font-semibold tabular-nums leading-tight">{value}</p>
      <p className="text-xs text-stone-500 dark:text-stone-400">{label}</p>
      {hint && <p className="mt-0.5 text-xs font-medium text-accent-700 dark:text-accent-400">{hint}</p>}
    </Card>
  );
}

// ---------------------------------------------------------------- separadores

// Separadores com contagens e setas do teclado. `variant="pills"` para um segundo nível dentro de um separador;
// `inHeader` quando ficam colados ao cabeçalho da página (que já tem a linha de baixo).
export function Tabs({ tabs, value, onChange, variant = "underline", label = "Secções", inHeader = false }) {
  const refs = useRef({});
  function onKeyDown(event, index) {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = tabs[(index + delta + tabs.length) % tabs.length];
    onChange(next.value);
    refs.current[next.value]?.focus();
  }
  const pills = variant === "pills";
  return (
    <div
      role="tablist"
      aria-label={label}
      className={
        pills
          ? "mb-4 inline-flex max-w-full gap-1 overflow-x-auto rounded-lg bg-stone-100 p-1 dark:bg-stone-800/60"
          : inHeader
            ? "no-scrollbar flex gap-1 overflow-x-auto overflow-y-hidden"
            : "no-scrollbar mb-5 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-stone-200 dark:border-stone-800"
      }
    >
      {tabs.map((tab, index) => {
        const active = value === tab.value;
        return (
          <button
            key={tab.value}
            ref={(el) => (refs.current[tab.value] = el)}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.value)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={`inline-flex shrink-0 items-center gap-1.5 text-sm transition-colors ${focusRing} ${
              pills
                ? `rounded-md px-3 py-1 ${active ? "bg-white font-medium text-stone-900 shadow-sm dark:bg-stone-700 dark:text-stone-100" : "text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"}`
                : `border-b-2 px-3 py-2.5 ${active ? "border-accent-500 font-medium text-stone-900 dark:text-stone-100" : "border-transparent text-stone-500 hover:border-stone-300 hover:text-stone-800 dark:text-stone-400 dark:hover:border-stone-600 dark:hover:text-stone-200"}`
            }`}
          >
            {tab.icon && <tab.icon className="size-4" />}
            {tab.label}
            {tab.count !== undefined && tab.count !== null && (
              <span className="rounded-full bg-stone-200/80 px-1.5 text-xs tabular-nums text-stone-600 dark:bg-stone-700 dark:text-stone-300">{tab.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- janelas e gavetas

function useDialogBehaviour(onClose) {
  const panelRef = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    // Foco no primeiro campo (ou na própria janela), para o teclado começar dentro dela.
    const panel = panelRef.current;
    const first = panel?.querySelector("input:not([type=hidden]), textarea, select");
    (first || panel)?.focus();
    function onKey(event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
      if (event.key === "Tab" && panel) {
        const focusable = [...panel.querySelectorAll("a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex='-1'])")];
        if (!focusable.length) return;
        const [firstEl, lastEl] = [focusable[0], focusable[focusable.length - 1]];
        if (event.shiftKey && document.activeElement === firstEl) {
          event.preventDefault();
          lastEl.focus();
        } else if (!event.shiftKey && document.activeElement === lastEl) {
          event.preventDefault();
          firstEl.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, []);
  return panelRef;
}

const modalSizes = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-3xl" };

// Janela por cima da página. `footer`: ações (Cancelar / Guardar), sempre visíveis no fundo.
export function Modal({ title, description, onClose, children, footer, size = "md", wide = false }) {
  const titleId = useId();
  const panelRef = useDialogBehaviour(onClose);
  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center bg-stone-900/40 backdrop-blur-[1px] sm:items-center sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`animate-fade-up flex h-full w-full flex-col bg-white outline-none dark:bg-stone-900 sm:h-auto sm:max-h-full sm:rounded-2xl sm:shadow-xl ${modalSizes[wide ? "lg" : size]}`}
      >
        <header className="flex items-start gap-3 border-b border-stone-200 px-5 py-4 dark:border-stone-800">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="font-semibold">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">{description}</p>}
          </div>
          <IconButton icon={X} label="Fechar" onClick={onClose} className="-mr-1 -mt-1" />
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-stone-200 px-5 py-3 dark:border-stone-800">{footer}</footer>}
      </section>
    </div>
  );
}

// Painel lateral, para definições e formulários longos que não devem tapar a página toda.
export function Drawer({ title, description, onClose, children, footer }) {
  const titleId = useId();
  const panelRef = useDialogBehaviour(onClose);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-stone-900/30" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex h-full w-full max-w-xl flex-col bg-white shadow-2xl outline-none dark:bg-stone-900"
      >
        <header className="flex items-start gap-3 border-b border-stone-200 px-5 py-4 dark:border-stone-800">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="font-semibold">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">{description}</p>}
          </div>
          <IconButton icon={X} label="Fechar" onClick={onClose} className="-mr-1 -mt-1" />
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>
        {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-stone-200 px-5 py-3 dark:border-stone-800">{footer}</footer>}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- confirmação

const ConfirmContext = createContext(null);

// Uma só forma de confirmar o que não se desfaz: `const confirm = useConfirm(); if (await confirm({...})) …`
export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);
  const confirm = useCallback(
    (options) =>
      new Promise((resolve) => {
        setRequest({ ...options, resolve });
      }),
    [],
  );
  function close(answer) {
    request?.resolve(answer);
    setRequest(null);
  }
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <Modal
          title={request.title}
          size="sm"
          onClose={() => close(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => close(false)}>
                Cancelar
              </Button>
              <Button variant={request.tone === "neutral" ? "primary" : "danger-solid"} onClick={() => close(true)} autoFocus>
                {request.confirmLabel || "Apagar"}
              </Button>
            </>
          }
        >
          <p className="text-sm text-stone-600 dark:text-stone-300">{request.message}</p>
        </Modal>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  // Sem provider (ex.: testes isolados), cai na confirmação do browser.
  return confirm || ((options) => Promise.resolve(window.confirm(options.message || options.title)));
}

// ---------------------------------------------------------------- menu

// Menu de ações ("…"): fecha com Escape, ao clicar fora ou ao escolher. items: [{ label, icon, onSelect, danger, hidden }]
export function Menu({ items, label = "Mais ações", align = "right", trigger }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    function onDown(event) {
      if (!ref.current?.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const visible = items.filter((item) => item && !item.hidden);
  if (!visible.length) return null;
  return (
    <div ref={ref} className="relative">
      {trigger ? (
        trigger({ open, toggle: () => setOpen(!open) })
      ) : (
        <IconButton icon={MoreHorizontal} label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} />
      )}
      {open && (
        <div
          role="menu"
          className={`animate-fade-up absolute z-30 mt-1 min-w-48 overflow-hidden rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-stone-900 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {visible.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                item.danger ? "text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40" : "text-stone-700 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
              }`}
            >
              {item.icon && <item.icon className="size-4 shrink-0" />}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- documentos

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
