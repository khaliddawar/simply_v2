# Summarization Quality Improvements - Implementation Plan

## Overview

This document outlines the executable implementation steps for fixing redundancy issues in the multi-step summarization system.

**Target File:** `backend/app/services/summarization_service.py`

---

## Phase 1: Quick Wins

### Task 1A: Enhanced Executive Summary Prompt

**Objective:** Modify `EXECUTIVE_SUMMARY_PROMPT` to explicitly handle redundancy.

**Changes Required:**

```python
# Location: summarization_service.py lines 84-109
# Replace EXECUTIVE_SUMMARY_PROMPT with:

EXECUTIVE_SUMMARY_PROMPT = """Based on these section summaries, create a comprehensive executive summary of the entire video.

VIDEO TITLE: {video_title}

SECTION SUMMARIES:
{section_summaries}

CRITICAL INSTRUCTIONS FOR HANDLING REPETITION:
1. If the same point, example, or anecdote appears across multiple sections, mention it ONLY ONCE
2. Consolidate repeated themes into single, comprehensive statements
3. Prioritize UNIQUE insights over frequently repeated points
4. The source video may intentionally repeat key messages - your job is to SYNTHESIZE, not echo
5. Each key takeaway must be DISTINCT - no near-duplicates allowed

Create:
1. A thorough executive summary (4-6 sentences) that CONSOLIDATES repeated themes into single mentions
2. 5-8 UNIQUE key takeaways - each must provide NEW information not covered by other takeaways
3. Who would benefit from this video (target audience with specific characteristics)

Respond in JSON format:
{{
    "executive_summary": "4-6 sentence comprehensive overview - mention repeated themes ONCE only",
    "key_takeaways": ["Unique takeaway 1", "Unique takeaway 2", ...],
    "target_audience": "Detailed description of who should watch this and why"
}}

Critical requirements:
- The executive summary should synthesize information from ALL sections coherently
- Key takeaways must be specific, actionable, and MUTUALLY EXCLUSIVE (no overlapping points)
- ONLY include information that appears in the section summaries - no external knowledge
- If a topic (e.g., "risk management") appears in 5 sections, summarize it ONCE comprehensively
- Output ONLY valid JSON"""
```

**Test Specification:**
- Input: Section summaries with repeated "$700K Tilray loss" across 5 sections
- Expected: Executive summary mentions the loss exactly ONCE
- Expected: Key takeaways contain no duplicate/near-duplicate points

---

### Task 1B: Post-Processing Consolidation Step

**Objective:** Add a new method `consolidate_summary()` that deduplicates the final output.

**New Method to Add:**

```python
# Add after generate_executive_summary() method (around line 270)

CONSOLIDATION_PROMPT = """Review this video summary and remove ALL redundant/repeated content.

CURRENT SUMMARY:
{summary_json}

YOUR TASKS:
1. IDENTIFY repeated information across sections (same events, facts, examples mentioned multiple times)
2. For each repeated item, KEEP the most detailed version in ONE section only
3. In other sections, either REMOVE the repeated content or replace with a brief reference like "As mentioned earlier..."
4. MERGE duplicate key_takeaways into single comprehensive points
5. Ensure the executive_summary mentions each major theme exactly ONCE

RULES:
- Each specific fact/event/example should appear in detail in ONE section only
- Key takeaways must be mutually exclusive - no two should cover the same ground
- Preserve all UNIQUE information - only remove/merge DUPLICATES
- Maintain the same JSON structure

Return the DEDUPLICATED summary in the exact same JSON structure.
Output ONLY valid JSON."""

async def consolidate_summary(self, raw_summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process the summary to remove cross-section redundancy.

    This is the final step that catches any repetition that slipped through
    the section-level summarization.
    """
    if not self.is_available():
        return raw_summary

    try:
        # Prepare summary for consolidation (exclude metadata)
        summary_for_consolidation = {
            "executive_summary": raw_summary.get("executive_summary", ""),
            "key_takeaways": raw_summary.get("key_takeaways", []),
            "target_audience": raw_summary.get("target_audience", ""),
            "sections": raw_summary.get("sections", [])
        }

        prompt = CONSOLIDATION_PROMPT.format(
            summary_json=json.dumps(summary_for_consolidation, indent=2)
        )

        result = await self._call_llm(prompt, temperature=0.2)

        if "error" in result:
            logger.warning(f"Consolidation failed, returning original: {result['error']}")
            return raw_summary

        # Merge consolidated content back with original metadata
        consolidated = {
            **raw_summary,
            "executive_summary": result.get("executive_summary", raw_summary.get("executive_summary", "")),
            "key_takeaways": result.get("key_takeaways", raw_summary.get("key_takeaways", [])),
            "target_audience": result.get("target_audience", raw_summary.get("target_audience", "")),
            "sections": result.get("sections", raw_summary.get("sections", [])),
            "metadata": {
                **raw_summary.get("metadata", {}),
                "consolidated": True
            }
        }

        logger.info("Summary consolidated successfully")
        return consolidated

    except Exception as e:
        logger.error(f"Error consolidating summary: {e}")
        return raw_summary
```

