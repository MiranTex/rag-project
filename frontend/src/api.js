const API_BASE = "http://127.0.0.1:8000";

function parseSseChunk(chunkText) {
  const events = [];
  const blocks = chunkText.split("\n\n");
  for (const block of blocks) {
    if (!block.trim()) {
      continue;
    }

    const lines = block.split("\n");
    let eventName = "message";
    let dataText = "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      }
      if (line.startsWith("data:")) {
        dataText += line.slice(5).trim();
      }
    }

    if (!dataText) {
      continue;
    }

    try {
      events.push({ event: eventName, data: JSON.parse(dataText) });
    } catch {
      continue;
    }
  }
  return events;
}

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("Falha no health check");
  return res.json();
}

export async function getDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error("Falha ao listar documentos");
  return res.json();
}

export async function uploadDocument(file, reindex = false) {
  const form = new FormData();
  form.append("file", file);
  form.append("reindex", String(reindex));

  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    body: form,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha no upload");
  return data;
}

export async function deleteDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: "DELETE",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao apagar documento");
  return data;
}

export async function reindexDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/reindex`, {
    method: "POST",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao reindexar documento");
  return data;
}

export async function getExtraction(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/extraction`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao carregar extração");
  return data;
}

export async function updatePage(documentId, page, changes) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/pages/${page}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao guardar página");
  return data;
}

export async function rerunPageOcr(documentId, page, dpi = null) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/pages/${page}/ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dpi }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao repetir OCR");
  return data;
}

export async function updateMetadata(documentId, metadata) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/metadata`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao guardar a ficha");
  return data;
}

export async function suggestMetadata(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/metadata/suggest`, {
    method: "POST",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao preencher a ficha");
  return data;
}

export async function approveDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/approve`, {
    method: "POST",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao aprovar documento");
  return data;
}

export async function askQuestion(payload) {
  const res = await fetch(`${API_BASE}/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Falha ao perguntar");
  return data;
}

// `signal` (AbortController) cancela o pedido; o backend deixa de correr passos quando a ligação fecha.
async function streamEvents(path, payload, onEvent, signal) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!res.ok) {
    let detail = "Falha ao perguntar em stream";
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      detail = "Falha ao perguntar em stream";
    }
    throw new Error(detail);
  }

  if (!res.body) {
    throw new Error("Resposta sem stream disponível.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    const boundary = buffer.lastIndexOf("\n\n");
    if (boundary === -1) {
      continue;
    }

    const chunk = buffer.slice(0, boundary + 2);
    buffer = buffer.slice(boundary + 2);

    for (const evt of parseSseChunk(chunk)) {
      if (evt.event === "error") {
        throw new Error(evt.data.detail || "Erro no stream do servidor");
      }
      onEvent(evt);
    }
  }
}

export async function askQuestionStream(payload, handlers, signal) {
  await streamEvents("/chat/ask-stream", payload, (evt) => {
    if (evt.event === "sources" && handlers?.onSources) {
      handlers.onSources(evt.data.sources || []);
    }
    if (evt.event === "expanded_queries" && handlers?.onExpandedQueries) {
      handlers.onExpandedQueries(evt.data.expanded_queries || []);
    }
    if (evt.event === "diagnostics" && handlers?.onDiagnostics) {
      handlers.onDiagnostics(evt.data.retrieval_diagnostics || []);
    }
    if (evt.event === "token" && handlers?.onToken) {
      handlers.onToken(evt.data.token || "");
    }
    if (evt.event === "done" && handlers?.onDone) {
      handlers.onDone(evt.data.answer || "");
    }
  }, signal);
}

// Eventos: thinking, tool_call, tool_result, export, sources, answer, done.
export async function askAgentStream(payload, onEvent, signal) {
  await streamEvents("/agent/ask-stream", payload, onEvent, signal);
}

export async function getAgentProfiles() {
  const res = await fetch(`${API_BASE}/agent/profiles`);
  if (!res.ok) throw new Error("Falha ao listar perfis do agente");
  return res.json();
}

export function exportUrl(name) {
  return `${API_BASE}/exports/${encodeURIComponent(name)}`;
}
