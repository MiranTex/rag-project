import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";
import {
  askAgentStream,
  askQuestionStream,
  deleteDocument,
  getAgentProfiles,
  getAuthConfig,
  getDocuments,
  getHealth,
  getMe,
  hasToken,
  onUnauthorized,
  setToken,
  reindexDocument,
  renameDocument,
  uploadDocument,
} from "./api";
import ChatPanel from "./components/ChatPanel";
import Login from "./components/Login";
import ReviewPanel from "./components/ReviewPanel";
import Sidebar from "./components/Sidebar";
import { useTheme } from "./theme";

const CHAT_STORAGE_PREFIX = "rag-study-chat-history";
const AGENT_HISTORY_TURNS = 6;

function isAbort(err) {
  return err?.name === "AbortError";
}

// Mensagem interrompida pelo utilizador: fica o que já chegou e os passos a meio deixam de aparecer "a correr".
function markStopped(msg) {
  return {
    stopped: true,
    steps: msg.steps?.map((step) => (step.status === "running" ? { ...step, status: "stopped" } : step)),
  };
}

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
        className={`animate-fade-up pointer-events-auto flex max-w-md items-start gap-2.5 rounded-xl border bg-white dark:bg-stone-800 px-4 py-3 text-sm shadow-lg dark:shadow-black/40 ${
          isError ? "border-red-200 dark:border-red-900 text-red-800 dark:text-red-300" : "border-stone-200 dark:border-stone-800 text-stone-800 dark:text-stone-200"
        }`}
      >
        <Icon className={`mt-0.5 size-4 shrink-0 ${isError ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}`} />
        <span>{notice.text}</span>
        <button type="button" onClick={onDismiss} aria-label="Fechar aviso" className="text-stone-400 dark:text-stone-500 hover:text-stone-700 dark:hover:text-stone-300">
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}

// Permissões do backend (backend/auth/permissions.py).
const DOCUMENTS_READ = "documents:read";
const DOCUMENTS_UPLOAD = "documents:upload";
const DOCUMENTS_REVIEW = "documents:review";
const DOCUMENTS_APPROVE = "documents:approve";
const CHAT_SELECT_DOCUMENT = "chat:select_document";