**Integration Point:**
```python
# In generate_summary() method, after compiling the result (around line 374):
# Add consolidation step before returning

# Before: return result
# After:
result = await self.consolidate_summary(result)
return result
```

**Test Specification:**
- Input: Raw summary with "$700K loss" in 6 sections
- Expected: Consolidated output with "$700K loss" detailed in 1 section, brief/no mention in others
- Expected: `metadata.consolidated = True`

---

## Phase 2: Architectural Improvements

### Task 2A: Cross-Section Context Passing

**Objective:** Modify `summarize_section()` to receive and use previous section summaries.

**Changes Required:**

```python
# New prompt with context awareness (add after existing prompts)

CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT = """You are an expert summarizer. Generate a comprehensive summary of the following section using Chain of Density technique.

SECTION TITLE: {section_title}
SECTION CONTENT:
{section_content}

{previous_context}

Your task:
1. First, write an initial summary (5-7 sentences) covering the main points thoroughly
2. Then, identify 3-4 key entities/facts that are missing from your summary
3. Rewrite the summary to include these entities while maintaining clarity
4. Repeat step 2-3 one more time (total 3 iterations)

CRITICAL: Focus on information that is NEW and UNIQUE to this section.
If something was already covered in previous sections, do NOT repeat it in detail.
You may briefly reference it (e.g., "Building on the earlier discussion of X...") but focus your summary on NEW content.

After 3 iterations, provide your final dense summary.

Respond in JSON format:
{{
    "summary": "Your final dense summary (5-7 sentences, focusing on NEW information)",
    "key_points": ["Key point 1", "Key point 2", "Key point 3", "Key point 4", "Key point 5"],
    "entities": ["Important entity 1", "Important entity 2", "Important entity 3"],
    "references_previous": ["Brief note of any topics that connect to previous sections"]
}}

Critical requirements:
- Prioritize NEW information unique to this section
- Do NOT repeat facts/examples already covered in previous sections
- Include 4-6 key points that are actionable or memorable takeaways
- Entities are important names, terms, numbers, or concepts EXPLICITLY mentioned
- Output ONLY valid JSON"""


# Modified summarize_section method signature and implementation

async def summarize_section(
    self,
    section_title: str,
    section_content: str,
    previous_summaries: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Apply Chain of Density summarization to a section.

    Args:
        section_title: Title of the section
        section_content: Content to summarize
        previous_summaries: List of summaries from previous sections (for context)
    """
    truncated = section_content[:8000] if len(section_content) > 8000 else section_content

    # Build context from previous sections
    previous_context = ""
    if previous_summaries:
        context_parts = ["PREVIOUSLY COVERED (do NOT repeat these in detail):"]
        for ps in previous_summaries:
            title = ps.get('title', 'Previous Section')
            key_points = ps.get('key_points', [])
            if key_points:
                points_str = "; ".join(key_points[:3])  # Top 3 points
                context_parts.append(f"- {title}: {points_str}")
        previous_context = "\n".join(context_parts)

    # Use context-aware prompt if we have previous sections
    if previous_summaries:
        prompt = CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT.format(
            section_title=section_title,
            section_content=truncated,
            previous_context=previous_context
        )
    else:
        # First section - use original prompt
        prompt = CHAIN_OF_DENSITY_PROMPT.format(
            section_title=section_title,
            section_content=truncated
        )

    result = await self._call_llm(prompt, temperature=0.3)

    if "error" in result:
        return {
            "summary": f"Summary for {section_title} could not be generated.",
            "key_points": [],
            "entities": []
        }

    return result
```

