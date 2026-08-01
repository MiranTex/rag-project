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

export async function askQuestionStream(payload, handlers) {
  const res = await fetch(`${API_BASE}/chat/ask-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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

    const events = parseSseChunk(chunk);
    for (const evt of events) {
      if (evt.event === "sources" && handlers?.onSources) {
        handlers.onSources(evt.data.sources || []);
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
      if (evt.event === "error") {
        throw new Error(evt.data.detail || "Erro no stream do servidor");
      }
    }
  }
}
