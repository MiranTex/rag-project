import DocumentList, { UploadDropzone } from "../components/DocumentList";
import PageShell from "../components/PageShell";

export default function DocumentsPage({ documents, uploadingName, onUpload, canUpload, onOpenSidebar, ...listProps }) {
  return (
    <PageShell
      title="Documentos"
      description={
        canUpload
          ? "Carrega PDFs, revê o texto extraído e aprova-os para entrarem nas respostas do chat."
          : "Documentos da base de conhecimento e o estado de cada um."
      }
      onOpenSidebar={onOpenSidebar}
    >
      {canUpload && (
        <div className="mb-6">
          <UploadDropzone uploading={!!uploadingName} onUpload={onUpload} />
        </div>
      )}
      <DocumentList documents={documents} uploadingName={uploadingName} canUpload={canUpload} {...listProps} />
    </PageShell>
  );
}
