#!/usr/bin/env python3
"""Run grounded RAG evaluation against the indexed PDF dataset."""

import json
import re
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import get_settings
from backend.dependencies import get_rag_pipeline, get_registry
from backend.services.rag_pipeline import SYSTEM_PROMPT


STOPWORDS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos", "e", "em",
    "é", "o", "os", "para", "por", "que", "se", "um", "uma",
}


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower())
        if token and token not in STOPWORDS
    }


def _score_keyword_coverage(text: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    normalized_text = text.lower()
    matches = sum(1 for keyword in expected_keywords if keyword.lower() in normalized_text)
    return matches / len(expected_keywords)


def _score_source_relevance(sources: list[dict], expected_keywords: list[str], expected_pages: list[int]) -> float:
    if not sources:
        return 0.0

    source_text = " ".join(source["text"] for source in sources)
    keyword_score = _score_keyword_coverage(source_text, expected_keywords)

    if expected_pages:
        matched_pages = sum(1 for source in sources if int(source["page"]) in expected_pages)
        page_score = min(matched_pages / len(expected_pages), 1.0)
    else:
        page_score = 1.0

    return round((keyword_score * 0.7) + (page_score * 0.3), 2)


def _score_answer_grounding(answer: str, sources: list[dict]) -> float:
    answer_tokens = _tokenize(answer)
    source_tokens = _tokenize(" ".join(source["text"] for source in sources))
    lexical_overlap = (len(answer_tokens & source_tokens) / len(answer_tokens)) if answer_tokens else 0.0

    citation_patterns = [
        rf"página\s+{source['page']}\b"
        for source in sources
    ] + [
        rf"p\.\s*{source['page']}\b"
        for source in sources
    ]
    citation_score = 1.0 if any(re.search(pattern, answer.lower()) for pattern in citation_patterns) else 0.0
    return round(min((lexical_overlap * 0.75) + (citation_score * 0.25), 1.0), 2)


def _score_answer_depth(answer: str, expected_keywords: list[str]) -> int:
    answer_length = len(answer.strip())
    sentence_count = max(len(re.findall(r"[.!?]+", answer)), 1)
    keyword_coverage = _score_keyword_coverage(answer, expected_keywords)

    raw_score = 1.0
    raw_score += min(answer_length / 180, 2.0)
    raw_score += min(sentence_count / 3, 1.0)
    raw_score += min(keyword_coverage, 1.0)
    return max(1, min(round(raw_score), 5))


def load_eval_data(eval_path: str = "tests/eval_data.json") -> dict:
    """Load evaluation dataset."""
    with open(eval_path, encoding="utf-8") as f:
        return json.load(f)


def resolve_document_id(explicit_document_id: str | None, preferred_filename: str | None) -> str | None:
    if explicit_document_id:
        return explicit_document_id

    registry = get_registry()
    for document in registry.list_documents():
        if preferred_filename and document.filename == preferred_filename:
            return document.document_id

    return None


def evaluate_single_query(
    rag_pipeline,
    question: str,
    expected_keywords: list[str],
    expected_pages: list[int],
    document_id: str | None = None,
    top_k: int = 5,
    rerank_weights: dict[str, float] | None = None,
) -> dict:
    """
    Evaluate a single question.
    Returns dict with answer, sources, and engagement metrics.
    """
    try:
        user_prompt, sources, diagnostics = rag_pipeline.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
        )
        answer = rag_pipeline.lmstudio_client.chat(SYSTEM_PROMPT, user_prompt)

        serialized_sources = [
            {
                "filename": source.filename,
                "page": source.page,
                "score": source.score,
                "text": source.text,
            }
            for source in sources
        ]

        metrics = {
            "answer_depth": _score_answer_depth(answer, expected_keywords),
            "grounding": _score_answer_grounding(answer, serialized_sources),
            "relevance": _score_source_relevance(serialized_sources, expected_keywords, expected_pages),
        }
        
        return {
            "query": question,
            "status": "success",
            "answer": answer,
            "num_sources": len(sources),
            "sources": [
                {
                    "filename": source["filename"],
                    "page": source["page"],
                    "score": source["score"],
                    "text": source["text"][:140] + "..." if len(source["text"]) > 140 else source["text"],
                }
                for source in serialized_sources
            ],
            "retrieval_diagnostics": [item.model_dump() for item in diagnostics],
            "metrics": metrics,
        }
    except Exception as e:
        return {
            "query": question,
            "status": "error",
            "error": str(e),
        }


def _aggregate_metrics(results: list[dict]) -> dict:
    successful = [r for r in results if r.get("status") == "success"]
    success_count = len(successful)
    total = len(results)

    return {
        "success": success_count,
        "total": total,
        "success_rate": ((success_count / total) * 100) if total else 0.0,
        "avg_sources": (
            sum(r.get("num_sources", 0) for r in successful) / success_count
            if success_count
            else 0.0
        ),
        "avg_depth": (
            sum(r.get("metrics", {}).get("answer_depth", 0) for r in successful) / success_count
            if success_count
            else 0.0
        ),
        "avg_grounding": (
            sum(r.get("metrics", {}).get("grounding", 0.0) for r in successful) / success_count
            if success_count
            else 0.0
        ),
        "avg_relevance": (
            sum(r.get("metrics", {}).get("relevance", 0.0) for r in successful) / success_count
            if success_count
            else 0.0
        ),
    }


