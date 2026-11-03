import { useEffect, useState } from "react";
import { KeyRound, Loader2, UserPlus } from "lucide-react";
import { createUser, listRoles, listUsers, updateUser } from "../api";
import PageShell from "../components/PageShell";

// Papéis do backend (backend/auth/permissions.py).
const ROLE_LABELS = {
  admin: { label: "Administrador", hint: "Tudo, incluindo utilizadores e configurações." },
  manager: { label: "Gestor", hint: "Carrega, revê e aprova documentos; usa o chat." },
  uploader: { label: "Carrega", hint: "Carrega e revê documentos; não aprova." },
  reviewer: { label: "Revê e aprova", hint: "Revê e aprova documentos; não carrega." },
  chat: { label: "Só chat", hint: "Faz perguntas; não vê a lista de documentos." },
};

const roleLabel = (role) => ROLE_LABELS[role]?.label || role;

const inputClass =
  "w-full rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 px-3 py-1.5 text-sm outline-none focus:border-stone-500";

function RolePicker({ roles, value, onChange, disabled }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {roles.map((role) => {
        const on = value.includes(role);
        return (
          <button
            key={role}
            type="button"
            disabled={disabled}
            title={ROLE_LABELS[role]?.hint}
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((r) => r !== role) : [...value, role])}
            className={`rounded-full border px-2.5 py-0.5 text-xs disabled:cursor-default ${
              on
                ? "border-accent-500 bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-400"
                : "border-stone-300 text-stone-600 enabled:hover:bg-stone-100 dark:border-stone-700 dark:text-stone-400 dark:enabled:hover:bg-stone-800"
            }`}
          >
            {roleLabel(role)}
          </button>
        );
      })}
    </div>
  );
}

function NewUserForm({ roles, onCreated }) {
  const [draft, setDraft] = useState({ username: "", display_name: "", password: "", roles: ["chat"] });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const user = await createUser({ ...draft, username: draft.username.trim() });
      setDraft({ username: "", display_name: "", password: "", roles: ["chat"] });
      onCreated(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-8 space-y-3 rounded-xl border border-stone-200 p-4 dark:border-stone-800">
      <h2 className="text-sm font-medium">Novo utilizador</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <input
          className={inputClass}
          placeholder="Utilizador"
          aria-label="Utilizador"
          value={draft.username}
          onChange={(e) => setDraft({ ...draft, username: e.target.value })}
          required
          minLength={2}
          autoComplete="off"
        />
        <input
          className={inputClass}
          placeholder="Nome (opcional)"
          aria-label="Nome"
          value={draft.display_name}
          onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
        />
        <input
          className={inputClass}
          type="password"
          placeholder="Palavra-passe (mín. 8)"
          aria-label="Palavra-passe"
          value={draft.password}
          onChange={(e) => setDraft({ ...draft, password: e.target.value })}
          required
          minLength={8}
          autoComplete="new-password"
        />
      </div>
      <RolePicker roles={roles} value={draft.roles} onChange={(next) => setDraft({ ...draft, roles: next })} />
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600 disabled:bg-stone-300 dark:disabled:bg-stone-700"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <UserPlus className="size-4" />}
          Criar
        </button>
        {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      </div>
    </form>
  );
}

function UserRow({ user, roles, isSelf, canEditRoles, canSetPassword, onSaved }) {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [password, setPassword] = useState(null);

  async function save(changes) {
    setSaving(true);
    setError("");
    try {
      onSaved(await updateUser(user.user_id, changes));
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className={`space-y-2 py-4 ${user.active ? "" : "opacity-60"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium text-stone-800 dark:text-stone-200">{user.display_name || user.username}</span>
        <span className="text-sm text-stone-500 dark:text-stone-400">
          {user.username}
          {user.external_id && " · externo"}
          {isSelf && " · tu"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {saving && <Loader2 className="size-4 animate-spin text-stone-400" />}
          {canSetPassword && !user.external_id && (
            <button
              type="button"
              onClick={() => setPassword(password === null ? "" : null)}
              title="Definir palavra-passe"
              aria-label="Definir palavra-passe"
              className="rounded-md p-1.5 text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
            >
              <KeyRound className="size-4" />
            </button>
          )}
          <label className="flex items-center gap-1.5 text-sm text-stone-600 dark:text-stone-400">
            <input
              type="checkbox"
              checked={user.active}
              disabled={saving || isSelf}
              onChange={(e) => save({ active: e.target.checked })}
            />
            Ativo
          </label>
        </div>
      </div>
      <RolePicker
        roles={roles}
        value={user.roles}
        disabled={saving || !canEditRoles}
        onChange={(next) => save({ roles: next })}
      />
      {password !== null && (
        <form
          className="flex gap-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await save({ password })) setPassword(null);
          }}
        >
          <input
            className={inputClass}
            type="password"
            placeholder="Nova palavra-passe (mín. 8)"
            aria-label="Nova palavra-passe"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
            autoFocus
            autoComplete="new-password"
          />
          <button
            type="submit"
            className="shrink-0 rounded-lg border border-stone-300 px-3 py-1.5 text-sm hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
          >
            Guardar
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
    </li>
  );
}

export default function UsersPage({ authConfig, currentUserId, onOpenSidebar }) {
  const [users, setUsers] = useState(null);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const local = authConfig.mode === "local";

  useEffect(() => {
    Promise.all([listUsers(), listRoles()])
      .then(([userList, roleMap]) => {
        setUsers(userList);
        setRoles(Object.keys(roleMap));
      })
      .catch((err) => setError(err.message));
  }, []);

  function replaceUser(updated) {
    setUsers((prev) => prev.map((u) => (u.user_id === updated.user_id ? updated : u)));
  }

  return (
    <PageShell
      title="Utilizadores"
      description={
        local
          ? "Quem entra na aplicação e o que cada pessoa pode fazer. Passa o rato por um papel para ver o que inclui."
          : authConfig.roles_from_token
            ? "Os utilizadores entram pelo sistema externo e os papéis vêm de lá. Aqui só se ativa ou desativa o acesso."
            : "Os utilizadores entram pelo sistema externo e aparecem aqui no primeiro acesso; os papéis atribuem-se aqui."
      }
      onOpenSidebar={onOpenSidebar}
    >
      {local && roles.length > 0 && (
        <NewUserForm roles={roles} onCreated={(user) => setUsers((prev) => [...prev, user])} />
      )}
      {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      {!users && !error && <Loader2 className="size-5 animate-spin text-stone-400" />}
      {users && (
        <ul className="divide-y divide-stone-200 dark:divide-stone-800">
          {users.map((user) => (
            <UserRow
              key={user.user_id}
              user={user}
              roles={roles}
              isSelf={user.user_id === currentUserId}
              canEditRoles={!authConfig.roles_from_token}
              canSetPassword={local}
              onSaved={replaceUser}
            />
          ))}
        </ul>
      )}
    </PageShell>
  );
}
