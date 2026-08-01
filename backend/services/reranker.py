"""
Advanced re-ranking strategies for RAG retrieval candidates.

This module implements multiple re-ranking approaches to improve chunk selection
quality beyond simple vector similarity scoring.
"""

import re
from dataclasses import dataclass
from typing import Sequence

from backend.models import SourceChunk


@dataclass
class RankingScores:
    """Breakdown of multi-factor ranking scores."""
    vector_score: float
    keyword_overlap: float
    position_penalty: float
    density_score: float
    recency_boost: float
    final_score: float


def _compute_keyword_overlap(question_text: str, chunk_text: str) -> float:
    """Compute keyword overlap bonus (0-1 scale)."""
    question_tokens = {
        token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", question_text.lower()) if token
    }
    chunk_tokens = {
        token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", chunk_text.lower()) if token
    }
    
    if not question_tokens:
        return 0.0
    
    overlap = len(question_tokens & chunk_tokens)
    # Normalize by question size to avoid bias toward longer questions
    overlap_ratio = overlap / len(question_tokens)
    return min(overlap_ratio * 0.25, 1.0)  # Cap at 0.25 within rescaled 1.0


def _compute_position_penalty(chunk_index: int, total_chunks: int, alpha: float = 0.9) -> float:
    """
    Penalize chunks that are too deep in the document.
    Early chunks are often summaries or introductions (higher rank).
    Returns a penalty factor (1.0 = no penalty, 0.5 = 50% penalty).
    alpha: decay rate (0.9 = gentle decay, 0.7 = aggressive decay)
    """
    if total_chunks <= 1:
        return 1.0
    
    # Position as ratio [0, 1]
    position_ratio = chunk_index / (total_chunks - 1)
    # Apply exponential decay: closer to start = higher score
    penalty = alpha ** (position_ratio * 5)  # Exponent of 5 for noticeable effect
    return max(penalty, 0.5)  # Floor at 0.5 to avoid negligible chunks


def _compute_text_density(chunk_text: str) -> float:
    """
    Score chunk based on information density.
    - High token count + low punctuation = narrative (score: 0.8)
    - Low token count + high punctuation = summary/list (score: 1.0)
    Returns a density score (0.6-1.0).
    """
    tokens = len(re.findall(r"[a-zA-ZÀ-ÿ0-9]+", chunk_text))
    punctuation = len(re.findall(r"[.!?;:,—-]", chunk_text))
    
    if tokens == 0:
        return 0.6
    
    # High punctuation density = structured/concise = higher score
    punct_ratio = punctuation / max(tokens, 1)
    # Bonus for dense information
    if punct_ratio > 0.1:  # High punctuation = lists/summaries
        return 1.0
    elif tokens > 100:  # Long paragraph
        return 0.75
    else:  # Moderate length
        return 0.85


def rerank_hybrid(
    question: str,
    candidates: Sequence[tuple[SourceChunk, float]],
    weights: dict | None = None,
) -> Sequence[tuple[SourceChunk, RankingScores]]:
    """
    Re-rank candidates using hybrid scoring: vector similarity + keyword overlap + 
    position penalty + density + recency.
    
    Args:
        question: User query text
        candidates: List of (SourceChunk, vector_score) tuples
        weights: Dictionary of weight multipliers for each factor
                 Default: {'vector': 0.6, 'keyword': 0.25, 'position': 0.1, 'density': 0.05}
    
    Returns:
        List of (SourceChunk, RankingScores) tuples sorted by final_score descending
    """
    if not weights:
        weights = {
            'vector': 0.6,
            'keyword': 0.25,
            'position': 0.1,
            'density': 0.05,
        }
    
    total_candidates = len(candidates)
    scored = []
    
    for chunk, vector_score in candidates:
        keyword_score = _compute_keyword_overlap(question, chunk.text)
        document_chunk_count = chunk.document_chunk_count or total_candidates
        position_mult = _compute_position_penalty(
            chunk_index=chunk.chunk_index,
            total_chunks=document_chunk_count,
        )
        density_score = _compute_text_density(chunk.text)
        
        # Recency boost: chunks from recent documents score slightly higher
        # (This could be enhanced with actual timestamp metadata)
        recency_boost = 1.0  # Placeholder for future timestamp-based boost
        
        # Compute weighted final score
        final = (
            weights['vector'] * vector_score +
            weights['keyword'] * keyword_score +
            weights['position'] * position_mult +
            weights['density'] * density_score
        ) * recency_boost
        
        scores = RankingScores(
            vector_score=vector_score,
            keyword_overlap=keyword_score,
            position_penalty=position_mult,
            density_score=density_score,
            recency_boost=recency_boost,
            final_score=final,
        )
        
        scored.append((chunk, scores))
    
    # Sort by final_score descending
    scored.sort(key=lambda x: x[1].final_score, reverse=True)
    return scored


def scores_to_dict(scores: RankingScores) -> dict[str, float]:
    return {
        "vector_score": scores.vector_score,
        "keyword_overlap": scores.keyword_overlap,
        "position_penalty": scores.position_penalty,
        "density_score": scores.density_score,
        "recency_boost": scores.recency_boost,
        "final_score": scores.final_score,
    }


def format_ranking_explanation(scores: RankingScores) -> str:
    """Format ranking scores for debugging/logging."""
    return (
        f"vector={scores.vector_score:.3f} "
        f"keyword={scores.keyword_overlap:.3f} "
        f"position={scores.position_penalty:.3f} "
        f"density={scores.density_score:.3f} "
        f"→ final={scores.final_score:.3f}"
    )