def run_evaluation_suite(
    document_id: str | None = None,
    eval_path: str = "tests/eval_data.json",
    rerank_weights: dict[str, float] | None = None,
    run_label: str = "single-run",
):
    """Run full evaluation suite on test questions."""

    print("\n" + "=" * 70)
    print(f"RAG QUALITY EVALUATION - Phase 3 Advanced Re-ranking ({run_label})")
    print("=" * 70)

    eval_data = load_eval_data(eval_path)
    print(f"\nLoaded {len(eval_data['eval_cases'])} evaluation cases")
    print(f"Metrics thresholds: {eval_data['metrics']}\n")

    try:
        rag_pipeline = get_rag_pipeline()
        print("RAG pipeline initialized\n")
    except Exception as e:
        print(f"Failed to initialize RAG pipeline: {e}")
        print("Make sure Chroma, LM Studio, and embeddings are available.")
        return

    target_document_id = resolve_document_id(
        explicit_document_id=document_id,
        preferred_filename=eval_data.get("metadata", {}).get("document_filename"),
    )
    print(f"Document selected: {target_document_id or 'all indexed documents'}")
    if rerank_weights:
        print(f"Rerank weights: {rerank_weights}")
    print()

    results = []

    for case in eval_data["eval_cases"]:
        case_id = case["id"]
        question = case["question"]
        difficulty = case["difficulty"]
        expected_keywords = case.get("expected_keywords", [])
        expected_pages = case.get("expected_pages", [])

        print(f"Q{case_id} [{difficulty}]: {question}")
        print("-" * 70)

        result = evaluate_single_query(
            rag_pipeline,
            question,
            expected_keywords=expected_keywords,
            expected_pages=expected_pages,
            document_id=target_document_id,
            rerank_weights=rerank_weights,
        )
        result["case_id"] = case_id
        result["difficulty"] = difficulty
        results.append(result)

        if result["status"] == "success":
            top_source = result["sources"][0] if result["sources"] else None
            print(f"Answer retrieved ({result['num_sources']} sources)")
            print(f"Answer preview: {result['answer'][:120]}...")
            if top_source:
                print(f"Top source: {top_source['filename']} (p.{top_source['page']})")
            print(
                "Metrics: "
                f"depth={result['metrics']['answer_depth']}/5 | "
                f"grounding={result['metrics']['grounding']:.2f} | "
                f"relevance={result['metrics']['relevance']:.2f}"
            )
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")

        print()

    print("=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)

    summary = _aggregate_metrics(results)

    print(f"\nSuccess rate: {summary['success']}/{summary['total']} ({summary['success_rate']:.1f}%)")

    by_difficulty = {}
    for r in results:
        diff = r["difficulty"]
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "success": 0}
        by_difficulty[diff]["total"] += 1
        if r["status"] == "success":
            by_difficulty[diff]["success"] += 1
    
    print("\nPerformance by difficulty:")
    for diff in ["easy", "medium", "hard"]:
        if diff in by_difficulty:
            stats = by_difficulty[diff]
            rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"   {diff.upper():8s}: {stats['success']}/{stats['total']} ({rate:.0f}%)")

    print(f"\nAverage sources retrieved: {summary['avg_sources']:.1f}")
    print(f"Average answer depth: {summary['avg_depth']:.2f}/5")
    print(f"Average grounding: {summary['avg_grounding']:.2f}")
    print(f"Average retrieval relevance: {summary['avg_relevance']:.2f}")

    print("\nImprovement guide:")
    print("   - Reindex existing documents so chunk_index becomes document-global and metadata includes document_chunk_count")
    print("   - Use include_debug=true on /chat/ask to inspect why a chunk ranked at the top")
    print("   - Tune weights in reranker.py if relevance is high but grounding is low")

    return {"results": results, "summary": summary}


def run_ab_evaluation(
    document_id: str | None = None,
    eval_path: str = "tests/eval_data.json",
) -> None:
    settings = get_settings()
    default_weights = settings.parse_rerank_weights("default")
    grounding_weights = settings.parse_rerank_weights("grounding")

    baseline = run_evaluation_suite(
        document_id=document_id,
        eval_path=eval_path,
        rerank_weights=default_weights,
        run_label="A/default",
    )
    challenger = run_evaluation_suite(
        document_id=document_id,
        eval_path=eval_path,
        rerank_weights=grounding_weights,
        run_label="B/grounding",
    )

    a = baseline["summary"]
    b = challenger["summary"]

    print("\n" + "=" * 70)
    print("A/B COMPARISON")
    print("=" * 70)
    print(f"Grounding delta (B-A): {b['avg_grounding'] - a['avg_grounding']:+.2f}")
    print(f"Relevance delta (B-A): {b['avg_relevance'] - a['avg_relevance']:+.2f}")
    print(f"Depth delta (B-A): {b['avg_depth'] - a['avg_depth']:+.2f}")
    print(f"Success rate delta (B-A): {b['success_rate'] - a['success_rate']:+.1f} pp")

    winner = "B/grounding" if b["avg_grounding"] >= a["avg_grounding"] else "A/default"
    print(f"Recommended profile for grounding: {winner}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate RAG system quality")
    parser.add_argument("--document-id", type=str, help="Document ID in vector store")
    parser.add_argument("--eval-path", type=str, default="tests/eval_data.json", help="Path to evaluation dataset")
    parser.add_argument("--ab", action="store_true", help="Run A/B evaluation between default and grounding rerank profiles")
    args = parser.parse_args()

    if args.ab:
        run_ab_evaluation(document_id=args.document_id, eval_path=args.eval_path)
    else:
        run_evaluation_suite(document_id=args.document_id, eval_path=args.eval_path)
