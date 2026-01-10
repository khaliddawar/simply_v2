"""
Test suite for summarization deduplication improvements.

Tests the following features:
1. Enhanced executive summary prompt consolidates repetition
2. Cross-section context passing prevents redundancy
3. MMR-based key point deduplication
4. Post-processing consolidation step
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any, List


class TestSummarizationDeduplication:
    """Tests for redundancy removal in summarization."""

    @pytest.fixture
    def mock_service(self):
        """Create a mocked summarization service instance."""
        # Import here to avoid issues if module not yet modified
        from app.services.summarization_service import SummarizationService

        with patch.object(SummarizationService, '__init__', lambda x: None):
            svc = SummarizationService()
            svc.settings = MagicMock()
            svc.settings.llm_model = 'gpt-4o-mini'
            svc.settings.llm_max_tokens = 4000
            svc.client = AsyncMock()
            svc.is_available = lambda: True
            return svc

    # Test 1: Executive summary consolidates repeated themes
    @pytest.mark.asyncio
    async def test_executive_summary_prompt_includes_dedup_instructions(self):
        """Verify executive summary prompt contains deduplication instructions."""
        from app.services.summarization_service import EXECUTIVE_SUMMARY_PROMPT

        # Check for key deduplication instructions
        assert "ONLY ONCE" in EXECUTIVE_SUMMARY_PROMPT or "once" in EXECUTIVE_SUMMARY_PROMPT.lower()
        assert "CONSOLIDATE" in EXECUTIVE_SUMMARY_PROMPT or "consolidate" in EXECUTIVE_SUMMARY_PROMPT.lower()
        assert "repeated" in EXECUTIVE_SUMMARY_PROMPT.lower() or "repetition" in EXECUTIVE_SUMMARY_PROMPT.lower()

    # Test 2: Cross-section context prompt exists
    @pytest.mark.asyncio
    async def test_context_aware_prompt_exists(self):
        """Verify context-aware prompt is defined."""
        from app.services.summarization_service import CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT

        assert "PREVIOUSLY COVERED" in CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT or "previous" in CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT.lower()
        assert "NEW" in CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT
        assert "UNIQUE" in CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT or "unique" in CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT.lower()

    # Test 3: summarize_section accepts previous_summaries parameter
    @pytest.mark.asyncio
    async def test_summarize_section_accepts_previous_summaries(self, mock_service):
        """Verify summarize_section has previous_summaries parameter."""
        import inspect
        from app.services.summarization_service import SummarizationService

        sig = inspect.signature(SummarizationService.summarize_section)
        params = list(sig.parameters.keys())

        assert 'previous_summaries' in params, "summarize_section should accept previous_summaries parameter"

    # Test 4: Cross-section context is built correctly
    @pytest.mark.asyncio
    async def test_cross_section_context_built(self, mock_service):
        """Later sections should receive previous section summaries in prompt."""
        mock_service._call_llm = AsyncMock(return_value={
            "summary": "Test summary focusing on new content",
            "key_points": ["New point 1"],
            "entities": ["Entity 1"]
        })

        previous = [
            {"title": "Intro", "key_points": ["Lost $700K on Tilray", "Patience is key"]},
            {"title": "Strategy", "key_points": ["Use moving averages", "Risk management"]}
        ]

        await mock_service.summarize_section(
            "Section 3",
            "Some new content about recovery",
            previous_summaries=previous
        )

        # Get the prompt that was passed to _call_llm
        call_args = mock_service._call_llm.call_args[0][0]

        # Should contain previous section information
        assert "PREVIOUSLY COVERED" in call_args or "Tilray" in call_args or "Intro" in call_args

    # Test 5: First section gets no previous context
    @pytest.mark.asyncio
    async def test_first_section_no_previous_context(self, mock_service):
        """First section should not include previous context in prompt."""
        mock_service._call_llm = AsyncMock(return_value={
            "summary": "Test", "key_points": [], "entities": []
        })

        await mock_service.summarize_section("Intro", "Content", previous_summaries=None)

        call_args = mock_service._call_llm.call_args[0][0]
        assert "PREVIOUSLY COVERED" not in call_args

    # Test 6: Key points are deduplicated
    @pytest.mark.asyncio
    async def test_deduplicate_key_points_reduces_count(self, mock_service):
        """Duplicate key points should be merged."""
        all_points = [
            "Don't exceed 1% of float when trading",
            "Never trade more than 1% of a stock's float",
            "Keep position size under 1% of float",
            "Patience is crucial in trading",
            "Wait for the right opportunities",
            "Use moving averages for entries",
            "Moving averages help time entries",
            "Risk management is essential",
            "Manage your risk carefully",
            "Always have stop losses"
        ]

        mock_service._call_llm = AsyncMock(return_value={
            "deduplicated_points": [
                "Limit position size to 1% of a stock's float",
                "Exercise patience and wait for optimal opportunities",
                "Use moving averages to time entries",
                "Implement proper risk management with stop losses"
            ],
            "merge_log": [
                {"merged": ["Don't exceed 1%...", "Never trade more...", "Keep position..."], "into": "Limit position size..."}
            ]
        })

        result = await mock_service.deduplicate_key_points(all_points)

        assert len(result) < len(all_points), "Should have fewer points after dedup"
        assert len(result) <= 8, "Should not exceed max points"

    # Test 7: Deduplication skips when under threshold
    @pytest.mark.asyncio
    async def test_deduplicate_skips_small_lists(self, mock_service):
        """Should not call LLM if points already under max."""
        small_list = ["Point 1", "Point 2", "Point 3"]

        mock_service._call_llm = AsyncMock()

        result = await mock_service.deduplicate_key_points(small_list, max_points=8)

        # Should return original without LLM call
        assert result == small_list
        mock_service._call_llm.assert_not_called()

    # Test 8: Consolidation step exists and is called
    @pytest.mark.asyncio
    async def test_consolidate_summary_method_exists(self, mock_service):
        """Verify consolidate_summary method exists."""
        assert hasattr(mock_service, 'consolidate_summary'), "consolidate_summary method should exist"

    # Test 9: Consolidation adds metadata flag
    @pytest.mark.asyncio
    async def test_consolidation_adds_metadata_flag(self, mock_service):
        """Consolidated summaries should have metadata.consolidated = True."""
        raw_summary = {
            "executive_summary": "Test summary",
            "key_takeaways": ["Point 1"],
            "target_audience": "Traders",
            "sections": [{"title": "S1", "summary": "Content", "key_points": []}],
            "metadata": {"model": "test"}
        }

        mock_service._call_llm = AsyncMock(return_value={
            "executive_summary": "Consolidated summary",
            "key_takeaways": ["Consolidated point"],
            "target_audience": "Traders",
            "sections": [{"title": "S1", "summary": "Consolidated content", "key_points": []}]
        })

        result = await mock_service.consolidate_summary(raw_summary)

        assert result["metadata"].get("consolidated") == True

    # Test 10: Consolidation fallback on error
    @pytest.mark.asyncio
    async def test_consolidation_fallback_on_error(self, mock_service):
        """Should return original summary if consolidation fails."""
        raw_summary = {
            "executive_summary": "Test",
            "sections": [],
            "metadata": {}
        }

        mock_service._call_llm = AsyncMock(return_value={"error": "API error"})

        result = await mock_service.consolidate_summary(raw_summary)

        # Should return original on failure
        assert result["executive_summary"] == "Test"
        assert "consolidated" not in result.get("metadata", {})

    # Test 11: MMR prompt exists
    @pytest.mark.asyncio
    async def test_mmr_dedup_prompt_exists(self):
        """Verify MMR deduplication prompt is defined."""
        from app.services.summarization_service import MMR_DEDUP_PROMPT

        assert "deduplicated_points" in MMR_DEDUP_PROMPT
        assert "merge" in MMR_DEDUP_PROMPT.lower()

    # Test 12: Consolidation prompt exists
    @pytest.mark.asyncio
    async def test_consolidation_prompt_exists(self):
        """Verify consolidation prompt is defined."""
        from app.services.summarization_service import CONSOLIDATION_PROMPT

        assert "redundant" in CONSOLIDATION_PROMPT.lower() or "repeated" in CONSOLIDATION_PROMPT.lower()


class TestConsolidateSummaryIntegration:
    """Integration tests for consolidate_summary with realistic data."""

    @pytest.fixture
    def mock_service(self):
        """Create a mocked summarization service instance."""
        from app.services.summarization_service import SummarizationService

        with patch.object(SummarizationService, '__init__', lambda x: None):
            svc = SummarizationService()
            svc.settings = MagicMock()
            svc.settings.llm_model = 'gpt-4o-mini'
            svc.settings.llm_max_tokens = 4000
            svc.client = AsyncMock()
            svc.is_available = lambda: True
            return svc

    @pytest.mark.asyncio
    async def test_consolidation_preserves_structure(self, mock_service):
        """Consolidation should maintain the same JSON structure."""
        raw_summary = {
            "executive_summary": "Original executive summary",
            "key_takeaways": ["Takeaway 1", "Takeaway 2"],
            "target_audience": "Traders and investors",
            "sections": [
                {"title": "Section 1", "summary": "Content 1", "key_points": ["Point 1"]},
                {"title": "Section 2", "summary": "Content 2", "key_points": ["Point 2"]}
            ],
            "video_title": "Test Video",
            "metadata": {"model": "gpt-4o-mini"}
        }

        mock_service._call_llm = AsyncMock(return_value={
            "executive_summary": "Consolidated executive summary",
            "key_takeaways": ["Merged takeaway"],
            "target_audience": "Traders and investors",
            "sections": [
                {"title": "Section 1", "summary": "Consolidated 1", "key_points": ["Point 1"]},
                {"title": "Section 2", "summary": "Consolidated 2", "key_points": ["Point 2"]}
            ]
        })

        result = await mock_service.consolidate_summary(raw_summary)

        # Verify structure is preserved
        assert "executive_summary" in result
        assert "key_takeaways" in result
        assert "target_audience" in result
        assert "sections" in result
        assert "metadata" in result
        # Verify original fields are preserved
        assert result.get("video_title") == "Test Video"

    @pytest.mark.asyncio
    async def test_consolidation_handles_empty_sections(self, mock_service):
        """Consolidation should handle summaries with empty sections."""
        raw_summary = {
            "executive_summary": "Summary",
            "key_takeaways": [],
            "target_audience": "",
            "sections": [],
            "metadata": {}
        }

        mock_service._call_llm = AsyncMock(return_value={
            "executive_summary": "Summary",
            "key_takeaways": [],
            "target_audience": "",
            "sections": []
        })

        result = await mock_service.consolidate_summary(raw_summary)

        assert result["executive_summary"] == "Summary"
        assert result["sections"] == []


class TestIntegration:
    """Integration tests for the full summarization pipeline."""

    @pytest.fixture
    def service(self):
        """Create real service instance for integration tests."""
        from app.services.summarization_service import SummarizationService
        return SummarizationService()

    @pytest.mark.asyncio
    async def test_generate_summary_calls_consolidation(self):
        """Verify generate_summary includes consolidation step."""
        from app.services.summarization_service import SummarizationService

        with patch.object(SummarizationService, '__init__', lambda x: None):
            svc = SummarizationService()
            svc.settings = MagicMock()
            svc.settings.llm_model = 'gpt-4o-mini'
            svc.settings.llm_max_tokens = 4000
            svc.settings.openai_api_key = 'test'
            svc.client = AsyncMock()
            svc.is_available = lambda: True

            # Mock all LLM calls
            svc._call_llm = AsyncMock(side_effect=[
                # detect_topics response
                {"sections": [{"title": "Intro", "start_time": "0:00", "end_time": "5:00", "description": "Introduction"}]},
                # summarize_section response
                {"summary": "Section summary", "key_points": ["Point 1"], "entities": []},
                # generate_executive_summary response
                {"executive_summary": "Executive summary", "key_takeaways": ["Takeaway"], "target_audience": "Everyone"},
                # consolidate_summary response
                {"executive_summary": "Consolidated", "key_takeaways": ["Consolidated takeaway"], "target_audience": "Everyone", "sections": []}
            ])

            result = await svc.generate_summary("Test transcript", "Test Video")

            # Verify consolidation was called (4th LLM call)
            assert svc._call_llm.call_count >= 4, "Should call LLM for consolidation step"
            assert result.get("metadata", {}).get("consolidated") == True

    @pytest.mark.asyncio
    async def test_consolidation_prompt_format(self):
        """Verify the consolidation prompt is correctly formatted."""
        from app.services.summarization_service import CONSOLIDATION_PROMPT

        # The prompt should have a placeholder for summary_json
        assert "{summary_json}" in CONSOLIDATION_PROMPT

        # Test that the prompt can be formatted
        test_summary = {"test": "data"}
        formatted = CONSOLIDATION_PROMPT.format(summary_json=json.dumps(test_summary))
        assert "test" in formatted
        assert "data" in formatted


class TestPromptContents:
    """Tests for prompt content and structure."""

    def test_executive_summary_prompt_structure(self):
        """Verify executive summary prompt has required placeholders."""
        from app.services.summarization_service import EXECUTIVE_SUMMARY_PROMPT

        assert "{video_title}" in EXECUTIVE_SUMMARY_PROMPT
        assert "{section_summaries}" in EXECUTIVE_SUMMARY_PROMPT

    def test_chain_of_density_prompt_structure(self):
        """Verify chain of density prompt has required placeholders."""
        from app.services.summarization_service import CHAIN_OF_DENSITY_PROMPT

        assert "{section_title}" in CHAIN_OF_DENSITY_PROMPT
        assert "{section_content}" in CHAIN_OF_DENSITY_PROMPT

    def test_topic_detection_prompt_structure(self):
        """Verify topic detection prompt has required placeholders."""
        from app.services.summarization_service import TOPIC_DETECTION_PROMPT

        assert "{transcript}" in TOPIC_DETECTION_PROMPT

    def test_consolidation_prompt_contains_dedup_instructions(self):
        """Verify consolidation prompt contains deduplication instructions."""
        from app.services.summarization_service import CONSOLIDATION_PROMPT

        prompt_lower = CONSOLIDATION_PROMPT.lower()
        # Should mention removing redundancy
        assert "redundant" in prompt_lower or "repeated" in prompt_lower or "duplicate" in prompt_lower
        # Should mention merging
        assert "merge" in prompt_lower


class TestSummarizationServiceMethods:
    """Tests for individual service methods."""

    @pytest.fixture
    def mock_service(self):
        """Create a mocked summarization service instance."""
        from app.services.summarization_service import SummarizationService

        with patch.object(SummarizationService, '__init__', lambda x: None):
            svc = SummarizationService()
            svc.settings = MagicMock()
            svc.settings.llm_model = 'gpt-4o-mini'
            svc.settings.llm_max_tokens = 4000
            svc.client = AsyncMock()
            svc.is_available = lambda: True
            return svc

    @pytest.mark.asyncio
    async def test_detect_topics_returns_sections(self, mock_service):
        """Verify detect_topics returns proper section structure."""
        mock_service._call_llm = AsyncMock(return_value={
            "sections": [
                {"title": "Intro", "start_time": "0:00", "end_time": "2:00", "description": "Introduction"},
                {"title": "Main", "start_time": "2:00", "end_time": "5:00", "description": "Main content"}
            ]
        })

        result = await mock_service.detect_topics("Test transcript content")

        assert "sections" in result
        assert len(result["sections"]) == 2
        assert result["sections"][0]["title"] == "Intro"

    @pytest.mark.asyncio
    async def test_summarize_section_returns_required_fields(self, mock_service):
        """Verify summarize_section returns summary, key_points, entities."""
        mock_service._call_llm = AsyncMock(return_value={
            "summary": "This is the section summary",
            "key_points": ["Point 1", "Point 2"],
            "entities": ["Entity 1"]
        })

        result = await mock_service.summarize_section("Test Section", "Section content here")

        assert "summary" in result
        assert "key_points" in result
        assert "entities" in result
        assert isinstance(result["key_points"], list)

    @pytest.mark.asyncio
    async def test_generate_executive_summary_returns_required_fields(self, mock_service):
        """Verify generate_executive_summary returns proper structure."""
        mock_service._call_llm = AsyncMock(return_value={
            "executive_summary": "Overall summary of the video",
            "key_takeaways": ["Takeaway 1", "Takeaway 2"],
            "target_audience": "Developers and engineers"
        })

        section_summaries = [
            {"title": "Section 1", "summary": "Content 1", "timestamp": "0:00 - 2:00"}
        ]

        result = await mock_service.generate_executive_summary("Test Video", section_summaries)

        assert "executive_summary" in result
        assert "key_takeaways" in result
        assert "target_audience" in result

    @pytest.mark.asyncio
    async def test_service_unavailable_returns_error(self, mock_service):
        """Verify service returns error when unavailable."""
        mock_service.is_available = lambda: False
        mock_service.client = None

        result = await mock_service.generate_summary("Test transcript", "Test Video")

        assert result.get("success") is False
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