**Integration in generate_summary():**
```python
# Modify the section processing loop (around lines 317-348)

section_summaries = []

for i, section in enumerate(sections):
    logger.info(f"  Processing section {i+1}/{len(sections)}: {section.get('title')}")

    # Extract content for this section
    section_content = self._extract_section_content(
        transcript,
        section.get("start_time", "0:00"),
        section.get("end_time", "99:99")
    )

    # If no content extracted, use a portion of the transcript
    if not section_content or len(section_content) < 100:
        chunk_size = len(transcript) // len(sections)
        start = i * chunk_size
        end = (i + 1) * chunk_size
        section_content = transcript[start:end]

    # Apply Chain of Density with context from previous sections
    section_summary = await self.summarize_section(
        section.get("title", f"Section {i+1}"),
        section_content,
        previous_summaries=section_summaries if i > 0 else None  # NEW
    )

    section_summaries.append({
        "title": section.get("title", f"Section {i+1}"),
        "timestamp": f"{section.get('start_time', '0:00')} - {section.get('end_time', '')}",
        "description": section.get("description", ""),
        "summary": section_summary.get("summary", ""),
        "key_points": section_summary.get("key_points", []),
        "entities": section_summary.get("entities", [])
    })
```

**Test Specification:**
- Input: Transcript where "Tilray loss" is mentioned in segments 1, 3, 5
- Expected: Section 1 has full details, Sections 3 and 5 have brief references or skip
- Verify: `previous_summaries` parameter is passed correctly

---

### Task 2B: MMR-based Key Point Deduplication

**Objective:** Add semantic deduplication of key points using MMR-inspired approach.

**New Method to Add:**

```python
# Add new method for key point deduplication

MMR_DEDUP_PROMPT = """You are a deduplication expert. Given a list of key points from a video summary,
identify and merge semantically similar points while preserving unique insights.

KEY POINTS TO DEDUPLICATE:
{key_points_json}

YOUR TASK:
1. Group points that convey the same or very similar information
2. For each group, create ONE comprehensive point that captures all the nuances
3. Keep points that are genuinely unique and distinct
4. Aim for 5-8 final points maximum

SCORING CRITERIA (MMR-inspired):
- Relevance: How important/actionable is the point?
- Novelty: How different is it from other selected points?
- Select points that maximize: relevance + novelty

Return JSON:
{{
    "deduplicated_points": [
        "Comprehensive unique point 1",
        "Comprehensive unique point 2",
        ...
    ],
    "merge_log": [
        {{"merged": ["original point A", "original point B"], "into": "merged point"}},
        ...
    ]
}}

Output ONLY valid JSON."""


async def deduplicate_key_points(
    self,
    all_points: List[str],
    max_points: int = 8
) -> List[str]:
    """
    Apply MMR-inspired deduplication to key points.

    Uses LLM to identify semantically similar points and merge them,
    while preserving unique insights.

    Args:
        all_points: List of all key points from all sections
        max_points: Maximum number of points to return

    Returns:
        Deduplicated list of key points
    """
    if not all_points:
        return []

    # If already under limit and few points, skip dedup
    if len(all_points) <= max_points:
        return all_points

    if not self.is_available():
        # Fallback: simple truncation
        return all_points[:max_points]

    try:
        prompt = MMR_DEDUP_PROMPT.format(
            key_points_json=json.dumps(all_points, indent=2)
        )

        result = await self._call_llm(prompt, temperature=0.2)

        if "error" in result:
            logger.warning(f"Deduplication failed: {result['error']}")
            return all_points[:max_points]

        deduplicated = result.get("deduplicated_points", all_points)

        # Log merge operations for debugging
        merge_log = result.get("merge_log", [])
        if merge_log:
            logger.info(f"Merged {len(merge_log)} groups of similar key points")

        return deduplicated[:max_points]

    except Exception as e:
        logger.error(f"Error deduplicating key points: {e}")
        return all_points[:max_points]
```

