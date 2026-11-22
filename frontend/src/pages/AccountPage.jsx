import { useState } from "react";
import { KeyRound } from "lucide-react";
import { changePassword } from "../api";
import PageShell from "../components/PageShell";
import { Button, Card, ErrorText, Field, Section, inputClass } from "../components/ui";

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
    <PageShell title="A minha conta" subtitle={`Sessão iniciada como ${user.username}.`} onOpenSidebar={onOpenSidebar}>
      <Section title="Mudar palavra-passe">
        <Card className="max-w-md p-4">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Palavra-passe atual">
              <input className={inputClass} type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
            </Field>
            <Field label="Nova palavra-passe" hint="Mínimo 8 caracteres.">
              <input className={inputClass} type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required />
            </Field>
            <Field label="Repetir a nova palavra-passe">
              <input className={inputClass} type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" minLength={8} required />
            </Field>
            <ErrorText>{error}</ErrorText>
            <div className="flex justify-end">
              <Button type="submit" variant="primary" icon={KeyRound} busy={saving}>
                Mudar palavra-passe
              </Button>
            </div>
          </form>
        </Card>
      </Section>
    </PageShell>
  );
}
