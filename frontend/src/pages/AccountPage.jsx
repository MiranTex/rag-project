import { useState } from "react";
import { Loader2 } from "lucide-react";
import { changePassword } from "../api";
import PageShell from "../components/PageShell";

const inputClass =
  "w-full rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 px-3 py-1.5 text-sm outline-none focus:border-stone-500";

export default function AccountPage({ user, onOpenSidebar, onSaved }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (next !== confirm) {
      setError("As duas palavras-passe novas não são iguais.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      onSaved((await changePassword(current, next)).message);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageShell title="A minha conta" description={`Sessão iniciada como ${user.username}.`} onOpenSidebar={onOpenSidebar}>
      <form onSubmit={handleSubmit} className="max-w-sm space-y-3">
        <h2 className="text-sm font-medium">Mudar palavra-passe</h2>
        <input
          className={inputClass}
          type="password"
          placeholder="Palavra-passe atual"
          aria-label="Palavra-passe atual"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          required
        />
        <input
          className={inputClass}
          type="password"
          placeholder="Nova palavra-passe (mín. 8)"
          aria-label="Nova palavra-passe"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
          minLength={8}
          required
        />
        <input
          className={inputClass}
          type="password"
          placeholder="Repetir a nova palavra-passe"
          aria-label="Repetir a nova palavra-passe"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          minLength={8}
          required
        />
        {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600 disabled:bg-stone-300 dark:disabled:bg-stone-700"
        >
          {saving && <Loader2 className="size-4 animate-spin" />}
          Mudar palavra-passe
        </button>
      </form>
    </PageShell>
  );
}
