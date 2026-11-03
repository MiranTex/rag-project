"""Descobrir: mapa de um tema, lacunas, "isto parece-se com quê?" (texto da pessoa) e verificação de afirmações.

Tudo parte da base (índice de documentos e excertos); o LLM só dá nomes aos grupos, sugere lacunas, explica
diferenças e classifica afirmações. Sem LLM, cada função devolve na mesma o que encontrou na base."""

import re
from collections import Counter

import numpy as np

from backend.agent.tools.analysis import find_open_questions
from backend.agent.tools.base import ToolContext
from backend.research.library import cosine
from backend.research.llm import ChatCompletionClient, ask_json
from backend.services.embeddings import embed_query
from backend.services.search_filters import SearchFilters

# Semelhança de cosseno entre o texto da pessoa e a ficha de um documento.
OVERLAP_HIGH = 0.9  # quase o mesmo trabalho
OVERLAP_MEDIUM = 0.8  # tema e abordagem muito próximos
MAX_PARAGRAPHS = 25
MAX_CLAIMS = 12
EXCERPT_CHARS = 500


def _excerpt(source) -> dict:
    return {
        "document_id": source.document_id,
        "filename": source.filename,
        "page": source.page,
        "section": source.section,
        "text": source.text[:EXCERPT_CHARS],
        "score": round(float(source.score), 3),
    }


def _similar_documents(ctx: ToolContext, embedding: list[float], top_k: int, filters: SearchFilters) -> list[dict]:
    """Documentos mais próximos de um vetor, com a semelhança de cosseno calculada aqui (o Chroma devolve
    distâncias, cuja escala depende da configuração da coleção)."""
    results = ctx.profile_store.query(embedding, top_k, where=filters.to_chroma_where())
    ids = [item["metadata"]["document_id"] for item in results]
    vectors = ctx.profile_store.get_embeddings(ids) if ids else {}
    documents = []
    for item in results:
        meta = item["metadata"]
        vector = vectors.get(meta["document_id"])
        documents.append(
            {
                "document_id": meta["document_id"],
                "filename": meta.get("filename", ""),
                "title": meta.get("title", ""),
                "year": meta.get("year"),
                "document_type": meta.get("document_type", ""),
                "similarity": round(cosine(embedding, vector), 3) if vector is not None else None,
                "profile": item["text"][:400],
            }
        )
    documents.sort(key=lambda d: d["similarity"] or 0, reverse=True)
    return documents


def _kmeans(vectors: np.ndarray, k: int, iterations: int = 20) -> list[int]:
    """K-means com início determinístico (o mais afastado dos centros já escolhidos): os mesmos documentos dão
    sempre os mesmos grupos."""
    centers = [vectors[0]]
    while len(centers) < k:
        distances = np.min([np.linalg.norm(vectors - c, axis=1) for c in centers], axis=0)
        centers.append(vectors[int(np.argmax(distances))])
    centers_arr = np.array(centers)
    labels = np.zeros(len(vectors), dtype=int)
    for _ in range(iterations):
        labels = np.argmin(np.linalg.norm(vectors[:, None, :] - centers_arr[None, :, :], axis=2), axis=1)
        updated = np.array([vectors[labels == i].mean(axis=0) if np.any(labels == i) else centers_arr[i] for i in range(k)])
        if np.allclose(updated, centers_arr):
            break
        centers_arr = updated
    return labels.tolist()


def _normalize_reference(reference: str) -> str:
    return re.sub(r"\W+", " ", reference.lower()).strip()[:90]


