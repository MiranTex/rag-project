import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
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
  research,
  uploadDocument,
} from "./api";
import ChatPanel from "./components/ChatPanel";
import Login from "./components/Login";
import ReviewPanel from "./components/ReviewPanel";
import Sidebar from "./components/Sidebar";
import AccountPage from "./pages/AccountPage";
import DiscoverPage from "./pages/DiscoverPage";
import DocumentsPage from "./pages/DocumentsPage";
import FeedbackPage from "./pages/FeedbackPage";
import FilesPage from "./pages/FilesPage";
import ProjectsPage from "./pages/ProjectsPage";
import SearchPage from "./pages/SearchPage";
import SettingsPage from "./pages/SettingsPage";
import UsersPage from "./pages/UsersPage";
import InvitationPage from "./pages/InvitationPage";
import ProjectPage from "./pages/project/ProjectPage";
import { ResearchProvider } from "./research/ResearchContext";
import { ConfirmProvider, useConfirm } from "./components/ui";
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
const USERS_MANAGE = "users:manage";
const SETTINGS_MANAGE = "settings:manage";
const RESEARCH_USE = "research:use";
const FEEDBACK_READ = "feedback:read";

function Workspace({ session, authConfig, onLogout }) {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const can = (permission) => session.permissions.includes(permission);
  const canReadDocuments = can(DOCUMENTS_READ);
  // Cada utilizador tem a sua conversa guardada no browser.
  const CHAT_STORAGE_KEY = `${CHAT_STORAGE_PREFIX}:${session.user.user_id}`;
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [notice, setNotice] = useState(null);
  const [uploadingName, setUploadingName] = useState("");
  const [reviewingDocument, setReviewingDocument] = useState(null);
  // Projeto de pesquisa onde o chat pesquisa ("" = toda a base).
  const [activeProjectId, setActiveProjectId] = useState(() => {
    try {
      return localStorage.getItem(`${CHAT_STORAGE_KEY}:project`) || "";
    } catch {
      return "";
    }
  });
  useEffect(() => {
    try {
      if (activeProjectId) localStorage.setItem(`${CHAT_STORAGE_KEY}:project`, activeProjectId);
      else localStorage.removeItem(`${CHAT_STORAGE_KEY}:project`);
    } catch {
      // Sem localStorage o projeto ativo dura só enquanto a página estiver aberta.
    }
  }, [activeProjectId]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useTheme();

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const abortRef = useRef(null);
  const [multiQuery, setMultiQuery] = useState(false);
  // Identifica a conversa na memória de sessão do backend; por utilizador, como o histórico do chat.
  const [sessionId] = useState(() => {
    const key = `rag-study-session-id:${session.user.user_id}`;
    const created = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      const existing = localStorage.getItem(key);
      if (existing) return existing;
      localStorage.setItem(key, created);
    } catch {
      // Sem localStorage a memória dura só enquanto a página estiver aberta.
    }
    return created;
  });
  // Conversa guardada no projeto ativo: { id, projectId, title, canEdit } ou null (ainda não guardada).
  const [conversation, setConversation] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(`${CHAT_STORAGE_KEY}:conversation`)) || null;
    } catch {
      return null;
    }
  });
  const lastSavedRef = useRef("");
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

  useEffect(() => {
    try {
      if (conversation) localStorage.setItem(`${CHAT_STORAGE_KEY}:conversation`, JSON.stringify(conversation));
      else localStorage.removeItem(`${CHAT_STORAGE_KEY}:conversation`);
    } catch {
      // Sem localStorage, a ligação à conversa dura só enquanto a página estiver aberta.
    }
  }, [conversation]);

  // Ao mudar de projeto (ou sair dele), as perguntas seguintes vão para outra conversa.
  useEffect(() => {
    if (conversation && conversation.projectId !== activeProjectId) setConversation(null);
  }, [activeProjectId]);

  // As perguntas feitas num projeto ficam guardadas numa conversa do projeto, visível aos outros membros.
  // Guarda quando a resposta termina (e quando se aceita/rejeita uma proposta).
  useEffect(() => {
    const projectId = conversation?.projectId || activeProjectId;
    if (asking || !projectId || !can(RESEARCH_USE)) return undefined;
    const toSave = messages
      .filter((m) => m.projectId === projectId && (m.answer || m.stopped))
      .map(({ retrievalDiagnostics, ...m }) => m);
    if (!toSave.length) return undefined;
    const snapshot = JSON.stringify([conversation?.id || "", toSave]);
    if (snapshot === lastSavedRef.current) return undefined;
    const timer = setTimeout(async () => {
      lastSavedRef.current = snapshot;
      try {
        if (conversation?.id && conversation.canEdit) {
          await research.saveConversation(projectId, conversation.id, { messages: toSave });
        } else {
          // Nova conversa, ou continuação de uma conversa de outra pessoa (fica uma cópia tua).
          const created = await research.createConversation(projectId, { messages: toSave });
          lastSavedRef.current = JSON.stringify([created.conversation_id, toSave]);
          setConversation({ id: created.conversation_id, projectId, title: created.title, canEdit: true });
        }
      } catch (err) {
        lastSavedRef.current = "";
        notify(`A conversa não ficou guardada no projeto: ${err.message}`, "error");
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [messages, asking, activeProjectId, conversation]);

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
      {
        id: pendingIndex,
        mode: "agent",
        question: cleanQuestion,
        answer: "",
        sources: [],
        steps: [],
        exports: [],
        projectId: activeProjectId || null,
      },
    ]);

    try {
      await askAgentStream(
        {
          question: cleanQuestion,
          profile: profile || null,
          project_id: activeProjectId || null,
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
          if (event === "proposal") {
            updateMessage(pendingIndex, (msg) => ({ proposals: [...(msg.proposals || []), data] }));
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
        projectId: activeProjectId || null,
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
          project_id: activeProjectId || null,
          include_debug: true,
          multi_query: multiQuery,
          session_id: sessionId,
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
    setConversation(null);
    lastSavedRef.current = "";
    localStorage.removeItem(CHAT_STORAGE_KEY);
  }

  // Abre uma conversa guardada no projeto para a continuar no chat.
  async function openConversation(projectId, conversationId) {
    const saved = await research.conversation(projectId, conversationId);
    handleStop();
    setActiveProjectId(projectId);
    setConversation({ id: saved.conversation_id, projectId, title: saved.title, canEdit: saved.can_edit });
    lastSavedRef.current = JSON.stringify([saved.conversation_id, saved.messages]);
    setMessages(saved.messages);
    navigate("/");
  }

  // Conversar no projeto: continua a conversa atual se já for deste projeto, senão começa uma nova. `draft`
  // deixa uma pergunta começada na caixa (ex.: "Sobre RF-003: "). É o agente que lê o caderno, por isso fica nesse modo.
  function chatInProject(projectId, draft = "") {
    if (activeProjectId !== projectId || !messages.every((m) => m.projectId === projectId)) handleClearChat();
    setActiveProjectId(projectId);
    setMode("agent");
    if (draft) setQuestion(draft);
    navigate("/");
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
  const attentionCount = documents.filter((d) => d.status === "pending_review" || d.status === "failed").length;
  const pages = {
    documents: canReadDocuments,
    research: can(RESEARCH_USE),
    users: can(USERS_MANAGE),
    settings: can(SETTINGS_MANAGE),
    feedback: can(FEEDBACK_READ),
  };
  const openSidebar = () => setSidebarOpen(true);

  return (
    <ResearchProvider
      notify={notify}
      activeProjectId={activeProjectId}
      setActiveProjectId={setActiveProjectId}
      chat={{ conversation, openConversation, chatInProject, newChat: handleClearChat }}
    >
      <div className="flex h-full overflow-hidden">
        <Sidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewChat={async () => {
            // Numa conversa de projeto nada se perde (fica no projeto); fora dele, a conversa só existe neste browser.
            if (messages.length && !conversation && !(await confirm({ title: "Começar uma conversa nova?", message: "Esta conversa não está guardada em nenhum projeto e vai ser apagada.", confirmLabel: "Apagar e começar" }))) return;
            handleClearChat();
            setActiveProjectId("");
            setSidebarOpen(false);
            navigate("/");
          }}
          health={health}
          theme={theme}
          onThemeChange={setTheme}
          pages={pages}
          attentionCount={attentionCount}
          user={session.user}
          canChangePassword={authConfig.mode === "local"}
          onLogout={onLogout}
        />

        <Routes>
          <Route
            path="/"
            element={
              <ChatPanel
                messages={messages}
                asking={asking}
                onClear={handleClearChat}
                onExport={handleExportChat}
                onOpenSidebar={openSidebar}
                documents={indexedDocuments}
                pendingCount={documents.length - indexedDocuments.length}
                knowsDocuments={canReadDocuments}
                canCreateProject={can(RESEARCH_USE)}
                onMessageChange={updateMessage}
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
            }
          />
          {pages.documents && (
            <Route
              path="/documentos"
              element={
                <DocumentsPage
                  documents={documents}
                  uploadingName={uploadingName}
                  onUpload={handleUpload}
                  canUpload={can(DOCUMENTS_UPLOAD)}
                  canReview={can(DOCUMENTS_REVIEW)}
                  onReview={setReviewingDocument}
                  onRename={handleRename}
                  onReindex={handleReindex}
                  onDelete={handleDelete}
                  onOpenSidebar={openSidebar}
                />
              }
            />
          )}
          {pages.research && (
            <>
              <Route path="/pesquisa" element={<SearchPage onOpenSidebar={openSidebar} />} />
              <Route path="/descobrir" element={<DiscoverPage onOpenSidebar={openSidebar} />} />
              <Route path="/projetos" element={<ProjectsPage onOpenSidebar={openSidebar} />} />
              <Route
                path="/projetos/:projectId/*"
                element={<ProjectPage currentUserId={session.user.user_id} onOpenSidebar={openSidebar} />}
              />
            </>
          )}
          <Route path="/ficheiros" element={<FilesPage onOpenSidebar={openSidebar} />} />
          {pages.feedback && <Route path="/avaliacoes" element={<FeedbackPage onOpenSidebar={openSidebar} />} />}
          {pages.users && (
            <Route
              path="/utilizadores"
              element={<UsersPage authConfig={authConfig} currentUserId={session.user.user_id} onOpenSidebar={openSidebar} />}
            />
          )}
          {pages.settings && (
            <Route path="/configuracoes" element={<SettingsPage onOpenSidebar={openSidebar} onSaved={notify} />} />
          )}
          {authConfig.mode === "local" && (
            <Route path="/conta" element={<AccountPage user={session.user} onOpenSidebar={openSidebar} onSaved={notify} />} />
          )}
          {/* Página sem permissão ou inexistente: volta ao chat. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

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
    </ResearchProvider>
  );
}

export default function App() {
  const location = useLocation();
  // undefined: a verificar a sessão; null: sem sessão (mostra o login).
  const [session, setSession] = useState(undefined);
  const [authConfig, setAuthConfig] = useState({ mode: "local", roles_from_token: false });
  const [loginMessage, setLoginMessage] = useState("");

  useEffect(() => {
    onUnauthorized(() => {
      setLoginMessage("A sessão terminou. Entra de novo.");
      setSession(null);
    });
    getAuthConfig()
      .then(setAuthConfig)
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
  // O link de um convite abre-se com ou sem sessão (quem não tem conta pode criá-la a partir dele).
  const invitation = location.pathname.match(/^\/convite\/([^/]+)/);
  if (invitation) {
    return (
      <InvitationPage
        token={decodeURIComponent(invitation[1])}
        session={session}
        authMode={authConfig.mode}
        onLoggedIn={(info) => {
          setLoginMessage("");
          setSession(info);
        }}
      />
    );
  }
  if (!session) {
    return (
      <Login
        mode={authConfig.mode}
        message={loginMessage}
        onLoggedIn={(info) => {
          setLoginMessage("");
          setSession(info);
        }}
      />
    );
  }
  // key: ao trocar de utilizador, o estado (conversa, documentos) começa do zero.
  return (
    <ConfirmProvider>
      <Workspace key={session.user.user_id} session={session} authConfig={authConfig} onLogout={handleLogout} />
    </ConfirmProvider>
  );
}
