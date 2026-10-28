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

const STATUS_ICON = { running: "…", ok: "✓", error: "✕" };

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
  if (name === "search_documents") return `"${args.query}"`;
  if (name === "read_document") {
    if (args.page_start || args.page_end) return `p.${args.page_start || 1}–${args.page_end || "fim"}`;
    return "documento completo";
  }
  if (name === "calculate") return args.expression;
  if (name === "export_csv" || name === "export_document") return args.filename;
  return "";
}

export default function AgentSteps({ steps }) {
  if (!steps?.length) return null;

  return (
    <ol className="agent-steps">
      {steps.map((step, i) =>
        step.type === "guard" ? (
          <li key={i} className={`agent-step agent-step-${step.allowed ? "ok" : "error"}`}>
            <span className="agent-step-icon">{step.allowed ? "✓" : "⛔"}</span>
            <span className="agent-step-name">Verificação de âmbito</span>
            <span className="agent-step-args">{GUARD_LABELS[step.category] || step.category}</span>
          </li>
        ) : step.type === "thinking" ? (
          <li key={i} className="agent-step agent-step-thinking">
            {step.text}
          </li>
        ) : (
          <li key={step.id || i} className={`agent-step agent-step-${step.status}`}>
            <span className="agent-step-icon">{STATUS_ICON[step.status]}</span>
            <span className="agent-step-name">
              {TOOL_LABELS[step.name] || step.name}
              {step.sideEffect && <span className="agent-step-badge">cria ficheiro</span>}
            </span>
            <span className="agent-step-args">{describeArguments(step.name, step.arguments)}</span>
            {step.summary && <span className="agent-step-summary">{step.summary}</span>}
          </li>
        ),
      )}
    </ol>
  );
}