**Integration in generate_summary():**
```python
# Modify key points compilation (around lines 354-357)

# Compile all key points
all_key_points = []
for s in section_summaries:
    all_key_points.extend(s.get("key_points", []))

# NEW: Apply MMR-based deduplication
logger.info(f"Deduplicating {len(all_key_points)} key points...")
deduplicated_key_points = await self.deduplicate_key_points(all_key_points)
logger.info(f"Reduced to {len(deduplicated_key_points)} unique points")

# Use deduplicated points in result (but keep executive's key_takeaways as primary)
# The section-level key_points remain for detailed view
```

**Test Specification:**
- Input: 20 key points with 5 variations of "don't exceed 1% of float"
- Expected: Output of 5-8 points with ONE consolidated "1% float" point
- Expected: `merge_log` shows which points were merged

---

## Test Suite Specification

### File: `backend/tests/test_summarization_dedup.py`

```python
"""
Test suite for summarization deduplication improvements.
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.summarization_service import SummarizationService


class TestSummarizationDeduplication:
    """Tests for redundancy removal in summarization."""

    @pytest.fixture
    def service(self):
        """Create a summarization service instance."""
        with patch.object(SummarizationService, '__init__', lambda x: None):
            svc = SummarizationService()
            svc.settings = type('Settings', (), {'llm_model': 'gpt-4o-mini', 'llm_max_tokens': 4000})()
            svc.client = AsyncMock()
            return svc

    # Test 1: Executive summary consolidates repeated themes
    @pytest.mark.asyncio
    async def test_executive_summary_consolidates_repetition(self, service):
        """Executive summary should mention repeated themes only once."""
        section_summaries = [
            {"title": "Section 1", "summary": "Lost $700K on Tilray. Important lesson.", "key_points": ["Lost $700K on Tilray"]},
            {"title": "Section 2", "summary": "The $700K Tilray loss was painful.", "key_points": ["$700K Tilray loss"]},
            {"title": "Section 3", "summary": "Recovered from $700K Tilray mistake.", "key_points": ["Recovered from $700K loss"]},
        ]

        # Mock LLM response
        service._call_llm = AsyncMock(return_value={
            "executive_summary": "The trader experienced a significant $700K loss on Tilray but recovered quickly.",
            "key_takeaways": ["Major losses can be recovered with discipline"],
            "target_audience": "Traders learning risk management"
        })

        result = await service.generate_executive_summary("Test Video", section_summaries)

        # Count mentions of "700" in executive summary
        mentions = result["executive_summary"].lower().count("700")
        assert mentions <= 1, f"Expected max 1 mention of $700K, got {mentions}"

    # Test 2: Cross-section context is passed correctly
    @pytest.mark.asyncio
    async def test_cross_section_context_passed(self, service):
        """Later sections should receive previous section summaries."""
        service._call_llm = AsyncMock(return_value={
            "summary": "Test summary",
            "key_points": ["Point 1"],
            "entities": ["Entity 1"]
        })

        previous = [
            {"title": "Intro", "key_points": ["Lost $700K on Tilray", "Patience is key"]}
        ]

        await service.summarize_section("Section 2", "Some content", previous_summaries=previous)

        # Verify the prompt included previous context
        call_args = service._call_llm.call_args[0][0]
        assert "PREVIOUSLY COVERED" in call_args or "Tilray" in call_args

    # Test 3: Key points are deduplicated
    @pytest.mark.asyncio
    async def test_key_points_deduplicated(self, service):
        """Duplicate key points should be merged."""
        all_points = [
            "Don't exceed 1% of float when trading",
            "Never trade more than 1% of a stock's float",
            "Keep position size under 1% of float",
            "Patience is crucial in trading",
            "Wait for the right opportunities",
            "Use moving averages for entries"
        ]

        service._call_llm = AsyncMock(return_value={
            "deduplicated_points": [
                "Limit position size to 1% of a stock's float",
                "Exercise patience and wait for optimal opportunities",
                "Use moving averages to time entries"
            ],
            "merge_log": [
                {"merged": ["Don't exceed 1%...", "Never trade more...", "Keep position..."], "into": "Limit position size..."}
            ]
        })

        result = await service.deduplicate_key_points(all_points)

        assert len(result) < len(all_points), "Should have fewer points after dedup"
        assert len(result) <= 8, "Should not exceed max points"

    # Test 4: Consolidation step removes cross-section redundancy
    @pytest.mark.asyncio
    async def test_consolidation_removes_redundancy(self, service):
        """Post-processing consolidation should deduplicate across sections."""
        raw_summary = {
            "executive_summary": "Video about trading with $700K loss mentioned.",
            "key_takeaways": ["Lost $700K", "Recovered from $700K loss"],
            "sections": [
                {"title": "S1", "summary": "Lost $700K on Tilray", "key_points": ["$700K loss"]},
                {"title": "S2", "summary": "The $700K Tilray loss hurt", "key_points": ["$700K Tilray loss"]},
            ],
            "metadata": {"model": "test"}
        }

        service._call_llm = AsyncMock(return_value={
            "executive_summary": "Video discusses a significant trading loss and recovery.",
            "key_takeaways": ["Major losses can be recovered with discipline"],
            "sections": [
                {"title": "S1", "summary": "Lost $700K on Tilray - a defining moment", "key_points": ["$700K Tilray loss"]},
                {"title": "S2", "summary": "Recovery strategies employed after the setback", "key_points": ["Quick recovery approach"]},
            ],
            "target_audience": "Traders"
        })

        result = await service.consolidate_summary(raw_summary)

        assert result["metadata"].get("consolidated") == True
        # Check that S2 no longer duplicates the $700K details
        s2_summary = result["sections"][1]["summary"]
        assert "700" not in s2_summary.lower() or "earlier" in s2_summary.lower()

    # Test 5: First section gets no previous context
    @pytest.mark.asyncio
    async def test_first_section_no_previous_context(self, service):
        """First section should not receive previous_summaries."""
        service._call_llm = AsyncMock(return_value={
            "summary": "Test", "key_points": [], "entities": []
        })

        await service.summarize_section("Intro", "Content", previous_summaries=None)

        call_args = service._call_llm.call_args[0][0]
        assert "PREVIOUSLY COVERED" not in call_args

    # Test 6: Graceful fallback on LLM failure
    @pytest.mark.asyncio
    async def test_consolidation_fallback_on_error(self, service):
        """Should return original summary if consolidation fails."""
        raw_summary = {"executive_summary": "Test", "sections": [], "metadata": {}}

        service._call_llm = AsyncMock(return_value={"error": "API error"})
        service.is_available = lambda: True

        result = await service.consolidate_summary(raw_summary)

        assert result == raw_summary  # Original returned on failure
        assert "consolidated" not in result.get("metadata", {})


class TestIntegration:
    """Integration tests for the full summarization pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_reduces_redundancy(self):
        """Full pipeline should produce non-redundant output."""
        # This would be a longer integration test with real or mocked LLM
        pass  # Implement with actual test transcript
```

---

## Validation Checklist

After implementation, verify:

- [ ] `EXECUTIVE_SUMMARY_PROMPT` updated with deduplication instructions
- [ ] `CONSOLIDATION_PROMPT` added
- [ ] `consolidate_summary()` method implemented
- [ ] `CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT` added
- [ ] `summarize_section()` accepts `previous_summaries` parameter
- [ ] `MMR_DEDUP_PROMPT` added
- [ ] `deduplicate_key_points()` method implemented
- [ ] `generate_summary()` calls consolidation step
- [ ] `generate_summary()` passes previous summaries to sections
- [ ] All tests pass
- [ ] Manual test with repetitive video shows reduced redundancy

---

*Implementation Plan Created: 2026-01-10*
