import { useNavigate } from "react-router-dom";
import { BookOpen, Compass, FileText, Pin, Search, X } from "lucide-react";
import { research } from "../../api";
import { Badge, Button, EmptyState, IconButton, documentLabel, useConfirm } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";

// Documentos fixados no projeto: é só neles que o assistente e a pesquisa do projeto procuram.
export default function Documents({ detail, onChange, onError }) {
  const { openReader } = useResearch();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { project } = detail;
  const canEdit = detail.my_role !== "viewer";

  async function unpin(doc) {
    const ok = await confirm({
      title: "Retirar do projeto?",
      message: `"${documentLabel(doc)}" deixa de ser usado pelo assistente neste projeto. O documento continua na base.`,
      confirmLabel: "Retirar",
    });
    if (ok) research.unpin(project.project_id, doc.document_id).then(onChange, (err) => onError(err.message));
  }

  const howToAdd = (
    <div className="flex flex-wrap justify-center gap-2">
      <Button icon={Search} onClick={() => navigate("/pesquisa")}>
        Pesquisar
      </Button>
      <Button icon={Compass} onClick={() => navigate("/descobrir")}>
        Descobrir
      </Button>
    </div>
  );

  if (!detail.documents.length) {
    return (
      <EmptyState icon={Pin} title="Ainda sem documentos fixados" action={canEdit && howToAdd}>
        Fixa documentos a partir da Pesquisa, do Descobrir ou do leitor ("Fixar no projeto"). O assistente do projeto procura só neles.
      </EmptyState>
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-sm text-stone-500 dark:text-stone-400">O assistente e a pesquisa do projeto procuram só nestes documentos.</p>
        {canEdit && howToAdd}
      </div>
      <ul className="divide-y divide-stone-200 overflow-hidden rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
        {detail.documents.map((doc) => (
          <li key={doc.document_id} className="flex items-center gap-3 px-4 py-3">
            <FileText className="size-5 shrink-0 text-stone-400" />
            <div className="min-w-0 flex-1">
              <button type="button" className="block max-w-full truncate text-left text-sm font-medium hover:underline" onClick={() => openReader({ document_id: doc.document_id, page: 1 })}>
                {documentLabel(doc)}
              </button>
              <p className="truncate text-xs text-stone-500 dark:text-stone-400">
                {[doc.authors.join(", "), doc.year, doc.page_count ? `${doc.page_count} páginas` : ""].filter(Boolean).join(" · ")}
              </p>
            </div>
            {doc.document_type && <Badge tone="outline">{doc.document_type}</Badge>}
            <IconButton icon={BookOpen} label="Abrir no leitor" onClick={() => openReader({ document_id: doc.document_id, page: 1 })} />
            {canEdit && <IconButton icon={X} label="Retirar do projeto" onClick={() => unpin(doc)} />}
          </li>
        ))}
      </ul>
    </>
  );
}
