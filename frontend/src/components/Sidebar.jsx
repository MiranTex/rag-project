import { NavLink } from "react-router-dom";
import { useResearch } from "../research/ResearchContext";
import {
  Compass,
  FileText,
  FolderOpen,
  Files,
  LogOut,
  Search,
  ThumbsUp,
  MessageSquare,
  Monitor,
  Moon,
  Settings,
  SquarePen,
  Sun,
  UserRound,
  Users,
  X,
} from "lucide-react";

// Fornecedor de LLM ativo (de /health), mostrado no tooltip do indicador "Modelo".
const PROVIDER_LABELS = {
  openrouter: "OpenRouter",
  anthropic: "Anthropic",
  openai: "OpenAI",
  lmstudio: "LM Studio",
  custom: "API compatível com OpenAI",
};

function HealthDot({ label, ok, title }) {
  const color = ok === undefined ? "bg-stone-300 dark:bg-stone-600" : ok ? "bg-emerald-500" : "bg-red-500";
  const name = title ? `${label}: ${title}` : label;
  return (
    <span className="flex items-center gap-1.5" title={ok === false ? `${name} indisponível` : name}>
      <span className={`size-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}

const THEME_OPTIONS = [
  { value: "system", label: "Tema do sistema", icon: Monitor },
  { value: "light", label: "Tema claro", icon: Sun },
  { value: "dark", label: "Tema escuro", icon: Moon },
];

function ThemeSwitch({ theme, onThemeChange }) {
  return (
    <div className="ml-auto flex rounded-md bg-stone-200/60 p-0.5 dark:bg-stone-800" role="group" aria-label="Tema">
      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          title={label}
          aria-label={label}
          aria-pressed={theme === value}
          onClick={() => onThemeChange(value)}
          className={`rounded p-1 ${
            theme === value
              ? "bg-white text-stone-900 shadow-sm dark:bg-stone-600 dark:text-stone-100"
              : "text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
          }`}
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  );
}

function NavItem({ to, icon: Icon, label, badge, onNavigate }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${
          isActive
            ? "bg-stone-200/70 font-medium text-stone-900 dark:bg-stone-800 dark:text-stone-100"
            : "text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
        }`
      }
    >
      <Icon className="size-4 shrink-0" />
      <span className="flex-1">{label}</span>
      {badge > 0 && (
        <span className="rounded-full bg-accent-500 px-1.5 text-xs font-medium leading-5 text-white">{badge}</span>
      )}
    </NavLink>
  );
}

function NavGroup({ label, children }) {
  return (
    <div className="pt-4 first:pt-0">
      {label && <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500">{label}</p>}
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

// Os projetos mexidos mais recentemente, para lá chegar sem passar pela lista.
function RecentProjects({ onNavigate }) {
  const { projects, activeProjectId } = useResearch();
  const recent = projects.slice(0, 5);
  if (!recent.length) return null;
  return (
    <div className="ml-4 mt-0.5 space-y-0.5 border-l border-stone-200 pl-2 dark:border-stone-800">
      {recent.map(({ project }) => (
        <NavLink
          key={project.project_id}
          to={`/projetos/${project.project_id}`}
          onClick={onNavigate}
          title={project.title}
          className={({ isActive }) =>
            `flex items-center gap-2 truncate rounded-md px-2 py-1 text-[13px] ${
              isActive ? "bg-stone-200/70 font-medium text-stone-900 dark:bg-stone-800 dark:text-stone-100" : "text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
            }`
          }
        >
          <span className={`size-1.5 shrink-0 rounded-full ${project.project_id === activeProjectId ? "bg-accent-500" : "bg-stone-300 dark:bg-stone-600"}`} />
          <span className="truncate">{project.title}</span>
        </NavLink>
      ))}
    </div>
  );
}

// Cada pessoa só vê as páginas que as suas permissões deixam usar.
export default function Sidebar({
  open,
  onClose,
  onNewChat,
  health,
  theme,
  onThemeChange,
  pages,
  attentionCount,
  user,
  canChangePassword,
  onLogout,
}) {
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-stone-900/30 md:hidden" onClick={onClose} />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-950 transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center justify-between px-4">
          <span className="font-semibold tracking-tight">RAG Study</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onNewChat}
              title="Nova conversa"
              aria-label="Nova conversa"
              className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-900 dark:hover:text-stone-100"
            >
              <SquarePen className="size-[18px]" />
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Fechar barra lateral"
              className="rounded-md p-1.5 text-stone-600 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 md:hidden"
            >
              <X className="size-[18px]" />
            </button>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-3" aria-label="Navegação principal">
          <NavGroup>
            <NavItem to="/" icon={MessageSquare} label="Chat" onNavigate={onClose} />
            {pages.research && (
              <>
                <NavItem to="/projetos" icon={FolderOpen} label="Projetos" onNavigate={onClose} />
                <RecentProjects onNavigate={onClose} />
                <NavItem to="/pesquisa" icon={Search} label="Pesquisa" onNavigate={onClose} />
                <NavItem to="/descobrir" icon={Compass} label="Descobrir" onNavigate={onClose} />
              </>
            )}
          </NavGroup>
          <NavGroup label="Biblioteca">
            {pages.documents && <NavItem to="/documentos" icon={FileText} label="Documentos" badge={attentionCount} onNavigate={onClose} />}
            <NavItem to="/ficheiros" icon={Files} label="Ficheiros gerados" onNavigate={onClose} />
          </NavGroup>
          {(pages.users || pages.feedback || pages.settings) && (
            <NavGroup label="Administração">
              {pages.users && <NavItem to="/utilizadores" icon={Users} label="Utilizadores" onNavigate={onClose} />}
              {pages.feedback && <NavItem to="/avaliacoes" icon={ThumbsUp} label="Avaliações" onNavigate={onClose} />}
              {pages.settings && <NavItem to="/configuracoes" icon={Settings} label="Configurações" onNavigate={onClose} />}
            </NavGroup>
          )}
        </nav>

        <div className="flex items-center gap-1 border-t border-stone-200 dark:border-stone-800 px-2 py-2 text-sm">
          {canChangePassword ? (
            <NavLink
              to="/conta"
              onClick={onClose}
              title="A minha conta"
              className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-stone-700 hover:bg-stone-200 dark:text-stone-300 dark:hover:bg-stone-800"
            >
              <UserRound className="size-4 shrink-0 text-stone-500 dark:text-stone-400" />
              <span className="truncate">{user.display_name || user.username}</span>
            </NavLink>
          ) : (
            <span className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-stone-700 dark:text-stone-300">
              <UserRound className="size-4 shrink-0 text-stone-500 dark:text-stone-400" />
              <span className="truncate">{user.display_name || user.username}</span>
            </span>
          )}
          <button
            type="button"
            onClick={onLogout}
            title="Sair"
            aria-label="Sair"
            className="rounded-md p-1.5 text-stone-500 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-900 dark:hover:text-stone-100"
          >
            <LogOut className="size-4" />
          </button>
        </div>

        <footer className="flex items-center gap-4 border-t border-stone-200 dark:border-stone-800 px-4 py-3 text-xs text-stone-500 dark:text-stone-400">
          <HealthDot label="API" ok={health ? !health.offline : undefined} />
          <HealthDot label="Modelo" ok={health?.lmstudio} title={PROVIDER_LABELS[health?.llm_provider]} />
          <HealthDot label="Vetores" ok={health?.vectors} />
          <ThemeSwitch theme={theme} onThemeChange={onThemeChange} />
        </footer>
      </aside>
    </>
  );
}
