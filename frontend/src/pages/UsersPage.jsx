import { useEffect, useState } from "react";
import { KeyRound, Loader2, UserPlus, Users } from "lucide-react";
import { createUser, listRoles, listUsers, updateUser } from "../api";
import PageShell from "../components/PageShell";
import { Badge, Button, EmptyState, ErrorText, Field, IconButton, Modal, Spinner, inputClass, useConfirm } from "../components/ui";

// Papéis do backend (backend/auth/permissions.py).
const ROLE_LABELS = {
  admin: { label: "Administrador", hint: "Tudo, incluindo utilizadores e configurações." },
  manager: { label: "Gestor", hint: "Carrega, revê e aprova documentos; usa o chat." },
  uploader: { label: "Carrega", hint: "Carrega e revê documentos; não aprova." },
  reviewer: { label: "Revê e aprova", hint: "Revê e aprova documentos; não carrega." },
  chat: { label: "Só chat", hint: "Faz perguntas; não vê a lista de documentos." },
};

const roleLabel = (role) => ROLE_LABELS[role]?.label || role;

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

function NewUserModal({ roles, onCreated, onClose }) {
  const [draft, setDraft] = useState({ username: "", display_name: "", password: "", roles: ["chat"] });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const user = await createUser({ ...draft, username: draft.username.trim() });
      onCreated(user);
      onClose();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Novo utilizador"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="new-user" variant="primary" icon={UserPlus} busy={saving}>
            Criar
          </Button>
        </>
      }
    >
      <form id="new-user" onSubmit={handleSubmit} className="space-y-4">
        <Field label="Utilizador" hint="Usado para entrar. Mínimo 2 caracteres.">
          <input
            className={inputClass}
            value={draft.username}
            onChange={(e) => setDraft({ ...draft, username: e.target.value })}
            required
            minLength={2}
            autoComplete="off"
          />
        </Field>
        <Field label="Nome (opcional)">
          <input className={inputClass} value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} />
        </Field>
        <Field label="Palavra-passe" hint="Mínimo 8 caracteres.">
          <input
            className={inputClass}
            type="password"
            value={draft.password}
            onChange={(e) => setDraft({ ...draft, password: e.target.value })}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </Field>
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-stone-700 dark:text-stone-300">Papéis</legend>
          <RolePicker roles={roles} value={draft.roles} onChange={(next) => setDraft({ ...draft, roles: next })} />
          <ul className="mt-2 space-y-0.5 text-xs text-stone-500 dark:text-stone-400">
            {draft.roles.map((role) => (
              <li key={role}>
                <span className="font-medium text-stone-600 dark:text-stone-300">{roleLabel(role)}:</span> {ROLE_LABELS[role]?.hint}
              </li>
            ))}
          </ul>
        </fieldset>
        <ErrorText>{error}</ErrorText>
      </form>
    </Modal>
  );
}

function UserRow({ user, roles, isSelf, canEditRoles, canSetPassword, onSaved }) {
  const confirm = useConfirm();
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [password, setPassword] = useState(null);
  const name = user.display_name || user.username;

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

  async function toggleActive(active) {
    if (
      !active &&
      !(await confirm({
        title: "Desativar utilizador?",
        message: `${name} deixa de conseguir entrar na aplicação. Podes voltar a ativar mais tarde.`,
        confirmLabel: "Desativar",
      }))
    )
      return;
    save({ active });
  }

  return (
    <li className={`space-y-2 px-4 py-3 ${user.active ? "" : "bg-stone-50 dark:bg-stone-900/60"}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={`font-medium ${user.active ? "text-stone-800 dark:text-stone-200" : "text-stone-500 dark:text-stone-400"}`}>{name}</span>
        <span className="text-sm text-stone-500 dark:text-stone-400">{user.username}</span>
        {user.external_id && <Badge tone="outline">externo</Badge>}
        {isSelf && <Badge tone="accent">tu</Badge>}
        {!user.active && <Badge tone="warning">desativado</Badge>}
        <div className="ml-auto flex items-center gap-2">
          {saving && <Loader2 className="size-4 animate-spin text-stone-400 dark:text-stone-500" />}
          {canSetPassword && !user.external_id && (
            <IconButton icon={KeyRound} label={`Definir palavra-passe de ${name}`} onClick={() => setPassword(password === null ? "" : null)} />
          )}
          <label className="flex items-center gap-1.5 text-sm text-stone-600 dark:text-stone-400" title={isSelf ? "Não te podes desativar a ti próprio." : undefined}>
            <input type="checkbox" checked={user.active} disabled={saving || isSelf} onChange={(e) => toggleActive(e.target.checked)} />
            Ativo
          </label>
        </div>
      </div>
      <RolePicker roles={roles} value={user.roles} disabled={saving || !canEditRoles} onChange={(next) => save({ roles: next })} />
      {password !== null && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await save({ password })) setPassword(null);
          }}
        >
          <Field label="Nova palavra-passe" hint="Mínimo 8 caracteres." className="min-w-48 flex-1">
            <input
              className={inputClass}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
              autoFocus
              autoComplete="new-password"
            />
          </Field>
          <div className="flex gap-2 pb-5">
            <Button variant="ghost" onClick={() => setPassword(null)}>
              Cancelar
            </Button>
            <Button type="submit" variant="primary" busy={saving}>
              Guardar
            </Button>
          </div>
        </form>
      )}
      <ErrorText>{error}</ErrorText>
    </li>
  );
}

export default function UsersPage({ authConfig, currentUserId, onOpenSidebar }) {
  const [users, setUsers] = useState(null);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
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
      subtitle={
        local
          ? "Quem entra na aplicação e o que cada pessoa pode fazer. Passa o rato por um papel para ver o que inclui."
          : authConfig.roles_from_token
            ? "Os utilizadores entram pelo sistema externo e os papéis vêm de lá. Aqui só se ativa ou desativa o acesso."
            : "Os utilizadores entram pelo sistema externo e aparecem aqui no primeiro acesso; os papéis atribuem-se aqui."
      }
      meta={users && <span>{users.length} utilizador{users.length === 1 ? "" : "es"}</span>}
      actions={
        local &&
        roles.length > 0 && (
          <Button variant="primary" icon={UserPlus} onClick={() => setCreating(true)}>
            Novo utilizador
          </Button>
        )
      }
      onOpenSidebar={onOpenSidebar}
    >
      <ErrorText>{error}</ErrorText>
      {!users && !error && <Spinner label="A carregar…" />}
      {users && users.length === 0 && <EmptyState icon={Users} title="Ainda não há utilizadores" />}
      {users && users.length > 0 && (
        <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
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
      {creating && <NewUserModal roles={roles} onCreated={(user) => setUsers((prev) => [...(prev || []), user])} onClose={() => setCreating(false)} />}
    </PageShell>
  );
}
