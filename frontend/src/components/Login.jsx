import { useState } from "react";
import { Loader2, LogIn } from "lucide-react";
import { login } from "../api";

// mode "external": o login é feito no sistema anfitrião, que abre esta aplicação com o token.
export default function Login({ mode, onLoggedIn, message }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setWorking(true);
    setError("");
    try {
      onLoggedIn(await login(username.trim(), password));
    } catch (err) {
      setError(err.message);
      setWorking(false);
    }
  }

  const input =
    "w-full rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 px-3 py-2 text-sm outline-none focus:border-stone-500 dark:focus:border-stone-500";

  return (
    <div className="flex h-full items-center justify-center bg-stone-50 dark:bg-stone-950 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 p-6 shadow-sm">
        <h1 className="text-lg font-semibold tracking-tight">RAG Study</h1>
        {mode === "external" ? (
          <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
            {message || "Sessão em falta. Entra a partir do sistema principal."}
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="mt-4 space-y-3">
            {message && <p className="text-sm text-stone-600 dark:text-stone-400">{message}</p>}
            <label className="block text-sm">
              <span className="mb-1 block text-stone-600 dark:text-stone-400">Utilizador</span>
              <input
                className={input}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-stone-600 dark:text-stone-400">Palavra-passe</span>
              <input
                className={input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
            <button
              type="submit"
              disabled={working}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:bg-stone-300 dark:disabled:bg-stone-700"
            >
              {working ? <Loader2 className="size-4 animate-spin" /> : <LogIn className="size-4" />}
              Entrar
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
