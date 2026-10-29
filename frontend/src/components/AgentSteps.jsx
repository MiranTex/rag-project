import { useState } from "react";
import { Ban, Check, ChevronRight, FilePlus2, Loader2, ShieldCheck, Square, X } from "lucide-react";

const TOOL_LABELS = {
  list_documents: "Listar documentos",
  search_documents: "Pesquisar",
  read_document: "Ler documento",
  calculate: "Calcular",
  percentage_change: "Variação %",
  date_difference: "Diferença de datas",
  date_add: "Somar a data",
  export_csv: "Exportar CSV",
  export_document: "Exportar documento",
};

// Frase curta para o estado "a trabalhar", no presente contínuo.
const TOOL_PROGRESS = {
  list_documents: "A ver que documentos existem",
  search_documents: "A pesquisar",
  read_document: "A ler o documento",
  calculate: "A calcular",
  percentage_change: "A calcular a variação",
  date_difference: "A contar o tempo entre datas",
  date_add: "A calcular a data",
  export_csv: "A preparar o CSV",
  export_document: "A preparar o documento",
};

const GUARD_LABELS = {
  documentos: "pergunta sobre documentos",
  seguimento: "seguimento da conversa",
  assistente: "pergunta sobre o assistente",
  conversa: "conversa",
  conhecimento_geral: "conhecimento geral",
  calculo: "cálculo",
  fora_do_ambito: "fora do âmbito",
  erro_guarda: "verificação indisponível",
};

function describeArguments(name, args = {}) {
  if (name === "search_documents") return `“${args.query}”`;
  if (name === "read_document") {
    if (args.page_start || args.page_end) return `p. ${args.page_start || 1}–${args.page_end || "fim"}`;
    return "documento completo";
  }
  if (name === "calculate") return args.expression;
  if (name === "export_csv" || name === "export_document") return args.filename;
  return "";
}

function StepIcon({ status }) {
  if (status === "running") return <Loader2 className="size-3.5 animate-spin text-stone-500" />;
  if (status === "stopped") return <Square className="size-3 text-stone-400" fill="currentColor" />;
  if (status === "error") return <X className="size-3.5 text-red-600" />;
  return <Check className="size-3.5 text-emerald-600" />;
}

function currentActivity(steps) {
  const running = [...steps].reverse().find((s) => s.type === "tool" && s.status === "running");
  if (running) {
    const args = describeArguments(running.name, running.arguments);
    return `${TOOL_PROGRESS[running.name] || TOOL_LABELS[running.name] || running.name}${args ? ` ${args}` : ""}`;
  }
  return "A pensar";
}

export default function AgentSteps({ steps, done, stopped }) {
  const [open, setOpen] = useState(false);
  if (!steps?.length) return null;

  const tools = steps.filter((s) => s.type === "tool");
  const blocked = steps.some((s) => s.type === "guard" && !s.allowed);
  const failed = tools.filter((s) => s.status === "error").length;

  let summary;
  if (!done) summary = `${currentActivity(steps)}…`;
  else if (stopped) summary = tools.length ? `Interrompido depois de ${tools.length} ferramenta${tools.length > 1 ? "s" : ""}` : "Interrompido";
  else if (blocked) summary = "Pedido fora do âmbito";
  else if (tools.length === 0) summary = "Respondeu sem usar ferramentas";
  else summary = `Usou ${tools.length} ferramenta${tools.length > 1 ? "s" : ""}${failed ? ` · ${failed} com erro` : ""}`;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="group flex items-center gap-1.5 text-sm text-stone-500 hover:text-stone-800"
      >
        {!done && <Loader2 className="size-3.5 animate-spin" />}
        <span className={done ? "" : "animate-pulse"}>{summary}</span>
        <ChevronRight className={`size-3.5 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>

      {open && (
        <ol className="animate-fade-up mt-2 space-y-2 border-l border-stone-200 pl-4 text-sm">
          {steps.map((step, i) => {
            if (step.type === "guard") {
              return (
                <li key={i} className="flex items-start gap-2">
                  {step.allowed ? (
                    <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
                  ) : (
                    <Ban className="mt-0.5 size-3.5 shrink-0 text-red-600" />
                  )}
                  <span>
                    Verificação de âmbito{" "}
                    <span className="text-stone-500">· {GUARD_LABELS[step.category] || step.category}</span>
                  </span>
                </li>
              );
            }
            if (step.type === "thinking") {
              return (
                <li key={i} className="whitespace-pre-wrap text-stone-500">
                  {step.text}
                </li>
              );
            }
            const args = describeArguments(step.name, step.arguments);
            return (
              <li key={step.id || i} className="flex items-start gap-2">
                <span className="mt-0.5 shrink-0">
                  <StepIcon status={step.status} />
                </span>
                <span className="min-w-0">
                  <span className="font-medium text-stone-800">{TOOL_LABELS[step.name] || step.name}</span>
                  {args && <span className="ml-1.5 break-words font-mono text-xs text-stone-500">{args}</span>}
                  {step.sideEffect && (
                    <span className="ml-1.5 inline-flex items-center gap-1 rounded bg-stone-100 px-1.5 py-0.5 text-xs text-stone-600">
                      <FilePlus2 className="size-3" />
                      cria ficheiro
                    </span>
                  )}
                  {step.summary && <span className="block text-stone-500">{step.summary}</span>}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
