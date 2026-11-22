// Origem do conteúdo de uma proposta do agente (e da entrada do caderno, depois de aceite, em source.basis).
// Só as que não vêm (só) dos documentos levam etiqueta no caderno: são as que precisam de ser verificadas.
export const BASIS = {
  documents: { label: "Dos documentos", tone: "success", title: "Conteúdo tirado dos documentos, com citações." },
  mixed: { label: "Documentos + assistente", tone: "warning", title: "Parte vem dos documentos (citada) e parte é contributo do assistente." },
  assistant: { label: "Sugestão do assistente", tone: "warning", title: "Contributo do assistente (ideia, rascunho, conhecimento geral): não vem dos documentos." },
};