function Workspace({ session, onLogout }) {
  const can = (permission) => session.permissions.includes(permission);
  const canReadDocuments = can(DOCUMENTS_READ);
  const canSelectDocument = can(CHAT_SELECT_DOCUMENT);
  // Cada utilizador tem a sua conversa guardada no browser.
  const CHAT_STORAGE_KEY = `${CHAT_STORAGE_PREFIX}:${session.user.user_id}`;
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [notice, setNotice] = useState(null);
  const [uploadingName, setUploadingName] = useState("");
  const [reviewingDocument, setReviewingDocument] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useTheme();

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const abortRef = useRef(null);
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
  const previousStatuses = useRef({});

  // Enquanto houver documentos a extrair ou a indexar, a lista atualiza-se sozinha.
  const processing = documents.some((d) => d.status === "extracting" || d.status === "indexing");
  useEffect(() => {
    if (!processing) return undefined;
    const timer = setInterval(() => {
      getDocuments().then(setDocuments).catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [processing]);

  // Avisa quando um trabalho em background termina.
  useEffect(() => {
    const before = previousStatuses.current;
    for (const doc of documents) {
      const was = before[doc.document_id];
      if (!was || was === doc.status || !["extracting", "indexing"].includes(was)) continue;
      const name = doc.filename.replace(/\.pdf$/i, "");
      if (doc.status === "failed") notify(`${name}: a extração falhou. ${doc.error}`, "error");
      else if (doc.error) notify(`${name}: ${doc.error}`, "error");
      else if (doc.status === "pending_review") notify(`${name} está pronto para revisão.`);
      else if (doc.status === "indexed") notify(`${name} foi indexado.`);
    }
    previousStatuses.current = Object.fromEntries(documents.map((d) => [d.document_id, d.status]));
  }, [documents]);

  function notify(text, tone = "ok") {
    setNotice({ text, tone, at: Date.now() });
  }

  async function refreshData() {
    // Quem só usa o chat não vê a lista de documentos.
    const [healthData, docsData] = await Promise.all([
      getHealth().catch(() => ({ offline: true })),
      canReadDocuments ? getDocuments() : Promise.resolve([]),
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

  async function handleAskAgent(cleanQuestion, signal) {
    const pendingIndex = Date.now();
    const history = messages
      .filter((msg) => msg.answer && !msg.stopped && !msg.answer.startsWith("Erro:"))
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
          document_id: (canSelectDocument && selectedDocument) || null,
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
        signal,
      );
    } catch (err) {
      if (isAbort(err)) {
        updateMessage(pendingIndex, markStopped);
      } else {
        updateMessage(pendingIndex, () => ({ answer: `Erro: ${err.message}` }));
      }
    }
  }

  // O envio é rápido: a extração (OCR, ficha) corre em background e a lista vai mostrando o estado.
  async function handleUpload(files) {
    const pdfs = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length < files.length) {
      notify("Só são aceites ficheiros PDF; os outros foram ignorados.", "error");
    }
    if (!pdfs.length) return;

    const failed = [];
    let lastMessage = "";
    for (const [index, file] of pdfs.entries()) {
      setUploadingName(pdfs.length > 1 ? `${file.name} (${index + 1} de ${pdfs.length})` : file.name);
      try {
        lastMessage = (await uploadDocument(file, false)).message;
      } catch (err) {
        failed.push(`${file.name}: ${err.message}`);
      }
    }
    setUploadingName("");
    await refreshData().catch(() => {});
    if (failed.length) {
      notify(`Não foi possível carregar ${failed.join("; ")}`, "error");
    } else {
      notify(pdfs.length > 1 ? `${pdfs.length} documentos na fila para extração.` : lastMessage);
    }
  }

  async function handleAsk() {
    const cleanQuestion = question.trim();
    if (!cleanQuestion || asking) {
      return;
    }

    // Como nos chats comuns: a pergunta sai logo da caixa e passa para a conversa.
    setQuestion("");
    setAsking(true);
    const controller = new AbortController();
    abortRef.current = controller;

    if (mode === "agent") {
      await handleAskAgent(cleanQuestion, controller.signal);
      abortRef.current = null;
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
          document_id: (canSelectDocument && selectedDocument) || null,
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
        controller.signal,
      );
    } catch (err) {
      if (isAbort(err)) {
        updateMessage(pendingIndex, markStopped);
        return;
      }
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
      abortRef.current = null;
      setAsking(false);
    }
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  async function handleReindex(documentId) {
    try {
      const result = await reindexDocument(documentId);
      notify(result.message);
      await refreshData();
    } catch (err) {
      notify(`Não foi possível extrair de novo: ${err.message}`, "error");
    }
  }

  async function handleRename(documentId, name) {
    try {
      const doc = await renameDocument(documentId, name);
      notify(`Renomeado para ${doc.filename}`);
      await refreshData();
    } catch (err) {
      notify(`Não foi possível renomear: ${err.message}`, "error");
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
    handleStop();
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
        onRename={handleRename}
        onReindex={handleReindex}
        onDelete={handleDelete}
        onNewChat={() => {
          handleClearChat();
          setSidebarOpen(false);
        }}
        health={health}
        theme={theme}
        onThemeChange={setTheme}
        canReadDocuments={canReadDocuments}
        canUpload={can(DOCUMENTS_UPLOAD)}
        canReview={can(DOCUMENTS_REVIEW)}
        user={session.user}
        onLogout={onLogout}
      />

      <ChatPanel
        messages={messages}
        asking={asking}
        onClear={handleClearChat}
        onExport={handleExportChat}
        onOpenSidebar={() => setSidebarOpen(true)}
        documents={indexedDocuments}
        pendingCount={documents.length - indexedDocuments.length}
        knowsDocuments={canReadDocuments}
        canSelectDocument={canSelectDocument}
        selectedDocument={selectedDocument}
        onSelectDocument={setSelectedDocument}
        question={question}
        onQuestionChange={setQuestion}
        onAsk={handleAsk}
        onStop={handleStop}
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
          canReview={can(DOCUMENTS_REVIEW)}
          canApprove={can(DOCUMENTS_APPROVE)}
        />
      )}

      <Notice notice={notice} onDismiss={dismissNotice} />
    </div>
  );
}

export default function App() {
  // undefined: a verificar a sessão; null: sem sessão (mostra o login).
  const [session, setSession] = useState(undefined);
  const [authMode, setAuthMode] = useState("local");
  const [loginMessage, setLoginMessage] = useState("");

  useEffect(() => {
    onUnauthorized(() => {
      setLoginMessage("A sessão terminou. Entra de novo.");
      setSession(null);
    });
    getAuthConfig()
      .then((config) => setAuthMode(config.mode))
      .catch(() => {});
    if (!hasToken()) {
      setSession(null);
      return;
    }
    getMe()
      .then(setSession)
      .catch(() => setSession(null));
  }, []);

  function handleLogout() {
    setToken(null);
    setLoginMessage("");
    setSession(null);
  }

  if (session === undefined) return null;
  if (!session) {
    return (
      <Login
        mode={authMode}
        message={loginMessage}
        onLoggedIn={(info) => {
          setLoginMessage("");
          setSession(info);
        }}
      />
    );
  }
  // key: ao trocar de utilizador, o estado (conversa, documentos) começa do zero.
  return <Workspace key={session.user.user_id} session={session} onLogout={handleLogout} />;
}