def theme_map(topic: str, filters: SearchFilters, max_documents: int, ctx: ToolContext, llm: ChatCompletionClient | None) -> dict:
    """Panorama de um tema: documentos agrupados por subtema, pessoas, anos, palavras-chave e referências mais
    citadas nesses documentos."""
    embedding = embed_query(ctx.embedding_model, topic)
    documents = _similar_documents(ctx, embedding, max_documents, filters)
    if not documents:
        return {"topic": topic, "clusters": [], "people": [], "years": {}, "keywords": [], "references": [], "documents": 0}

    vectors = ctx.profile_store.get_embeddings([d["document_id"] for d in documents])
    with_vectors = [d for d in documents if d["document_id"] in vectors]
    # Cerca de metade dos documentos por grupo nos temas pequenos, até 4 grupos.
    k = min(4, max(1, (len(with_vectors) + 1) // 2))
    labels = _kmeans(np.array([vectors[d["document_id"]] for d in with_vectors]), k) if with_vectors else []

    people: Counter = Counter()
    keywords: Counter = Counter()
    references: dict[str, list] = {}
    years: Counter = Counter()
    cluster_keywords: list[Counter] = [Counter() for _ in range(k)]
    for doc, label in zip(with_vectors, labels):
        doc["cluster"] = label
    for doc in documents:
        metadata = ctx.extraction_store.load_metadata(doc["document_id"])
        doc_type = ctx.document_types.get(metadata.document_type) if ctx.document_types else None
        for author in metadata.authors:
            people[(author, "Autor")] += 1
        if doc_type:
            for field in doc_type.fields:
                value = metadata.fields.get(field.key)
                if field.kind == "people" and value:
                    for name in value if isinstance(value, list) else [value]:
                        people[(name, field.label)] += 1
        for keyword in metadata.keywords:
            keywords[keyword.lower()] += 1
            if "cluster" in doc:
                cluster_keywords[doc["cluster"]][keyword.lower()] += 1
        for reference in metadata.references:
            key = _normalize_reference(reference)
            entry = references.setdefault(key, [reference, set()])
            entry[1].add(doc["document_id"])
        if metadata.year:
            years[metadata.year] += 1

    clusters = [
        {
            "label": ", ".join(word for word, _ in cluster_keywords[i].most_common(3)),
            "documents": [d for d in with_vectors if d["cluster"] == i],
        }
        for i in range(k)
    ]
    clusters = [c for c in clusters if c["documents"]]
    _name_clusters(topic, clusters, llm)

    return {
        "topic": topic,
        "documents": len(documents),
        "clusters": clusters,
        "people": [{"name": name, "role": role, "count": count} for (name, role), count in people.most_common(12)],
        "years": dict(sorted(years.items())),
        "keywords": [{"keyword": word, "count": count} for word, count in keywords.most_common(15)],
        "references": [
            {"reference": original, "cited_by": len(ids)}
            for original, ids in sorted(references.values(), key=lambda entry: len(entry[1]), reverse=True)[:10]
            if len(ids) > 1
        ],
    }


def _name_clusters(topic: str, clusters: list[dict], llm: ChatCompletionClient | None) -> None:
    """Nome curto para cada grupo; sem LLM ficam as palavras-chave mais frequentes (ou o primeiro título)."""
    for cluster in clusters:
        if not cluster["label"]:
            first = cluster["documents"][0]
            cluster["label"] = first["title"] or first["filename"]
    if len(clusters) < 2:
        return
    listing = "\n\n".join(
        f"Grupo {i + 1}:\n" + "\n".join(f"- {d['title'] or d['filename']}" for d in c["documents"][:8])
        for i, c in enumerate(clusters)
    )
    result = ask_json(
        llm,
        "Dás nomes curtos (2 a 5 palavras, em português) a grupos de documentos sobre um tema.",
        f"Tema: {topic}\n\n{listing}",
        "name_groups",
        "Regista um nome por grupo, pela mesma ordem.",
        {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}}, "required": ["names"]},
    )
    names = (result or {}).get("names") or []
    if len(names) == len(clusters):
        for cluster, name in zip(clusters, names):
            if isinstance(name, str) and name.strip():
                cluster["label"] = name.strip()


