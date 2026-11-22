import { useEffect, useState } from "react";
import { FileDown, FolderOpen } from "lucide-react";
import { downloadExport, listExports } from "../api";
import PageShell from "../components/PageShell";
import { EmptyState, ErrorText, IconButton, ListCard, Spinner } from "../components/ui";

const formatSize = (bytes) => (bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

// Ficheiros gerados para a pessoa: exports do agente, esqueletos, estado da arte, matriz, bibliografia.
export default function FilesPage({ onOpenSidebar }) {
  const [files, setFiles] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listExports().then(setFiles, (err) => setError(err.message));
  }, []);

  return (
    <PageShell title="Ficheiros" subtitle="O que geraste: exports do agente, esqueletos, rascunhos, matrizes e bibliografias. Só tu os vês." onOpenSidebar={onOpenSidebar}>
      <ErrorText>{error}</ErrorText>
      {!files && !error && <Spinner label="A carregar…" />}
      {files && files.length === 0 && (
        <EmptyState icon={FolderOpen} title="Ainda não geraste ficheiros">
          Os exports do agente e o que gerares num projeto (esqueletos, matrizes, bibliografias) aparecem aqui.
        </EmptyState>
      )}
      {files && files.length > 0 && (
        <ListCard>
          {files.map((file) => (
            <li key={file.name} className="flex items-center gap-3 py-2 pl-4 pr-2 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-stone-800 dark:text-stone-200">{file.name}</span>
                <span className="block text-xs text-stone-500 dark:text-stone-400">
                  {formatSize(file.size)} · {new Date(file.created_at).toLocaleString("pt-PT")}
                </span>
              </span>
              <IconButton icon={FileDown} label={`Descarregar ${file.name}`} onClick={() => downloadExport(file.name).catch((err) => setError(err.message))} />
            </li>
          ))}
        </ListCard>
      )}
    </PageShell>
  );
}
