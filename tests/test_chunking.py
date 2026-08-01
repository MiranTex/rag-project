from backend.services.pdf_ingestion import chunk_pages


def test_chunk_pages_generates_segments() -> None:
    pages = [(1, "a" * 2500)]
    chunks = chunk_pages(pages, document_id="doc-1", chunk_size=1000, chunk_overlap=100)

    assert len(chunks) >= 2
    assert chunks[0].page == 1
    assert chunks[0].id == "doc-1:0"
    assert chunks[0].chunk_index == 0
    assert chunks[-1].document_chunk_count == len(chunks)


def test_chunk_pages_respects_sentence_boundaries() -> None:
    page_text = (
        "Primeira frase de contexto relevante. "
        "Segunda frase de contexto relevante. "
        "Terceira frase de contexto relevante."
    )
    chunks = chunk_pages(
        pages=[(1, page_text)],
        document_id="doc-2",
        chunk_size=40,
        chunk_overlap=10,
    )

    assert len(chunks) >= 2
    assert all(chunk.text.endswith((".", "!", "?")) for chunk in chunks)
