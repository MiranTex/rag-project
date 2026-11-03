import { useEffect, useState } from "react";
import { FileDown, Save, Wand2, X } from "lucide-react";
import { research } from "../../api";
import { Button, Empty, ErrorText, Spinner, documentLabel, inputClass } from "../../components/ui";
import { useResearch } from "../../research/ResearchContext";

const SUGGESTED = ["Objetivo", "Método", "Dados", "Principais resultados", "Limitações"];

function Cell({ cell, note, canEdit, onNote, onOpen }) {
  const [open, setOpen] = useState(false);
  return (
    <td className="min-w-56 border border-stone-200 p-2 align-top text-sm dark:border-stone-800">
      {cell?.summary && <p className="text-stone-800 dark:text-stone-200">{cell.summary}</p>}
      {cell?.excerpts?.length > 0 && (
        <button type="button" className="mt-1 text-xs text-accent-700 hover:underline dark:text-accent-400" onClick={() => setOpen(!open)}>
          {open ? "Esconder" : "Ver"} {cell.excerpts.length} excerto{cell.excerpts.length === 1 ? "" : "s"}
        </button>
      )}
      {open &&
        cell.excerpts.map((e, i) => (
          <button key={i} type="button" onClick={() => onOpen(e)} className="mt-1 block text-left text-xs text-stone-600 hover:underline dark:text-stone-400">
            p. {e.page}: {e.text.slice(0, 220)}…
          </button>
        ))}
      <textarea
        className={`${inputClass} mt-2 text-xs`}
        rows={2}
        placeholder={canEdit ? "A tua nota" : ""}
        value={note || ""}
        disabled={!canEdit}
        onChange={(e) => onNote(e.target.value)}
      />
    </td>
  );
}

function toMarkdown(matrix) {
  const header = `| Documento | ${matrix.dimensions.join(" | ")} |`;
  const divider = `|${" --- |".repeat(matrix.dimensions.length + 1)}`;
  const clean = (text) => (text || "").replace(/\|/g, "/").replace(/\n/g, " ");
  const rows = matrix.documents.map((doc) => {
    const cells = matrix.dimensions.map((d) => {
      const note = matrix.notes[doc.document_id]?.[d];
      const summary = matrix.cells[doc.document_id]?.[d]?.summary;
      return clean([summary, note].filter(Boolean).join(" — "));
    });
    return `| ${clean(documentLabel(doc))}${doc.year ? ` (${doc.year})` : ""} | ${cells.join(" | ")} |`;
  });
  return [header, divider, ...rows].join("\n");
}

