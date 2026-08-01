"""
Tests for advanced re-ranking functionality.
"""

import pytest

from backend.models import SourceChunk
from backend.services.reranker import (
    RankingScores,
    _compute_keyword_overlap,
    _compute_position_penalty,
    _compute_text_density,
    format_ranking_explanation,
    rerank_hybrid,
)


class TestKeywordOverlap:
    """Test keyword overlap computation."""

    def test_high_overlap_identical_words(self):
        question = "memória e aprendizado"
        chunk = "Discussão sobre memória e aprendizado profundo."
        overlap = _compute_keyword_overlap(question, chunk)
        # Overlap is capped at 0.25 (normalized for balanced weighting across factors)
        assert overlap == 0.25, "Should match overlap cap with high keyword matching"

    def test_low_overlap_different_topics(self):
        question = "geometria euclidiana"
        chunk = "A história da culinária portuguesa é fascinante."
        overlap = _compute_keyword_overlap(question, chunk)
        assert overlap < 0.3, "Should have low overlap with different topics"

    def test_empty_question(self):
        question = ""
        chunk = "Some text here."
        overlap = _compute_keyword_overlap(question, chunk)
        assert overlap == 0.0, "Empty question should result in 0 overlap"

    def test_case_insensitive(self):
        question = "MEMÓRIA"
        chunk = "memória estruturada"
        overlap = _compute_keyword_overlap(question, chunk)
        # 1 out of 1 question token matches = 100% * 0.25 cap = 0.25
        assert overlap == 0.25, "Should be case insensitive and apply overlap cap"


class TestPositionPenalty:
    """Test position-based penalty computation."""

    def test_early_chunk_no_penalty(self):
        penalty = _compute_position_penalty(chunk_index=0, total_chunks=10)
        assert penalty > 0.95, "Early chunks should have minimal penalty"

    def test_late_chunk_significant_penalty(self):
        penalty = _compute_position_penalty(chunk_index=9, total_chunks=10)
        assert penalty < 0.85, "Late chunks should have noticeable penalty"

    def test_single_chunk_no_penalty(self):
        penalty = _compute_position_penalty(chunk_index=0, total_chunks=1)
        assert penalty == 1.0, "Single chunk should have no penalty"

    def test_middle_chunk_moderate_penalty(self):
        mid_penalty = _compute_position_penalty(chunk_index=5, total_chunks=10)
        early_penalty = _compute_position_penalty(chunk_index=0, total_chunks=10)
        assert mid_penalty < early_penalty, "Middle chunks should rank lower than early ones"
        assert mid_penalty > 0.5, "Should not be penalized below floor"


class TestTextDensity:
    """Test information density scoring."""

    def test_punctuation_dense_text(self):
        # List-like text with high punctuation
        text = "Item 1: Primeiro; Item 2: Segundo; Item 3: Terceiro."
        density = _compute_text_density(text)
        assert density == 1.0, "Punctuation-dense text should score 1.0"

    def test_long_narrative(self):
        # Long paragraph with low punctuation
        text = " ".join(["palavra"] * 150)  # 150 tokens, minimal punctuation
        density = _compute_text_density(text)
        assert density == 0.75, "Long narrative should score 0.75"

    def test_moderate_text(self):
        # Medium paragraph with punctuation (10 periods out of ~50 tokens = 20% punct_ratio)
        text = "Esta é uma frase. " * 10  # ~50 tokens, 20% punctuation density
        density = _compute_text_density(text)
        # Punctuation density 20% > 10% threshold → scores 1.0
        assert density == 1.0, "Text with 20% punctuation should score max density"

    def test_empty_text(self):
        density = _compute_text_density("")
        assert density == 0.6, "Empty text should score minimum 0.6"


