import { useEffect, useRef, useState } from "react";

export default function ChatPanel({
  question,
  onQuestionChange,
  onAsk,
  onClear,
  onExport,
  asking,
  messages,
  multiQuery,
  onMultiQueryChange,
}) {
  const streamRef = useRef(null);
  const [expandedById, setExpandedById] = useState({});

  useEffect(() => {
    const streamEl = streamRef.current;
    if (!streamEl) return;
    streamEl.scrollTop = streamEl.scrollHeight;
  }, [messages]);

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onAsk();
    }
  }

  function toggleContext(messageId) {
    setExpandedById((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }));
  }

  return (
    <section className="panel chat-panel">
      <div className="chat-header-row">
        <div>
          <h2>Chat</h2>
          <p className="muted">Pergunta de um lado, resposta do outro, como num chat convencional.</p>
        </div>
        <div className="chat-toolbar">
          <label className="multi-query-toggle" title="Expande a pergunta em variantes antes de fazer retrieval">
            <input
              type="checkbox"
              checked={multiQuery}
              onChange={(e) => onMultiQueryChange(e.target.checked)}
            />
            Multi-Query
          </label>
          <button type="button" onClick={onExport} disabled={messages.length === 0}>
            Exportar historico
          </button>
          <button type="button" onClick={onClear} disabled={messages.length === 0}>
            Limpar historico
          </button>
        </div>
      </div>

      <div className="chat-stream" ref={streamRef}>
        {messages.length === 0 && (
          <div className="empty-chat-state">
            <p>Sem mensagens ainda. Faz a primeira pergunta.</p>
          </div>
        )}

        {messages.map((msg) => {
          const hasContext = (msg.sources && msg.sources.length > 0)
            || (msg.retrievalDiagnostics && msg.retrievalDiagnostics.length > 0)
            || (msg.expandedQueries && msg.expandedQueries.length > 0);
          const isExpanded = !!expandedById[msg.id];

          return (
            <article key={msg.id} className="chat-turn">
              <div className="bubble bubble-user">
                <p className="bubble-label">Utilizador</p>
                <p>{msg.question}</p>
              </div>

              <div className="bubble bubble-assistant">
                <p className="bubble-label">Assistente</p>
                <p>{msg.answer || (asking ? "A responder..." : "")}</p>

                {hasContext && (
                  <button
                    type="button"
                    className="context-toggle"
                    onClick={() => toggleContext(msg.id)}
                  >
                    {isExpanded ? "Ocultar fontes e diagnostico" : "Mostrar fontes e diagnostico"}
                  </button>
                )}

                {isExpanded && (
                  <div className="context-box">
                    {msg.expandedQueries?.length > 0 && (
                      <>
                        <h3>Queries expandidas ({msg.expandedQueries.length})</h3>
                        <ol className="expanded-queries-list">
                          {msg.expandedQueries.map((q, i) => (
                            <li key={`${msg.id}-eq-${i}`}>{q}</li>
                          ))}
                        </ol>
                      </>
                    )}
                    <h3>Fontes</h3>
                    {msg.sources?.length ? (
                      <ul>
                        {msg.sources.map((source, i) => (
                          <li key={`${msg.id}-src-${i}`}>
                            {source.filename} | pag. {source.page} | score {source.score.toFixed(3)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>Sem fontes devolvidas.</p>
                    )}

                    <h3>Diagnostico do ranking</h3>
                    {msg.retrievalDiagnostics?.length ? (
                      <ul className="diag-list">
                        {msg.retrievalDiagnostics.map((diag, i) => (
                          <li key={`${msg.id}-diag-${i}`}>
                            <strong>
                              {diag.filename} | pag. {diag.page} | chunk {diag.chunk_index}
                            </strong>
                            <span>
                              final {diag.final_score.toFixed(3)} = vec {diag.vector_score.toFixed(3)} + kw {diag.keyword_overlap.toFixed(3)} + pos {diag.position_penalty.toFixed(3)} + dens {diag.density_score.toFixed(3)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>Sem diagnostico devolvido.</p>
                    )}
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <div className="chat-composer">
        <textarea
          rows={3}
          value={question}
          onChange={(e) => onQuestionChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Escreve a tua pergunta... (Enter para enviar, Shift+Enter para nova linha)"
        />
        <button onClick={onAsk} disabled={asking}>
          {asking ? "A responder..." : "Perguntar"}
        </button>
      </div>
    </section>
  );
}
