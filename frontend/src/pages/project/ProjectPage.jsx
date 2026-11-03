import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MessageSquare } from "lucide-react";
import { research } from "../../api";
import PageShell from "../../components/PageShell";
import { Button, ErrorText, Spinner, Tabs } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";
import Matrix from "./Matrix";
import Notebook from "./Notebook";
import Overview from "./Overview";
import Writing from "./Writing";

const TABS = [
  { value: "overview", label: "Resumo" },
  { value: "notebook", label: "Caderno" },
  { value: "matrix", label: "Matriz" },
  { value: "write", label: "Escrever" },
];

export default function ProjectPage({ currentUserId, onOpenSidebar }) {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { setActiveProjectId, refreshProjects } = useResearch();
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("overview");
  const [error, setError] = useState("");

  const load = useCallback(() => research.project(projectId).then(setDetail, (err) => setError(err.message)), [projectId]);
  useEffect(() => {
    load();
  }, [load]);

  function update(next) {
    setDetail(next);
    refreshProjects();
  }

  const canEdit = detail && detail.my_role !== "viewer";

  return (
    <PageShell
      title={detail?.project.title || "Projeto"}
      onOpenSidebar={onOpenSidebar}
      actions={
        detail && (
          <Button
            variant="primary"
            icon={MessageSquare}
            disabled={!detail.documents.length}
            title={detail.documents.length ? "O chat pesquisa só nos documentos deste projeto" : "Fixa documentos primeiro"}
            onClick={() => {
              setActiveProjectId(projectId);
              navigate("/");
            }}
          >
            Conversar
          </Button>
        )
      }
    >
      <ErrorText>{error}</ErrorText>
      {!detail && !error && <Spinner label="A carregar o projeto…" />}
      {detail && (
        <>
          <Tabs tabs={TABS} value={tab} onChange={setTab} />
          {tab === "overview" && (
            <Overview
              detail={detail}
              canEdit={canEdit}
              currentUserId={currentUserId}
              onChange={update}
              onDeleted={() => {
                refreshProjects();
                navigate("/projetos");
              }}
            />
          )}
          {tab === "notebook" && <Notebook projectId={projectId} canEdit={canEdit} currentUserId={currentUserId} isOwner={detail.my_role === "owner"} />}
          {tab === "matrix" && <Matrix projectId={projectId} canEdit={canEdit} />}
          {tab === "write" && <Writing detail={detail} />}
        </>
      )}
    </PageShell>
  );
}