export default function Matrix({ projectId, canEdit }) {
  const { openReader, notify } = useResearch();
  const [matrix, setMatrix] = useState(null);
  const [newDimension, setNewDimension] = useState("");
  const [busy, setBusy] = useState("");
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    research.matrix(projectId).then(setMatrix, (err) => setError(err.message));
  }, [projectId]);

  async function act(kind, action) {
    setBusy(kind);
    setError("");
    try {
      setMatrix(await action());
      setDirty(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  if (!matrix) return error ? <ErrorText>{error}</ErrorText> : <Spinner label="A carregar a matriz…" />;

  const setDimensions = (dimensions) => {
    setMatrix({ ...matrix, dimensions });
    setDirty(true);
  };
  const setNote = (documentId, dimension, value) => {
    setMatrix({ ...matrix, notes: { ...matrix.notes, [documentId]: { ...matrix.notes[documentId], [dimension]: value } } });
    setDirty(true);
  };
  const save = () => act("save", () => research.saveMatrix(projectId, { dimensions: matrix.dimensions, notes: matrix.notes }));

  return (
    <>
      <p className="mb-4 text-sm text-stone-500 dark:text-stone-400">
        Compara os documentos do projeto lado a lado. "Preencher" procura em cada documento o que diz sobre cada dimensão; as tuas notas ficam.
      </p>
      {canEdit && (
        <div className="mb-4 space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {matrix.dimensions.map((d) => (
              <span key={d} className="inline-flex items-center gap-1 rounded-full bg-stone-200/70 py-0.5 pl-2.5 pr-1 text-sm dark:bg-stone-800">
                {d}
                <button type="button" aria-label={`Retirar ${d}`} onClick={() => setDimensions(matrix.dimensions.filter((x) => x !== d))} className="rounded-full p-0.5 hover:bg-stone-300 dark:hover:bg-stone-700">
                  <X className="size-3" />
                </button>
              </span>
            ))}
            {SUGGESTED.filter((s) => !matrix.dimensions.includes(s)).map((s) => (
              <button
                key={s}
                type="button"
                disabled={matrix.dimensions.length >= 6}
                onClick={() => setDimensions([...matrix.dimensions, s])}
                className="rounded-full border border-dashed border-stone-300 px-2.5 py-0.5 text-sm text-stone-500 hover:border-stone-500 disabled:opacity-40 dark:border-stone-700"
              >
                + {s}
              </button>
            ))}
          </div>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (newDimension.trim() && matrix.dimensions.length < 6) setDimensions([...matrix.dimensions, newDimension.trim()]);
              setNewDimension("");
            }}
          >
            <input className={`${inputClass} flex-1`} placeholder="Outra dimensão (máx. 6)" value={newDimension} onChange={(e) => setNewDimension(e.target.value)} />
            <Button
              variant="primary"
              icon={Wand2}
              busy={busy === "fill"}
              disabled={!matrix.dimensions.length || matrix.documents.length < 2}
              title={matrix.documents.length < 2 ? "Fixa pelo menos 2 documentos" : undefined}
              onClick={() =>
                act("fill", async () => {
                  // O servidor mantém as notas guardadas: as que ainda não foram guardadas iam perder-se.
                  if (dirty) await research.saveMatrix(projectId, { dimensions: matrix.dimensions, notes: matrix.notes });
                  return research.fillMatrix(projectId, { dimensions: matrix.dimensions });
                })
              }
            >
              Preencher
            </Button>
            <Button icon={Save} busy={busy === "save"} disabled={!dirty} onClick={save}>
              Guardar
            </Button>
            <Button
              variant="ghost"
              icon={FileDown}
              disabled={!matrix.dimensions.length}
              onClick={() =>
                research
                  .export({ title: "Matriz de literatura", markdown: toMarkdown(matrix), format: "docx" })
                  .then((r) => notify(`Exportado: ${r.name} (em Ficheiros)`), (err) => setError(err.message))
              }
            >
              Word
            </Button>
          </form>
        </div>
      )}
      <ErrorText>{error}</ErrorText>
      {busy === "fill" && <Spinner label="A ler os documentos…" />}
      {matrix.documents.length === 0 ? (
        <Empty>Fixa documentos no projeto para os comparar.</Empty>
      ) : matrix.dimensions.length === 0 ? (
        <Empty>Escolhe as dimensões a comparar (método, dados, resultados…).</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="border border-stone-200 p-2 text-left text-xs font-medium text-stone-500 dark:border-stone-800">Documento</th>
                {matrix.dimensions.map((d) => (
                  <th key={d} className="border border-stone-200 p-2 text-left text-xs font-medium text-stone-500 dark:border-stone-800">
                    {d}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.documents.map((doc) => (
                <tr key={doc.document_id}>
                  <th className="min-w-40 border border-stone-200 p-2 text-left align-top text-sm font-medium dark:border-stone-800">
                    <button type="button" className="text-left hover:underline" onClick={() => openReader({ document_id: doc.document_id, page: 1 })}>
                      {documentLabel(doc)}
                    </button>
                    {doc.year && <span className="block text-xs font-normal text-stone-500">{doc.year}</span>}
                  </th>
                  {matrix.dimensions.map((d) => (
                    <Cell
                      key={d}
                      cell={matrix.cells[doc.document_id]?.[d]}
                      note={matrix.notes[doc.document_id]?.[d]}
                      canEdit={canEdit}
                      onNote={(value) => setNote(doc.document_id, d, value)}
                      onOpen={(e) => openReader({ ...e, document_id: doc.document_id })}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
