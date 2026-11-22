import { useEffect, useState } from "react";
import { Check, Copy, Mail, UserPlus, X } from "lucide-react";
import { research } from "../../api";
import { Button, ErrorText, inputClass, controlBase } from "../../components/ui";
import { Modal, ROLE_LABELS, useConfirm } from "../../components/ui";

export { ROLE_LABELS };

function RoleSelect({ value, onChange }) {
  return (
    <select className={`${controlBase} w-36 shrink-0`} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Papel">
      <option value="viewer">{ROLE_LABELS.viewer}</option>
      <option value="editor">{ROLE_LABELS.editor}</option>
    </select>
  );
}

function inviteLink(token) {
  return `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, "")}/convite/${encodeURIComponent(token)}`;
}

function CreatedInvite({ invite, onDone }) {
  const [copied, setCopied] = useState(false);
  const link = inviteLink(invite.token);
  const subject = encodeURIComponent("Convite para um projeto");
  const body = encodeURIComponent(`Olá! Convidei-te para um projeto. Abre este link para entrar (ou criar conta):\n\n${link}`);
  return (
    <div className="space-y-2 rounded-xl border border-accent-300 bg-accent-50/50 p-3 text-sm dark:border-accent-500/40 dark:bg-accent-500/5">
      <p>
        Convite criado para <strong>{invite.email}</strong>. Envia-lhe este link; só é mostrado agora e serve uma vez.
      </p>
      <input className={`${inputClass} font-mono text-xs`} readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Link do convite" />
      <div className="flex gap-2">
        <Button
          icon={copied ? Check : Copy}
          onClick={() =>
            navigator.clipboard.writeText(link).then(
              () => setCopied(true),
              () => setCopied(false),
            )
          }
        >
          {copied ? "Copiado" : "Copiar link"}
        </Button>
        <a
          href={`mailto:${invite.email}?subject=${subject}&body=${body}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-100 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
        >
          <Mail className="size-4" /> Abrir no email
        </a>
        <Button variant="ghost" className="ml-auto" onClick={onDone}>
          Fechar
        </Button>
      </div>
    </div>
  );
}

// Partilhar o projeto: membros atuais, juntar quem já tem conta e convidar por email quem ainda não tem.
export default function ShareDialog({ detail, currentUserId, onChange, onLeft, onClose }) {
  const { project } = detail;
  const isOwner = detail.my_role === "owner";
  const confirm = useConfirm();
  const [member, setMember] = useState({ username: "", role: "editor" });
  const [invite, setInvite] = useState({ email: "", role: "editor" });
  const [pending, setPending] = useState([]);
  const [created, setCreated] = useState(null);
  const [error, setError] = useState("");

  const loadPending = () => isOwner && research.invitations(project.project_id).then(setPending, (err) => setError(err.message));
  useEffect(() => {
    loadPending();
  }, [project.project_id]);

  async function run(action) {
    setError("");
    try {
      return await action();
    } catch (err) {
      setError(err.message);
      return null;
    }
  }

  return (
    <Modal title={`Partilhar "${project.title}"`} onClose={onClose}>
      <div className="space-y-6">
        <section>
          <h3 className="mb-2 text-sm font-medium">Pessoas com acesso</h3>
          <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 text-sm dark:divide-stone-800 dark:border-stone-800">
            {detail.members.map((m) => (
              <li key={m.user_id} className="flex items-center gap-2 px-3 py-2">
                <span className="min-w-0 flex-1 truncate">
                  {m.display_name || m.username} <span className="text-stone-500 dark:text-stone-400">({m.username})</span>
                </span>
                <span className="text-xs text-stone-500 dark:text-stone-400">{ROLE_LABELS[m.role]}</span>
                {m.role !== "owner" && (isOwner || m.user_id === currentUserId) && (
                  <Button
                    variant="ghost"
                    icon={X}
                    aria-label={m.user_id === currentUserId ? "Sair do projeto" : `Remover ${m.username}`}
                    onClick={() =>
                      run(async () => {
                        const self = m.user_id === currentUserId;
                        const ok = await confirm({
                          title: self ? "Sair do projeto?" : `Remover ${m.display_name || m.username}?`,
                          message: self ? "Deixas de ver este projeto." : "Deixa de ter acesso ao projeto.",
                          confirmLabel: self ? "Sair" : "Remover",
                        });
                        if (!ok) return;
                        const next = await research.removeMember(project.project_id, m.user_id);
                        if (next) onChange(next);
                        else onLeft();
                      })
                    }
                  />
                )}
              </li>
            ))}
          </ul>
        </section>

        {isOwner && (
          <section>
            <h3 className="mb-1 text-sm font-medium">Adicionar quem já tem conta</h3>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  onChange(await research.addMember(project.project_id, { username: member.username.trim(), role: member.role }));
                  setMember({ ...member, username: "" });
                });
              }}
            >
              <input
                className={`${controlBase} min-w-0 flex-1`}
                placeholder="Nome de utilizador"
                aria-label="Nome de utilizador"
                value={member.username}
                onChange={(e) => setMember({ ...member, username: e.target.value })}
                required
              />
              <RoleSelect value={member.role} onChange={(role) => setMember({ ...member, role })} />
              <Button type="submit" icon={UserPlus}>
                Adicionar
              </Button>
            </form>
          </section>
        )}

        {isOwner && (
          <section>
            <h3 className="mb-1 text-sm font-medium">Convidar por email</h3>
            <p className="mb-2 text-xs text-stone-500 dark:text-stone-400">Para quem ainda não tem conta: recebe um link para a criar e entrar no projeto.</p>
            {created ? (
              <CreatedInvite invite={created} onDone={() => setCreated(null)} />
            ) : (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    setCreated(await research.invite(project.project_id, { email: invite.email.trim(), role: invite.role }));
                    setInvite({ ...invite, email: "" });
                    loadPending();
                  });
                }}
              >
                <input
                  type="email"
                  className={`${controlBase} min-w-0 flex-1`}
                  placeholder="email@exemplo.pt"
                  aria-label="Email"
                  value={invite.email}
                  onChange={(e) => setInvite({ ...invite, email: e.target.value })}
                  required
                />
                <RoleSelect value={invite.role} onChange={(role) => setInvite({ ...invite, role })} />
                <Button type="submit" icon={Mail}>
                  Convidar
                </Button>
              </form>
            )}
            {pending.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {pending.map((i) => (
                  <li key={i.invitation_id} className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate">{i.email}</span>
                    <span className="text-xs text-stone-500 dark:text-stone-400">
                      {ROLE_LABELS[i.role]} · até {new Date(i.expires_at).toLocaleDateString("pt-PT")}
                    </span>
                    <Button
                      variant="ghost"
                      icon={X}
                      aria-label={`Anular o convite de ${i.email}`}
                      onClick={() =>
                        run(async () => {
                          if (await confirm({ title: "Anular o convite?", message: `O link enviado a ${i.email} deixa de funcionar.`, confirmLabel: "Anular" }))
                            await research.revokeInvitation(project.project_id, i.invitation_id).then(loadPending);
                        })
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
        <ErrorText>{error}</ErrorText>
      </div>
    </Modal>
  );
}