def gaps(topic: str, filters: SearchFilters, max_documents: int, ctx: ToolContext, llm: ChatCompletionClient | None) -> dict:
    """O que os documentos sobre o tema deixaram em aberto, quanto o tema já foi estudado e sugestões de
    temas por explorar (com o LLM), cada uma apoiada nos documentos de onde saiu."""
    params = {"query": topic, "max_documents": max_documents}
    if filters.document_type:
        params["document_type"] = filters.document_type
    if filters.year_from:
        params["year_from"] = filters.year_from
    if filters.year_to:
        params["year_to"] = filters.year_to
    if filters.fields:
        params["fields"] = filters.fields
    open_questions = find_open_questions.run(params, ctx).content

    embedding = embed_query(ctx.embedding_model, topic)
    similar = _similar_documents(ctx, embedding, 20, SearchFilters(document_ids=filters.document_ids))
    close = [d for d in similar if (d["similarity"] or 0) >= 0.5]
    coverage = {
        "related_documents": len(close),
        "years": dict(sorted(Counter(d["year"] for d in close if d["year"]).items())),
    }

    suggestions: list[dict] = []
    documents = open_questions.get("documents", [])
    if documents:
        listing = "\n\n".join(
            f"[{i + 1}] {d.get('title') or d['filename']} ({d.get('year', 's.d.')})\n"
            + "\n".join(f"- {o['section']} (p. {o['pages']}): {o['text'][:800]}" for o in d.get("open", []))
            for i, d in enumerate(documents)
        )
        result = ask_json(
            llm,
            "Ajudas quem procura um tema de investigação. A partir do que vários trabalhos deixaram em aberto, "
            "propões temas por explorar. Cada proposta tem de vir do que está nos excertos e indica os números "
            "dos documentos em que se apoia. Escreve em português.",
            f"Tema: {topic}\n\nPontos em aberto:\n\n{listing}",
            "suggest_gaps",
            "Regista entre 2 e 6 temas por explorar.",
            {
                "type": "object",
                "properties": {
                    "gaps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "documents": {"type": "array", "items": {"type": "integer"}},
                            },
                            "required": ["title", "description", "documents"],
                        },
                    }
                },
                "required": ["gaps"],
            },
        )
        for gap in (result or {}).get("gaps") or []:
            refs = [n for n in gap.get("documents") or [] if isinstance(n, int) and 1 <= n <= len(documents)]
            if gap.get("title") and refs:
                suggestions.append(
                    {
                        "title": gap["title"],
                        "description": gap.get("description", ""),
                        "documents": [
                            {"document_id": documents[n - 1]["document_id"], "title": documents[n - 1].get("title") or documents[n - 1]["filename"]}
                            for n in refs
                        ],
                    }
                )
    return {"topic": topic, "open_questions": open_questions, "coverage": coverage, "suggestions": suggestions}


def split_paragraphs(text: str, min_chars: int = 120) -> list[str]:
    """Parágrafos (separados por linha em branco); os curtos juntam-se ao seguinte para terem contexto."""
    paragraphs, buffer = [], ""
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        if not block:
            continue
        buffer = f"{buffer} {block}".strip()
        if len(buffer) >= min_chars:
            paragraphs.append(buffer)
            buffer = ""
    if buffer:
        if paragraphs and len(buffer) < min_chars:
            paragraphs[-1] = f"{paragraphs[-1]} {buffer}"
        else:
            paragraphs.append(buffer)
    return paragraphs[:MAX_PARAGRAPHS]


