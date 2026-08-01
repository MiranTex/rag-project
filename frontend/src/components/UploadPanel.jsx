export default function UploadPanel({
  documents,
  selectedDocument,
  onSelectDocument,
  uploadStatus,
  onFileChange,
  onUpload,
  onReindex,
  onDelete,
  loading,
}) {
  return (
    <section className="panel">
      <h2>Documentos</h2>
      <p className="muted">Carrega PDFs para alimentar a base vetorial.</p>

      <div className="upload-controls">
        <input type="file" accept="application/pdf" onChange={onFileChange} />
        <button onClick={onUpload} disabled={loading}>
          {loading ? "A indexar..." : "Carregar e indexar"}
        </button>
      </div>

      {uploadStatus && <p className="status">{uploadStatus}</p>}

      <label className="field-label">Filtrar perguntas por documento:</label>
      <select
        value={selectedDocument}
        onChange={(e) => onSelectDocument(e.target.value)}
      >
        <option value="">Todos os documentos</option>
        {documents.map((doc) => (
          <option key={doc.document_id} value={doc.document_id}>
            {doc.filename} ({doc.chunk_count} chunks)
          </option>
        ))}
      </select>

      <ul className="doc-list">
        {documents.map((doc) => (
          <li key={doc.document_id}>
            <strong>{doc.filename}</strong>
            <span>{doc.chunk_count} chunks</span>
            <div className="doc-actions">
              <button
                type="button"
                onClick={() => onReindex(doc.document_id)}
                disabled={loading}
              >
                Reindexar
              </button>
              <button
                type="button"
                onClick={() => onDelete(doc.document_id)}
                disabled={loading}
              >
                Apagar
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