class TestRerankHybrid:
    """Test full hybrid re-ranking pipeline."""

    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks for testing."""
        chunk1 = SourceChunk(
            document_id="doc1",
            filename="memoria.pdf",
            page=1,
            chunk_index=0,
            score=0.95,
            text="Memória é a capacidade de reter e recuperar informações.",
            document_chunk_count=10,
        )
        chunk2 = SourceChunk(
            document_id="doc1",
            filename="memoria.pdf",
            page=2,
            chunk_index=1,
            score=0.85,
            text="Aprendizado reforçado; Memória de curto prazo; Consolidação.",
            document_chunk_count=10,
        )
        chunk3 = SourceChunk(
            document_id="doc1",
            filename="memoria.pdf",
            page=10,
            chunk_index=9,
            score=0.80,
            text="A história da culinária é um tópico completamente diferente.",
            document_chunk_count=10,
        )
        return [(chunk1, 0.95), (chunk2, 0.85), (chunk3, 0.80)]

    def test_rerank_prefers_keyword_match(self, sample_chunks):
        question = "O que é memória?"
        reranked = rerank_hybrid(question, sample_chunks)
        
        # First (highest scoring) should be chunk1 or chunk2 (both mention "memória")
        top_chunk, top_scores = reranked[0]
        assert "memória" in top_chunk.text.lower(), "Top result should contain keyword"

    def test_rerank_penalizes_position(self, sample_chunks):
        question = "processo de aprendizado"
        reranked = rerank_hybrid(question, sample_chunks)
        
        # Chunk3 is deep in document (index 9) so should be penalized
        chunk3_rank = next(i for i, (chunk, _) in enumerate(reranked) if chunk.chunk_index == 9)
        assert chunk3_rank > 0, "Late chunk should not be ranked first"

    def test_rerank_returns_ranking_scores(self, sample_chunks):
        question = "memória"
        reranked = rerank_hybrid(question, sample_chunks)
        
        for chunk, scores in reranked:
            assert isinstance(scores, RankingScores)
            assert 0 <= scores.vector_score <= 1
            assert 0 <= scores.keyword_overlap <= 1
            assert 0.5 <= scores.position_penalty <= 1.0
            assert 0.6 <= scores.density_score <= 1.0
            assert scores.final_score > 0

    def test_rerank_sort_order(self, sample_chunks):
        question = "memória"
        reranked = rerank_hybrid(question, sample_chunks)
        
        # Verify scores are in descending order
        scores = [s.final_score for _, s in reranked]
        assert scores == sorted(scores, reverse=True), "Scores should be sorted descending"

    def test_rerank_custom_weights(self, sample_chunks):
        question = "memória"
        # Favor keyword overlap heavily
        custom_weights = {
            'vector': 0.1,
            'keyword': 0.7,  # High weight on keywords
            'position': 0.1,
            'density': 0.1,
        }
        reranked = rerank_hybrid(question, sample_chunks, weights=custom_weights)
        
        # With high keyword weight, chunk with "memória" should rank high
        top_chunk, _ = reranked[0]
        assert "memória" in top_chunk.text.lower()

    def test_rerank_uses_real_chunk_position_instead_of_candidate_order(self):
        early_chunk = SourceChunk(
            document_id="doc1",
            filename="memoria.pdf",
            page=1,
            chunk_index=0,
            score=0.80,
            text="Resumo sobre gestão de contratos.",
            document_chunk_count=10,
        )
        late_chunk = SourceChunk(
            document_id="doc1",
            filename="memoria.pdf",
            page=8,
            chunk_index=8,
            score=0.80,
            text="Resumo sobre gestão de contratos.",
            document_chunk_count=10,
        )

        reranked = rerank_hybrid("gestão de contratos", [(late_chunk, 0.80), (early_chunk, 0.80)])

        top_chunk, _ = reranked[0]
        assert top_chunk.chunk_index == 0


class TestFormatRankingExplanation:
    """Test ranking score formatting."""

    def test_format_output_format(self):
        scores = RankingScores(
            vector_score=0.95,
            keyword_overlap=0.25,
            position_penalty=0.90,
            density_score=0.85,
            recency_boost=1.0,
            final_score=0.88,
        )
        explanation = format_ranking_explanation(scores)
        
        assert "vector=" in explanation
        assert "keyword=" in explanation
        assert "position=" in explanation
        assert "density=" in explanation
        assert "final=" in explanation
        assert "0.95" in explanation
        assert "0.88" in explanation