def analyze_text(text: str, filters: SearchFilters, ctx: ToolContext, llm: ChatCompletionClient | None) -> dict:
    """"Isto parece-se com quê?": documentos parecidos com o texto, excertos da base ligados a cada parágrafo e
    alerta de sobreposição (trabalhos já feitos muito parecidos, com o que os distingue). O texto não é guardado."""
    embedding = embed_query(ctx.embedding_model, text[:4000])
    similar = _similar_documents(ctx, embedding, 8, SearchFilters(document_ids=filters.document_ids))

    paragraphs = []
    for index, paragraph in enumerate(split_paragraphs(text)):
        sources = ctx.pipeline.retrieve_sources(question=paragraph[:1000], top_k=3, filters=filters)
        paragraphs.append({"index": index, "text": paragraph, "excerpts": [_excerpt(s) for s in sources]})

    overlap = []
    for doc in similar:
        similarity = doc["similarity"] or 0
        if similarity < OVERLAP_MEDIUM:
            continue
        entry = {**doc, "level": "high" if similarity >= OVERLAP_HIGH else "medium", "difference": ""}
        if len(overlap) < 2:
            result = ask_json(
                llm,
                "Comparas o texto de uma pessoa com um trabalho que já existe. Em 2 a 3 frases, em português, "
                "dizes em que se distinguem (pergunta, abordagem, dados, contexto). Se forem praticamente o mesmo "
                "trabalho, di-lo.",
                f"Texto da pessoa:\n{text[:3000]}\n\nTrabalho existente ({doc['title'] or doc['filename']}):\n{doc['profile']}",
                "record_difference",
                "Regista a diferença.",
                {"type": "object", "properties": {"difference": {"type": "string"}}, "required": ["difference"]},
            )
            entry["difference"] = (result or {}).get("difference", "")
        overlap.append(entry)

    return {"similar_documents": similar, "paragraphs": paragraphs, "overlap": overlap}


def split_claims(text: str, min_chars: int = 40) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\"«(])", " ".join(text.split()))
    return [s.strip() for s in sentences if len(s.strip()) >= min_chars][:MAX_CLAIMS]


VERDICTS = ("supported", "contradicted", "unsupported")


def check_claims(text: str, filters: SearchFilters, ctx: ToolContext, llm: ChatCompletionClient | None) -> dict:
    """Cada afirmação do texto com os excertos mais próximos da base e o veredicto do LLM: apoiada,
    contradita ou sem apoio. Sem LLM, o veredicto fica "unchecked" e a pessoa avalia pelos excertos."""
    claims = []
    for claim in split_claims(text):
        sources = ctx.pipeline.retrieve_sources(question=claim, top_k=3, filters=filters)
        claims.append({"claim": claim, "verdict": "unchecked", "explanation": "", "evidence": [_excerpt(s) for s in sources]})
    if not claims:
        return {"claims": []}

    listing = "\n\n".join(
        f"Afirmação {i + 1}: {c['claim']}\n"
        + "\n".join(f"  Excerto {j + 1} ({e['filename']}, p. {e['page']}): {e['text']}" for j, e in enumerate(c["evidence"]))
        for i, c in enumerate(claims)
    )
    result = ask_json(
        llm,
        "Verificas afirmações contra excertos de documentos. Para cada afirmação: supported se algum excerto a "
        "apoia, contradicted se algum a contradiz, unsupported se os excertos não dizem nada sobre ela. Usa só os "
        "excertos dados, não o teu conhecimento. Explica numa frase, em português, e indica os excertos usados.",
        listing,
        "record_verdicts",
        "Regista um veredicto por afirmação.",
        {
            "type": "object",
            "properties": {
                "verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "integer"},
                            "verdict": {"type": "string", "enum": list(VERDICTS)},
                            "explanation": {"type": "string"},
                            "excerpts": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["claim", "verdict", "explanation", "excerpts"],
                    },
                }
            },
            "required": ["verdicts"],
        },
    )
    for verdict in (result or {}).get("verdicts") or []:
        index = verdict.get("claim")
        if not isinstance(index, int) or not 1 <= index <= len(claims) or verdict.get("verdict") not in VERDICTS:
            continue
        claim = claims[index - 1]
        claim["verdict"] = verdict["verdict"]
        claim["explanation"] = verdict.get("explanation", "")
        used = {n for n in verdict.get("excerpts") or [] if isinstance(n, int)}
        for number, evidence in enumerate(claim["evidence"], start=1):
            evidence["used"] = number in used
    return {"claims": claims}
