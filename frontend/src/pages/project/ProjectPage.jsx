import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FileText, LayoutDashboard, LogOut, MessageSquare, MessagesSquare, NotebookPen, PenLine, Settings2, Table2, Trash2, UserPlus } from "lucide-react";
import { research } from "../../api";
import PageShell from "../../components/PageShell";
import { Badge, Button, ErrorText, Menu, ROLE_LABELS, Spinner, Tabs, useConfirm } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";
import Conversations from "./Conversations";
import Documents from "./Documents";
import Matrix from "./Matrix";
import Notebook from "./Notebook";
import Overview from "./Overview";
import ProjectSettings from "./ProjectSettings";
import ShareDialog from "./ShareDialog";
import Writing from "./Writing";

// O separador ativo está no URL (/projetos/:id/caderno…): o refresh e o "voltar" do browser mantêm-no, e dá
// para enviar a ligação direta a alguém.
const TABS = [
  { value: "", label: "Visão geral", icon: LayoutDashboard },
  { value: "caderno", label: "Caderno", icon: NotebookPen },
  { value: "documentos", label: "Documentos", icon: FileText },
  { value: "conversas", label: "Conversas", icon: MessagesSquare },
  { value: "matriz", label: "Matriz", icon: Table2 },
  { value: "escrita", label: "Escrita", icon: PenLine },
];
// Separadores com trabalho por guardar ou resultados lentos de gerar: ficam montados (escondidos) ao sair deles.
const KEEP_MOUNTED = new Set(["caderno", "matriz", "escrita"]);

export default function ProjectPage({ currentUserId, onOpenSidebar }) {
  const { projectId, "*": rest = "" } = useParams();
  const tab = TABS.some((t) => t.value === rest.split("/")[0]) ? rest.split("/")[0] : "";
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { chatInProject, refreshProjects, projects } = useResearch();
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState(null); // "share" | "settings"
  const [visited, setVisited] = useState(() => new Set([tab]));

  const load = useCallback(() => research.project(projectId).then(setDetail, (err) => setError(err.message)), [projectId]);
  useEffect(() => {
    setDetail(null);
    setVisited(new Set([tab]));
    load();
  }, [load]);
  useEffect(() => {
    setVisited((prev) => (prev.has(tab) ? prev : new Set([...prev, tab])));
  }, [tab]);

  function update(next) {
    setDetail(next);
    refreshProjects();
  }

  function goTo(value) {
    navigate(`/projetos/${projectId}${value ? `/${value}` : ""}`);
  }

  async function leave() {
    const ok = await confirm({ title: "Sair do projeto?", message: "Deixas de ver este projeto. Para voltar, alguém tem de te convidar de novo.", confirmLabel: "Sair" });
    if (!ok) return;
    try {
      await research.removeMember(projectId, currentUserId);
      refreshProjects();
      navigate("/projetos");
    } catch (err) {
      setError(err.message);
    }
  }

  if (!detail) {
    return (
      <PageShell title="Projeto" back={{ to: "/projetos", label: "Projetos" }} onOpenSidebar={onOpenSidebar} width="wide">
        <ErrorText>{error}</ErrorText>
        {!error && <Spinner label="A carregar o projeto…" />}
      </PageShell>
    );
  }

  const { project } = detail;
  const canEdit = detail.my_role !== "viewer";
  const isOwner = detail.my_role === "owner";
  const summary = projects.find((p) => p.project.project_id === projectId);
  const tabs = TABS.map((t) => ({
    ...t,
    count: t.value === "caderno" ? summary?.item_count : t.value === "documentos" ? detail.documents.length : undefined,
  }));

  const panels = {
    "": () => <Overview detail={detail} currentUserId={currentUserId} onOpenSettings={() => setDialog("settings")} onShare={() => setDialog("share")} />,
    caderno: () => <Notebook projectId={projectId} structure={project.structure} canEdit={canEdit} currentUserId={currentUserId} isOwner={isOwner} />,
    documentos: () => <Documents detail={detail} onChange={update} onError={setError} />,
    conversas: () => <Conversations projectId={projectId} currentUserId={currentUserId} isOwner={isOwner} canChat />,
    matriz: () => <Matrix projectId={projectId} canEdit={canEdit} />,
    escrita: () => <Writing detail={detail} />,
  };

  return (
    <PageShell
      back={{ to: "/projetos", label: "Projetos" }}
      title={project.title}
      subtitle={project.question}
      width="wide"
      onOpenSidebar={onOpenSidebar}
      meta={
        <>
          <Badge tone={isOwner ? "accent" : "neutral"}>{ROLE_LABELS[detail.my_role]}</Badge>
          <button type="button" className="hover:text-stone-900 hover:underline dark:hover:text-stone-100" onClick={() => setDialog("share")}>
            {detail.members.length} {detail.members.length === 1 ? "pessoa" : "pessoas"}
          </button>
          <span>Atualizado {new Date(project.updated_at).toLocaleDateString("pt-PT")}</span>
        </>
      }
      actions={
        <>
          <span className="max-sm:hidden">
            <Button icon={UserPlus} onClick={() => setDialog("share")}>
              Partilhar
            </Button>
          </span>
          <Button variant="primary" icon={MessageSquare} onClick={() => chatInProject(projectId)} title="O assistente conhece o caderno e pesquisa nos documentos do projeto">
            Conversar
          </Button>
          <Menu
            label="Mais ações do projeto"
            items={[
              { label: "Partilhar", icon: UserPlus, onSelect: () => setDialog("share") },
              { label: canEdit ? "Definições" : "Ver definições", icon: Settings2, onSelect: () => setDialog("settings") },
              { label: "Sair do projeto", icon: LogOut, onSelect: leave, hidden: isOwner },
              { label: "Apagar projeto", icon: Trash2, onSelect: () => setDialog("settings"), danger: true, hidden: !isOwner },
            ]}
          />
        </>
      }
      tabs={<Tabs tabs={tabs} value={tab} onChange={goTo} inHeader label="Partes do projeto" />}
    >
      <ErrorText>{error}</ErrorText>
      {TABS.map(({ value }) => {
        const active = value === tab;
        if (!active && !(KEEP_MOUNTED.has(value) && visited.has(value))) return null;
        return (
          <div key={value} role="tabpanel" hidden={!active}>
            {panels[value]()}
          </div>
        );
      })}

      {dialog === "share" && (
        <ShareDialog
          detail={detail}
          currentUserId={currentUserId}
          onChange={update}
          onClose={() => setDialog(null)}
          onLeft={() => {
            refreshProjects();
            navigate("/projetos");
          }}
        />
      )}
      {dialog === "settings" && (
        <ProjectSettings
          detail={detail}
          onSaved={update}
          onClose={() => setDialog(null)}
          onDeleted={() => {
            refreshProjects();
            navigate("/projetos");
          }}
        />
      )}
    </PageShell>
  );
}
