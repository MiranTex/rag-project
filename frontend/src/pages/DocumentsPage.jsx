import { FileText } from "lucide-react";
import DocumentList, { UploadButton, UploadDropTarget } from "../components/DocumentList";
import PageShell from "../components/PageShell";
import { EmptyState } from "../components/ui";

export default function DocumentsPage({ documents, uploadingName, onUpload, canUpload, onOpenSidebar, ...listProps }) {
  const uploading = !!uploadingName;
  const empty = documents.length === 0 && !uploading;
  const content = empty ? (
    <EmptyState
      icon={FileText}
      title="Ainda não há documentos"
      action={canUpload && <UploadButton uploading={uploading} onUpload={onUpload} />}
    >
      {canUpload ? "Carrega PDFs (ou arrasta-os para aqui). Depois de revistos e aprovados, entram nas respostas do chat." : "Quando forem carregados documentos, aparecem aqui."}
    </EmptyState>
  ) : (
    <DocumentList documents={documents} uploadingName={uploadingName} canUpload={canUpload} {...listProps} />
  );

  return (
    <PageShell
      title="Documentos"
      subtitle={
        canUpload
          ? "Carrega PDFs, revê o texto extraído e aprova-os para entrarem nas respostas do chat. Também podes arrastar ficheiros para a lista."
          : "Documentos da base de conhecimento e o estado de cada um."
      }
      actions={canUpload && !empty && <UploadButton uploading={uploading} onUpload={onUpload} />}
      onOpenSidebar={onOpenSidebar}
    >
      {canUpload ? (
        <UploadDropTarget uploading={uploading} onUpload={onUpload}>
          {content}
        </UploadDropTarget>
      ) : (
        content
      )}
    </PageShell>
  );
}
