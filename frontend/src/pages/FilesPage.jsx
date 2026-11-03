import { useEffect, useState } from "react";
import { FileDown } from "lucide-react";
import { downloadExport, listExports } from "../api";
import PageShell from "../components/PageShell";
import { Button, Empty, ErrorText, Spinner } from "../components/ui";

const formatSize = (bytes) => (bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

// Ficheiros gerados para a pessoa: exports do agente, esqueletos, estado da arte, matriz, bibliografia.
export default function FilesPage({ onOpenSidebar }) {
  const [files, setFiles] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listExports().then(setFiles, (err) => setError(err.message));
  }, []);

  return (
    <PageShell title="Ficheiros" description="O que geraste: exports do agente, esqueletos, rascunhos, matrizes e bibliografias. Só tu os vês." onOpenSidebar={onOpenSidebar}>
      <ErrorText>{error}</ErrorText>
      {!files && !error && <Spinner label="A carregar…" />}
      {files && files.length === 0 && <Empty>Ainda não geraste ficheiros.</Empty>}
      {files && files.length > 0 && (
        <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {files.map((file) => (
            <li key={file.name} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
              <span className="text-xs text-stone-500">
                {formatSize(file.size)} · {new Date(file.created_at).toLocaleString("pt-PT")}
              </span>
              <Button variant="ghost" icon={FileDown} aria-label={`Descarregar ${file.name}`} onClick={() => downloadExport(file.name).catch((err) => setError(err.message))} />
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
