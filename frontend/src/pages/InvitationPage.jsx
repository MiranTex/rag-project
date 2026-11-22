import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FolderOpen, Loader2 } from "lucide-react";
import { invitations, login } from "../api";
import { Button, ErrorText, inputClass } from "../components/ui";

const ROLE_TEXT = { editor: "editar", viewer: "ler e comentar" };

function Field({ label, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-stone-600 dark:text-stone-400">{label}</span>
      {children}
    </label>
  );
}

function SignupForm({ token, onDone }) {
  const [form, setForm] = useState({ username: "", display_name: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          onDone(await invitations.signup(token, { ...form, username: form.username.trim() }));
        } catch (err) {
          setError(err.message);
          setBusy(false);
        }
      }}
    >
      <Field label="O teu nome">
        <input className={inputClass} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} autoComplete="name" />
      </Field>
      <Field label="Nome de utilizador">
        <input className={inputClass} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="username" required minLength={2} />
      </Field>
      <Field label="Palavra-passe (8 caracteres ou mais)">
        <input type="password" className={inputClass} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" required minLength={8} />
      </Field>
      <ErrorText>{error}</ErrorText>
      <Button type="submit" variant="primary" busy={busy} className="w-full">
        Criar conta e entrar no projeto
      </Button>
    </form>
  );
}

function LoginForm({ onDone }) {
  const [form, setForm] = useState({ username: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          onDone(await login(form.username.trim(), form.password));
        } catch (err) {
          setError(err.message);
          setBusy(false);
        }
      }}
    >
      <Field label="Utilizador">
        <input className={inputClass} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="username" required />
      </Field>
      <Field label="Palavra-passe">
        <input type="password" className={inputClass} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="current-password" required />
      </Field>
      <ErrorText>{error}</ErrorText>
      <Button type="submit" variant="primary" busy={busy} className="w-full">
        Entrar
      </Button>
    </form>
  );
}

// Página do link de convite: abre-se sem sessão. Quem já tem conta entra e aceita; quem não tem cria-a aqui.
export default function InvitationPage({ token, session, authMode, onLoggedIn }) {
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [view, setView] = useState("signup");

  useEffect(() => {
    invitations.info(token).then(
      (data) => {
        setInfo(data);
        if (!data.signup_allowed) setView("login");
      },
      (err) => setError(err.message),
    );
  }, [token]);

  async function accept() {
    setAccepting(true);
    setError("");
    try {
      const { project_id } = await invitations.accept(token);
      navigate(`/projetos/${project_id}`, { replace: true });
    } catch (err) {
      setError(err.message);
      setAccepting(false);
    }
  }

  const tabClass = (active) =>
    `flex-1 rounded-md px-3 py-1.5 text-sm ${active ? "bg-white font-medium shadow-sm dark:bg-stone-800" : "text-stone-500 dark:text-stone-400"}`;

  return (
    <div className="flex h-full items-center justify-center bg-stone-50 px-4 dark:bg-stone-950">
      <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900">
        {!info && !error && (
          <p className="flex items-center gap-2 text-sm text-stone-500">
            <Loader2 className="size-4 animate-spin" /> A abrir o convite…
          </p>
        )}
        {!info && error && (
          <>
            <h1 className="text-lg font-semibold">Convite indisponível</h1>
            <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">{error}</p>
            <Button className="mt-4" onClick={() => navigate("/", { replace: true })}>
              Ir para a aplicação
            </Button>
          </>
        )}
        {info && (
          <>
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-accent-700 dark:text-accent-400">
              <FolderOpen className="size-4" /> Convite para um projeto
            </p>
            <h1 className="mt-1 text-lg font-semibold tracking-tight">{info.project_title}</h1>
            <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
              {info.invited_by || "Alguém"} convidou {info.email} para {ROLE_TEXT[info.role]} neste projeto.
            </p>

            <div className="mt-5">
              {info.status !== "pending" ? (
                <>
                  <p className="text-sm">{info.status === "accepted" ? "Este convite já foi usado." : "Este convite expirou. Pede um novo a quem te convidou."}</p>
                  <Button className="mt-4" onClick={() => navigate("/", { replace: true })}>
                    Ir para a aplicação
                  </Button>
                </>
              ) : session ? (
                <>
                  <p className="mb-3 text-sm text-stone-600 dark:text-stone-400">
                    Entraste como <strong>{session.user.display_name || session.user.username}</strong>.
                  </p>
                  <ErrorText>{error}</ErrorText>
                  <Button variant="primary" className="w-full" busy={accepting} onClick={accept}>
                    Aceitar e abrir o projeto
                  </Button>
                </>
              ) : authMode !== "local" ? (
                <p className="text-sm text-stone-600 dark:text-stone-400">Entra a partir do sistema principal e abre este link de novo para aceitar.</p>
              ) : (
                <>
                  {info.signup_allowed && (
                    <div className="mb-4 flex gap-1 rounded-lg bg-stone-100 p-1 dark:bg-stone-950" role="tablist">
                      <button type="button" role="tab" aria-selected={view === "signup"} className={tabClass(view === "signup")} onClick={() => setView("signup")}>
                        Criar conta
                      </button>
                      <button type="button" role="tab" aria-selected={view === "login"} className={tabClass(view === "login")} onClick={() => setView("login")}>
                        Já tenho conta
                      </button>
                    </div>
                  )}
                  {view === "signup" && info.signup_allowed ? (
                    <SignupForm
                      token={token}
                      onDone={(user) => {
                        onLoggedIn(user);
                        // A conta nova já entrou no projeto: abre a aplicação no início (a lista de projetos mostra-o).
                        navigate("/projetos", { replace: true });
                      }}
                    />
                  ) : (
                    <LoginForm onDone={onLoggedIn} />
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
