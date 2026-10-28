import { useEffect, useState } from "react";
import {
  askAgentStream,
  askQuestionStream,
  deleteDocument,
  getAgentProfiles,
  getDocuments,
  getHealth,
  reindexDocument,
  uploadDocument,
} from "./api";
import ChatPanel from "./components/ChatPanel";
import UploadPanel from "./components/UploadPanel";

const CHAT_STORAGE_KEY = "rag-study-chat-history";
const AGENT_HISTORY_TURNS = 6;

export default function App() {
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploading, setUploading] = useState(false);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const [multiQuery, setMultiQuery] = useState(false);
  const [mode, setMode] = useState("agent");
  const [profiles, setProfiles] = useState([]);
  const [profile, setProfile] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(CHAT_STORAGE_KEY);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setMessages(parsed);
      }
    } catch {
      setMessages([]);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
  }, [messages]);

  async function refreshData() {
    const [healthData, docsData] = await Promise.all([getHealth(), getDocuments()]);
    setHealth(healthData);
    setDocuments(docsData);
  }

  useEffect(() => {
    refreshData().catch((err) => {
      setUploadStatus(`Erro inicial: ${err.message}`);
    });
    getAgentProfiles()
      .then((data) => {
        setProfiles(data);
        setProfile((current) => current || data[0]?.name || "");
      })
      .catch(() => setProfiles([]));
  }, []);

  function updateMessage(id, update) {
    setMessages((prev) => prev.map((msg) => (msg.id === id ? { ...msg, ...update(msg) } : msg)));
  }

  async function handleAskAgent(cleanQuestion) {
    const pendingIndex = Date.now();
    const history = messages
      .filter((msg) => msg.answer && !msg.answer.startsWith("Erro:"))
      .slice(-AGENT_HISTORY_TURNS)
      .map((msg) => ({ question: msg.question, answer: msg.answer }));

    setMessages((prev) => [
      ...prev,
      { id: pendingIndex, mode: "agent", question: cleanQuestion, answer: "", sources: [], steps: [], exports: [] },
    ]);

    try {
      await askAgentStream(
        {
          question: cleanQuestion,
          profile: profile || null,
          document_id: selectedDocument || null,
          history,
        },
        ({ event, data }) => {
          if (event === "thinking") {
            updateMessage(pendingIndex, (msg) => ({ steps: [...msg.steps, { type: "thinking", text: data.text }] }));
          }
          if (event === "tool_call") {
            updateMessage(pendingIndex, (msg) => ({
              steps: [
                ...msg.steps,
                { type: "tool", id: data.id, name: data.name, arguments: data.arguments, sideEffect: data.side_effect, status: "running" },
              ],
            }));
          }
          if (event === "tool_result") {
            updateMessage(pendingIndex, (msg) => ({
              steps: msg.steps.map((step) =>
                step.id === data.id ? { ...step, status: data.ok ? "ok" : "error", summary: data.summary } : step,
              ),
            }));
          }
          if (event === "export") {
            updateMessage(pendingIndex, (msg) => ({ exports: [...msg.exports, data] }));
          }
          if (event === "sources") {
            updateMessage(pendingIndex, () => ({ sources: data.sources || [] }));
          }
          if (event === "answer") {
            updateMessage(pendingIndex, () => ({ answer: data.answer }));
          }
        },
      );
      setQuestion("");
    } catch (err) {
      updateMessage(pendingIndex, () => ({ answer: `Erro: ${err.message}` }));
    }
  }

  async function handleUpload() {
    if (!selectedFile) {
      setUploadStatus("Escolhe um PDF antes de carregar.");
      return;
    }

    setUploading(true);
    setUploadStatus("A processar e indexar documento...");
    try {
      const result = await uploadDocument(selectedFile, false);
      setUploadStatus(result.message);
      setSelectedFile(null);
      await refreshData();
    } catch (err) {
      setUploadStatus(`Erro no upload: ${err.message}`);
    } finally {
      setUploading(false);
    }
  }

  async function handleAsk() {
    const cleanQuestion = question.trim();
    if (!cleanQuestion) {
      return;
    }

    setAsking(true);
    if (mode === "agent") {
      await handleAskAgent(cleanQuestion);
      setAsking(false);
      return;
    }

    const pendingIndex = Date.now();

    setMessages((prev) => [
      ...prev,
      {
        id: pendingIndex,
        mode: "rag",
        question: cleanQuestion,
        answer: "",
        sources: [],
        retrievalDiagnostics: [],
        expandedQueries: [],
      },
    ]);

    try {
      await askQuestionStream(
        {
          question: cleanQuestion,
          document_id: selectedDocument || null,
          include_debug: true,
          multi_query: multiQuery,
        },
        {
          onSources: (sources) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === pendingIndex ? { ...msg, sources } : msg,
              ),
            );
          },
          onExpandedQueries: (expandedQueries) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === pendingIndex ? { ...msg, expandedQueries } : msg,
              ),
            );
          },
          onDiagnostics: (retrievalDiagnostics) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === pendingIndex
                  ? {
                      ...msg,
                      retrievalDiagnostics,
                    }
                  : msg,
              ),
            );
          },
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === pendingIndex
                  ? {
                      ...msg,
                      answer: `${msg.answer}${token}`,
                    }
                  : msg,
              ),
            );
          },
          onDone: (finalAnswer) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === pendingIndex
                  ? {
                      ...msg,
                      answer: finalAnswer || msg.answer,
                    }
                  : msg,
              ),
            );
          },
        },
      );
      setQuestion("");
    } catch (err) {
      setMessages((prev) => [
        ...prev.map((msg) =>
          msg.id === pendingIndex
            ? {
                ...msg,
                answer: `Erro: ${err.message}`,
                sources: [],
                retrievalDiagnostics: [],
              }
            : msg,
        ),
      ]);
    } finally {
      setAsking(false);
    }
  }

  async function handleReindex(documentId) {
    setUploadStatus("A reindexar documento...");
    try {
      const result = await reindexDocument(documentId);
      setUploadStatus(result.message);
      await refreshData();
    } catch (err) {
      setUploadStatus(`Erro na reindexação: ${err.message}`);
    }
  }

  async function handleDelete(documentId) {
    setUploadStatus("A remover documento...");
    try {
      const result = await deleteDocument(documentId);
      if (selectedDocument === documentId) {
        setSelectedDocument("");
      }
      setUploadStatus(result.message);
      await refreshData();
    } catch (err) {
      setUploadStatus(`Erro ao remover: ${err.message}`);
    }
  }

  function handleClearChat() {
    setMessages([]);
    localStorage.removeItem(CHAT_STORAGE_KEY);
  }

  function handleExportChat() {
    const exportPayload = {
      exported_at: new Date().toISOString(),
      total_messages: messages.length,
      messages,
    };
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "rag-chat-history.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">RAG Study Lab</p>
        <h1>PDF para conhecimento pesquisável</h1>
        <p>
          Carrega documentos, indexa no Chroma e pergunta ao assistente, ou deixa o
          agente pesquisar, calcular e exportar resultados.
        </p>
        <div className="health-badge">
          API: {health?.status || "..."} | LLM: {String(health?.lmstudio)} |
          Chroma: {String(health?.chroma)}
        </div>
      </header>

      <section className="grid">
        <UploadPanel
          documents={documents}
          selectedDocument={selectedDocument}
          onSelectDocument={setSelectedDocument}
          uploadStatus={uploadStatus}
          onFileChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
          onUpload={handleUpload}
          onReindex={handleReindex}
          onDelete={handleDelete}
          loading={uploading}
        />

        <ChatPanel
          question={question}
          onQuestionChange={setQuestion}
          onAsk={handleAsk}
          onClear={handleClearChat}
          onExport={handleExportChat}
          asking={asking}
          messages={messages}
          multiQuery={multiQuery}
          onMultiQueryChange={setMultiQuery}
          mode={mode}
          onModeChange={setMode}
          profiles={profiles}
          profile={profile}
          onProfileChange={setProfile}
        />
      </section>
    </main>
  );
}
