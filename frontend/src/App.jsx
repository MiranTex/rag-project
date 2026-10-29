import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";
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
import ReviewPanel from "./components/ReviewPanel";
import Sidebar from "./components/Sidebar";

const CHAT_STORAGE_KEY = "rag-study-chat-history";
const AGENT_HISTORY_TURNS = 6;

function Notice({ notice, onDismiss }) {
  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(onDismiss, notice.tone === "error" ? 8000 : 4000);
    return () => clearTimeout(timer);
  }, [notice, onDismiss]);

  if (!notice) return null;
  const isError = notice.tone === "error";
  const Icon = isError ? AlertCircle : CheckCircle2;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[60] flex justify-center px-4">
      <div
        role="status"
        className={`animate-fade-up pointer-events-auto flex max-w-md items-start gap-2.5 rounded-xl border bg-white px-4 py-3 text-sm shadow-lg ${
          isError ? "border-red-200 text-red-800" : "border-stone-200 text-stone-800"
        }`}
      >
        <Icon className={`mt-0.5 size-4 shrink-0 ${isError ? "text-red-600" : "text-emerald-600"}`} />
        <span>{notice.text}</span>
        <button type="button" onClick={onDismiss} aria-label="Fechar aviso" className="text-stone-400 hover:text-stone-700">
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [notice, setNotice] = useState(null);
  const [uploadingName, setUploadingName] = useState("");
  const [reviewingDocument, setReviewingDocument] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

  const dismissNotice = useCallback(() => setNotice(null), []);

  function notify(text, tone = "ok") {
    setNotice({ text, tone, at: Date.now() });
  }

  async function refreshData() {
    const [healthData, docsData] = await Promise.all([
      getHealth().catch(() => ({ offline: true })),
      getDocuments(),
    ]);
    setHealth(healthData);
    setDocuments(docsData);
  }

  useEffect(() => {
    refreshData().catch(() => {
      setHealth({ offline: true });
      notify("Não foi possível ligar à API. Confirma que o backend está a correr.", "error");
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
          if (event === "guard") {
            updateMessage(pendingIndex, (msg) => ({
              steps: [...msg.steps, { type: "guard", category: data.category, allowed: data.allowed }],
            }));
          }
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
            updateMessage(pendingIndex, () => ({ answer: data.answer, blocked: !!data.blocked }));
          }
        },
      );
      setQuestion("");
    } catch (err) {
      updateMessage(pendingIndex, () => ({ answer: `Erro: ${err.message}` }));
    }
  }

  async function handleUpload(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      notify("Só são aceites ficheiros PDF.", "error");
      return;
    }

    setUploadingName(file.name);
    try {
      const result = await uploadDocument(file, false);
      notify(result.message);
      await refreshData();
      if (result.document.status === "pending_review") {
        setSidebarOpen(false);
        setReviewingDocument(result.document.document_id);
      }
    } catch (err) {
      notify(`Não foi possível carregar ${file.name}: ${err.message}`, "error");
    } finally {
      setUploadingName("");
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
    const doc = documents.find((d) => d.document_id === documentId);
    setUploadingName(doc?.filename || "Documento");
    try {
      const result = await reindexDocument(documentId);
      notify(result.message);
      await refreshData();
      if (result.document.status === "pending_review") {
        setSidebarOpen(false);
        setReviewingDocument(documentId);
      }
    } catch (err) {
      notify(`Não foi possível extrair de novo: ${err.message}`, "error");
    } finally {
      setUploadingName("");
    }
  }

  async function handleDelete(documentId) {
    try {
      const result = await deleteDocument(documentId);
      if (selectedDocument === documentId) {
        setSelectedDocument("");
      }
      notify(result.message);
      await refreshData();
    } catch (err) {
      notify(`Não foi possível remover: ${err.message}`, "error");
    }
  }

  async function handleReviewClosed(message) {
    setReviewingDocument(null);
    if (message) {
      notify(message);
    }
    await refreshData().catch(() => {});
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

  const indexedDocuments = documents.filter((d) => d.status === "indexed");

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        documents={documents}
        uploadingName={uploadingName}
        onUpload={handleUpload}
        onReview={(id) => {
          setSidebarOpen(false);
          setReviewingDocument(id);
        }}
        onReindex={handleReindex}
        onDelete={handleDelete}
        onNewChat={() => {
          handleClearChat();
          setSidebarOpen(false);
        }}
        health={health}
      />

      <ChatPanel
        messages={messages}
        asking={asking}
        onClear={handleClearChat}
        onExport={handleExportChat}
        onOpenSidebar={() => setSidebarOpen(true)}
        documents={indexedDocuments}
        pendingCount={documents.length - indexedDocuments.length}
        selectedDocument={selectedDocument}
        onSelectDocument={setSelectedDocument}
        question={question}
        onQuestionChange={setQuestion}
        onAsk={handleAsk}
        mode={mode}
        onModeChange={setMode}
        profiles={profiles}
        profile={profile}
        onProfileChange={setProfile}
        multiQuery={multiQuery}
        onMultiQueryChange={setMultiQuery}
      />

      {reviewingDocument && (
        <ReviewPanel
          documentId={reviewingDocument}
          onClose={() => handleReviewClosed()}
          onApproved={handleReviewClosed}
        />
      )}

      <Notice notice={notice} onDismiss={dismissNotice} />
    </div>
  );
}
