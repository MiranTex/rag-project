import { useEffect, useState } from "react";
import { Bot, Loader2, ShieldCheck } from "lucide-react";
import { oauth } from "../api";
import { Button, ErrorText } from "../components/ui";

// Página aberta por uma aplicação (claude.ai, Claude Desktop, Claude Code…) que quer usar a base de conhecimento
// em nome da pessoa. Só aparece com sessão iniciada; ao autorizar ou recusar, volta-se à aplicação.
export default function OAuthConsentPage({ requestId, session }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [canWrite, setCanWrite] = useState(false);
  const [working, setWorking] = useState("");

  useEffect(() => {
    if (!requestId) {
      setError("Falta o pedido de autorização. Volta à aplicação e liga-a de novo.");
      return;
    }
    oauth.request(requestId).then(setInfo, (err) => setError(err.message));
  }, [requestId]);

  async function decide(kind) {
    setWorking(kind);
    setError("");
    try {
      const { redirect_to } = kind === "approve" ? await oauth.approve(requestId, canWrite) : await oauth.deny(requestId);
      window.location.assign(redirect_to);
    } catch (err) {
      setError(err.message);
      setWorking("");
    }
  }

  const asksWrite = info?.scopes.includes("write");

  return (
    <div className="flex h-full items-center justify-center bg-stone-50 px-4 dark:bg-stone-950">
      <div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900">
        {!info && !error && (
          <p className="flex items-center gap-2 text-sm text-stone-500">
            <Loader2 className="size-4 animate-spin" /> A abrir o pedido…
          </p>
        )}

        {info && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-100 text-accent-700 dark:bg-accent-500/20 dark:text-accent-300">
                <Bot className="size-5" />
              </span>
              <div className="min-w-0">
                <h1 className="text-base font-semibold">{info.client_name} quer ligar-se à tua conta</h1>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  Sessão de {info.user} · volta para {info.redirect_host}
                </p>
              </div>
            </div>

            <div className="space-y-2 text-sm text-stone-700 dark:text-stone-300">
              <p>Se autorizares, esta aplicação vai poder, em teu nome:</p>
              <ul className="list-disc space-y-1 pl-5">
                <li>pesquisar e ler os documentos da base de conhecimento;</li>
                <li>ver os projetos de que és membro, o caderno e os comentários.</li>
              </ul>
              <p className="text-xs text-stone-500 dark:text-stone-400">
                É a própria aplicação que pensa e escreve as respostas: não gasta a chave de IA da plataforma.
              </p>
            </div>

            {asksWrite && (
              <label className="flex items-start gap-2 rounded-xl border border-stone-200 p-3 text-sm dark:border-stone-800">
                <input type="checkbox" className="mt-0.5" checked={canWrite} onChange={(e) => setCanWrite(e.target.checked)} disabled={!!working} />
                <span>
                  Também propor alterações ao caderno e comentar nos projetos
                  <span className="block text-xs text-stone-500 dark:text-stone-400">
                    As propostas só entram no caderno quando alguém da equipa as aceitar. Tudo fica assinado com o nome da aplicação.
                  </span>
                </span>
              </label>
            )}

            <p className="flex items-start gap-2 text-xs text-stone-500 dark:text-stone-400">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" />
              Só autorizes se foste tu a ligar esta aplicação agora. Podes revogar o acesso a qualquer momento em A minha conta.
            </p>

            <div className="flex justify-end gap-2">
              <Button variant="ghost" busy={working === "deny"} disabled={!!working} onClick={() => decide("deny")}>
                Recusar
              </Button>
              <Button variant="primary" busy={working === "approve"} disabled={!!working} onClick={() => decide("approve")}>
                Autorizar
              </Button>
            </div>
          </div>
        )}

        <ErrorText>{error}</ErrorText>
      </div>
    </div>
  );
}
