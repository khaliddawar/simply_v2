"""
Summarization Service

Implements a hybrid Map-Reduce + Refine approach for high-quality video transcript summarization:

NEW ARCHITECTURE (v2):
1. Fixed-Size Chunking - Split transcript into ~2000 token chunks with 15% overlap
2. MAP Step - Summarize each chunk independently (parallelizable)
3. REFINE Step - Sequentially assemble chunk summaries with context passing
4. Section Grouping - Group chunks into logical sections, generate titles from content
5. Final Consolidation - Remove redundancy using GPT-4o

LEGACY ARCHITECTURE (v1 - preserved for backward compatibility):
1. Topic Detection - Identifies distinct sections/topics in the transcript
2. Chain of Density (CoD) - Iteratively refines summaries for information density

This approach minimizes hallucinations while preserving key details and ensuring full coverage.
"""
import logging
import json
import re
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI

from app.settings import get_settings

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS FOR CHUNKING
# ============================================================================

# Target chunk size in characters (roughly 2000 tokens = ~8000 chars)
CHUNK_SIZE_CHARS = 8000
# Overlap between chunks (15%)
CHUNK_OVERLAP_CHARS = 1200
# Minimum chunk size to avoid tiny fragments
MIN_CHUNK_SIZE = 500

# ============================================================================
# PROMPTS
# ============================================================================

TOPIC_DETECTION_PROMPT = """Analyze this video transcript and identify distinct topic sections.

For each section, provide:
1. A clear title (2-5 words)
2. The approximate timestamp range (start-end in MM:SS format)
3. A detailed description of what's covered (2-3 sentences)

TRANSCRIPT:
{transcript}

Respond in JSON format:
{{
    "sections": [
        {{
            "title": "Section Title",
            "start_time": "0:00",
            "end_time": "2:30",
            "description": "Detailed description of this section covering main points discussed"
        }}
    ]
}}

Important:
- Identify 4-8 distinct sections based on topic changes
- If timestamps are in the transcript, use them; otherwise estimate based on content
- Keep section titles concise and descriptive
- ONLY include information that is explicitly stated in the transcript
- Do NOT infer or assume information not present in the text
- Output ONLY valid JSON, no additional text"""

CHAIN_OF_DENSITY_PROMPT = """You are an expert summarizer. Generate a comprehensive summary of the following section using Chain of Density technique.

SECTION TITLE: {section_title}
SECTION CONTENT:
{section_content}

Your task:
1. First, write an initial summary (5-7 sentences) covering the main points thoroughly
2. Then, identify 3-4 key entities/facts that are missing from your summary
3. Rewrite the summary to include these entities while maintaining clarity
4. Repeat step 2-3 one more time (total 3 iterations)

After 3 iterations, provide your final dense summary.

Respond in JSON format:
{{
    "summary": "Your final dense summary (5-7 sentences, comprehensive and information-rich)",
    "key_points": ["Key point 1", "Key point 2", "Key point 3", "Key point 4", "Key point 5"],
    "entities": ["Important entity/term 1", "Important entity/term 2", "Important entity/term 3"]
}}

Critical requirements:
- The final summary should be information-dense, comprehensive, and readable
- Include 4-6 key points that are actionable or memorable takeaways
- Entities are important names, terms, numbers, or concepts EXPLICITLY mentioned
- ONLY include facts directly stated in the source content - no speculation or inference
- If specific numbers, statistics, or quotes are mentioned, include them accurately
- Do NOT add information that is not present in the section content
- Output ONLY valid JSON"""

CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT = """You are an expert summarizer using the Delta Extraction approach.

SECTION TITLE: {section_title}
SECTION CONTENT:
{section_content}

{previous_context}

DELTA EXTRACTION APPROACH:
For topics/events already covered in previous sections, extract ONLY NEW DETAILS - not the base facts.

Example of what we want:
- Previous section mentioned: "Speaker lost $700K shorting Tilray in 2018"
- This section mentions it again but adds: "recovered the loss within a month"
- CORRECT: Include "recovered within a month" (NEW detail)
- WRONG: Repeat "lost $700K shorting Tilray" (BASE FACT already covered)

Your task:
1. Identify what topics from this section were already covered previously
2. For those topics, extract ONLY the new details, developments, or perspectives
3. For genuinely new topics, provide full context
4. Apply Chain of Density: iterate 2-3 times to increase information density

Respond in JSON format:
{{
    "summary": "5-7 sentences focusing on NEW details. For previously covered topics, mention only what's NEW (e.g., 'The speaker later recovered the Tilray loss within a month' NOT 'The speaker lost $700K on Tilray')",
    "key_points": ["Each point should be genuinely new information or a new perspective"],
    "entities": ["Important entities from THIS section"],
    "delta_notes": ["Brief note on what new info was added about previously covered topics"]
}}

Critical requirements:
- For recurring topics: extract the DELTA (new details), not the base facts
- Base facts belong in their FIRST mention only
- Later sections add context, outcomes, lessons, or new perspectives
- If this section adds nothing new about a topic, don't mention that topic
- Output ONLY valid JSON"""

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

CONSOLIDATION_PROMPT = """Apply Delta Consolidation to this video summary.

CURRENT SUMMARY:
{summary_json}

DELTA CONSOLIDATION APPROACH:
The goal is NOT to remove all repetition, but to ensure each section contributes UNIQUE VALUE.

For recurring topics (e.g., a major event mentioned in multiple sections):
- FIRST MENTION: Keep full base facts (who, what, when, where, how much)
- LATER MENTIONS: Keep ONLY new details (outcomes, lessons, perspectives, developments)

Example - Topic "Tilray loss" appearing in 5 sections:
- Section 1: "Lost $700K shorting Tilray in 2018" ✓ (base facts - KEEP)
- Section 3: "Lost $700K shorting Tilray in 2018" ✗ → "Recovered the loss within a month" ✓ (delta)
- Section 5: "Lost $700K shorting Tilray in 2018" ✗ → "Considers it his biggest trading mistake" ✓ (delta)
- Section 7: "Lost $700K shorting Tilray in 2018" ✗ → "The psychological toll affected later trades" ✓ (delta)

YOUR TASKS:
1. IDENTIFY base facts that appear multiple times (same event/example/statistic)
2. KEEP base facts in their FIRST detailed mention
3. In later sections, REPLACE base facts with the NEW details from that section
4. If a section adds NO new details about a topic, remove that topic from that section
5. PRESERVE genuinely new information - don't over-consolidate

PRESERVE THESE (they add value):
- New outcomes or results
- New perspectives or reflections
- New lessons learned
- Timeline progression (what happened next)
- Emotional/psychological aspects mentioned later

REMOVE THESE (pure repetition):
- Same statistic repeated verbatim
- Same event described the same way
- Same example with no new context

Return the consolidated summary in the exact same JSON structure.
Output ONLY valid JSON."""

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
        "Comprehensive unique point 2"
    ],
    "merge_log": [
        {{"merged": ["original point A", "original point B"], "into": "merged point"}}
    ]
}}

Output ONLY valid JSON."""

# ============================================================================
# LARGE CONTEXT PROMPT (for Gemini 2.0 Flash via OpenRouter)
# ============================================================================

LARGE_CONTEXT_SUMMARY_PROMPT = """You are an expert video summarizer. Analyze this COMPLETE video transcript and create a comprehensive, structured summary.

VIDEO TITLE: {video_title}

COMPLETE TRANSCRIPT:
{transcript}

YOUR TASK:
Create a thorough summary of this video with the following structure:

1. **Executive Summary** (4-6 sentences): A comprehensive overview capturing the main themes, key arguments, and overall message of the video.

2. **Sections** (4-8 sections): Break the video into logical topic sections. For each section provide:
   - A clear, descriptive title (2-5 words)
   - Approximate timestamp (estimate based on position in transcript)
   - A detailed summary (3-5 sentences)
   - 3-5 specific key points from that section
   - Important entities/names/numbers mentioned

3. **Key Takeaways** (5-8 points): The most important, actionable insights from the entire video. Each must be:
   - Specific and concrete (not generic advice)
   - Mutually exclusive (no overlapping points)
   - Include specific examples, numbers, or quotes where mentioned

4. **Target Audience**: Who would benefit most from this video and why.

CRITICAL REQUIREMENTS:
- Cover the ENTIRE transcript - do not skip any significant portion
- Each section should cover a distinct topic - no repetition between sections
- Key takeaways must be UNIQUE - if something appears in multiple sections, consolidate it
- Include specific numbers, names, examples, and quotes when mentioned
- Do NOT add information not present in the transcript
- Estimate timestamps based on position (e.g., content at 25% = ~15:00 for a 60-min video)

Respond in JSON format:
{{
    "executive_summary": "4-6 sentence comprehensive overview",
    "sections": [
        {{
            "title": "Section Title",
            "timestamp": "MM:SS - MM:SS",
            "summary": "3-5 sentence summary of this section",
            "key_points": ["Specific point 1", "Specific point 2"],
            "entities": ["Name/term 1", "Name/term 2"]
        }}
    ],
    "key_takeaways": ["Unique takeaway 1", "Unique takeaway 2"],
    "target_audience": "Detailed description of ideal viewer"
}}

Output ONLY valid JSON."""

# ============================================================================
# NEW PROMPTS FOR HYBRID ARCHITECTURE (v2)
# ============================================================================

CHUNK_SUMMARY_PROMPT = """You are an expert summarizer. Summarize this portion of a video transcript.

CHUNK CONTENT (this is part {chunk_index} of {total_chunks} from the video):
{chunk_content}

Your task:
1. Summarize the key information in this chunk (3-5 sentences)
2. Extract 3-5 key points that are specific and actionable
3. Suggest a short title (2-5 words) that describes this chunk's main topic
4. List any important entities (names, numbers, terms) mentioned

Respond in JSON format:
{{
    "summary": "3-5 sentence summary of this chunk",
    "key_points": ["Specific point 1", "Specific point 2", "..."],
    "suggested_title": "Short descriptive title",
    "entities": ["Entity 1", "Entity 2", "..."]
}}

Critical requirements:
- Focus on UNIQUE details - avoid generic statements
- Include specific numbers, names, or examples if mentioned
- The summary should stand alone but also work as part of a larger document
- Output ONLY valid JSON"""

REFINE_ASSEMBLY_PROMPT = """You are assembling a video summary by integrating new content with an existing summary.

CURRENT RUNNING SUMMARY:
{running_summary}

KEY POINTS ALREADY COVERED:
{covered_points}

NEW CHUNK TO INTEGRATE (chunk {chunk_index} of {total_chunks}):
{new_chunk_summary}

Your task:
1. Read the new chunk summary
2. Identify what is GENUINELY NEW vs what was already covered
3. Add only the NEW information to the running summary
4. Update the key points list with any NEW unique points

IMPORTANT - Avoid redundancy:
- If a topic was already covered, only add NEW details about it
- Do NOT repeat the same facts, examples, or statistics
- Each section of the summary should contribute UNIQUE value

Respond in JSON format:
{{
    "updated_summary": "The running summary with new information integrated (should grow by 1-2 sentences max)",
    "new_points_added": ["Only genuinely NEW points from this chunk"],
    "topics_updated": ["Topics that received new details (not full repetition)"]
}}

Output ONLY valid JSON."""

SECTION_TITLE_PROMPT = """Given these chunk summaries from a video, group them into logical sections and generate appropriate titles.

CHUNK SUMMARIES:
{chunk_summaries_json}

Your task:
1. Identify natural topic boundaries where the content shifts
2. Group consecutive chunks that discuss the same topic
3. Generate a clear, descriptive title for each section (2-5 words)
4. Estimate timestamps based on chunk positions

Respond in JSON format:
{{
    "sections": [
        {{
            "title": "Section Title",
            "chunk_indices": [0, 1, 2],
            "start_time": "0:00",
            "end_time": "10:00",
            "combined_summary": "Combined summary of all chunks in this section"
        }}
    ]
}}

Guidelines:
- Aim for 4-8 sections total (merge small topics, split large ones)
- Titles should be specific to the content, not generic
- Each section should represent a coherent topic or theme
- Output ONLY valid JSON"""

FINAL_EXECUTIVE_PROMPT = """Create a final executive summary from these section summaries.

VIDEO TITLE: {video_title}

SECTION SUMMARIES:
{section_summaries}

Create:
1. A comprehensive executive summary (4-6 sentences) that captures the entire video
2. 5-8 unique key takeaways (each must be distinct - no overlapping points)
3. Target audience description

CRITICAL - Consolidation rules:
- If the same topic appears in multiple sections, mention it ONCE in the executive summary
- Key takeaways must be MUTUALLY EXCLUSIVE - no two should cover the same idea
- Prioritize unique insights over frequently repeated points

Respond in JSON format:
{{
    "executive_summary": "4-6 sentence comprehensive overview",
    "key_takeaways": ["Unique takeaway 1", "Unique takeaway 2", "..."],
    "target_audience": "Who should watch this and why"
}}

Output ONLY valid JSON."""


class SummarizationService:
    """Service for generating structured video summaries"""

    def __init__(self):
        """Initialize the summarization service"""
        self.settings = get_settings()
        self.client: Optional[AsyncOpenAI] = None
        self.openrouter_client: Optional[AsyncOpenAI] = None

        # Initialize OpenAI client
        if self.settings.openai_api_key:
            self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            logger.info(f"Summarization service initialized with model: {self.settings.llm_model}")
        else:
            logger.warning("OpenAI API key not configured - summarization will not work")

        # Initialize OpenRouter client for large context models
        if self.settings.openrouter_api_key:
            self.openrouter_client = AsyncOpenAI(
                api_key=self.settings.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            logger.info(f"OpenRouter initialized with model: {self.settings.openrouter_default_model}")

    def is_available(self) -> bool:
        """Check if summarization service is available"""
        return self.client is not None

    def is_openrouter_available(self) -> bool:
        """Check if OpenRouter is available for large context models"""
        return self.openrouter_client is not None

    async def _call_openrouter(
        self,
        prompt: str,
        temperature: float = 0.3,
        model_override: Optional[str] = None,
        max_tokens: int = 8000
    ) -> Dict[str, Any]:
        """Make an LLM call via OpenRouter and parse JSON response

        Args:
            prompt: The prompt to send
            temperature: Sampling temperature
            model_override: Optional model to use instead of default
            max_tokens: Maximum tokens for response (default 8000 for detailed summaries)
        """
        if not self.openrouter_client:
            return {"error": "OpenRouter not configured"}

        model = model_override or self.settings.openrouter_default_model

        try:
            logger.info(f"Calling OpenRouter with model: {model}")
            response = await self.openrouter_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                extra_headers={
                    "HTTP-Referer": "https://tubevibe.app",
                    "X-Title": "TubeVibe Library"
                }
            )

            content = response.choices[0].message.content

            # Log token usage for cost tracking
            if hasattr(response, 'usage') and response.usage:
                logger.info(f"OpenRouter usage - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")

            # Debug: log raw content if parsing fails
            if not content:
                logger.error("OpenRouter returned empty content")
                return {"error": "OpenRouter returned empty response"}

            # Strip markdown code blocks if present (Gemini often wraps JSON in ```json ... ```)
            content = content.strip()
            if content.startswith("```"):
                # Find the end of the first line (```json or ```)
                first_newline = content.find("\n")
                if first_newline > 0:
                    content = content[first_newline + 1:]
                # Remove trailing ```
                if content.endswith("```"):
                    content = content[:-3].strip()

            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error from OpenRouter: {e}")
            logger.error(f"Raw response content: {content[:500] if content else 'None'}...")
            return {"error": f"Failed to parse OpenRouter response: {e}"}
        except Exception as e:
            logger.error(f"OpenRouter call error: {e}")
            return {"error": str(e)}

    async def _call_llm(
        self,
        prompt: str,
        temperature: float = 0.3,
        model_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make an LLM call and parse JSON response

        Args:
            prompt: The prompt to send
            temperature: Sampling temperature
            model_override: Optional model to use instead of default (e.g., 'gpt-4o' for complex tasks)
        """
        if not self.client:
            return {"error": "LLM not configured"}

        model = model_override or self.settings.llm_model

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=self.settings.llm_max_tokens,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {"error": f"Failed to parse LLM response: {e}"}
        except Exception as e:
            logger.error(f"LLM call error: {e}")
            return {"error": str(e)}

    def _extract_section_content(self, transcript: str, start_time: str, end_time: str) -> str:
        """Extract content between timestamps from transcript"""
        # Try to find content between timestamps
        # This handles various timestamp formats: [0:00], 0:00, (0:00)

        def time_to_seconds(time_str: str) -> int:
            """Convert MM:SS or HH:MM:SS to seconds"""
            parts = time_str.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return 0

        start_seconds = time_to_seconds(start_time)
        end_seconds = time_to_seconds(end_time)

        # Find timestamp patterns in transcript
        timestamp_pattern = r'\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?'
        matches = list(re.finditer(timestamp_pattern, transcript))

        if not matches:
            # No timestamps found - estimate based on position
            total_length = len(transcript)
            # Assuming transcript corresponds linearly to video duration
            # This is a rough approximation
            start_pos = int(total_length * (start_seconds / max(end_seconds, 1)))
            end_pos = int(total_length * (end_seconds / max(end_seconds, 1)))
            return transcript[start_pos:end_pos] if end_pos > start_pos else transcript

        # Find content between timestamp ranges
        content_start = 0
        content_end = len(transcript)

        for i, match in enumerate(matches):
            match_time = time_to_seconds(match.group(1))
            if match_time >= start_seconds and content_start == 0:
                content_start = match.start()
            if match_time >= end_seconds:
                content_end = match.start()
                break

        return transcript[content_start:content_end].strip()

    async def detect_topics(self, transcript: str) -> Dict[str, Any]:
        """Detect topic sections in transcript"""
        # Truncate transcript if too long (keep first ~16000 chars for topic detection)
        # Increased from 8000 to capture more context for better section identification
        truncated = transcript[:16000] if len(transcript) > 16000 else transcript

        prompt = TOPIC_DETECTION_PROMPT.format(transcript=truncated)
        result = await self._call_llm(prompt, temperature=0.2)

        if "error" in result:
            # Fallback: create single section
            return {
                "sections": [{
                    "title": "Full Video",
                    "start_time": "0:00",
                    "end_time": "99:99",
                    "description": "Complete video content"
                }]
            }

        return result

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
        # Truncate section if too long (increased from 4000 to 8000 for richer summaries)
        # This allows more context per section while staying within model limits
        truncated = section_content[:8000] if len(section_content) > 8000 else section_content

        # Build context from previous sections with base facts tracking
        previous_context = ""
        if previous_summaries:
            context_parts = ["BASE FACTS ALREADY COVERED (extract only NEW details about these):"]
            all_entities = set()
            for ps in previous_summaries:
                title = ps.get('title', 'Previous Section')
                key_points = ps.get('key_points', [])
                entities = ps.get('entities', [])
                all_entities.update(entities)
                if key_points:
                    points_str = "; ".join(key_points[:3])  # Top 3 points
                    context_parts.append(f"- {title}: {points_str}")

            # Add entities as explicit base facts
            if all_entities:
                context_parts.append(f"\nKEY ENTITIES ALREADY INTRODUCED: {', '.join(list(all_entities)[:10])}")
                context_parts.append("If these appear again, only include NEW information about them.")

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

    async def generate_executive_summary(
        self,
        video_title: str,
        section_summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate executive summary from section summaries"""
        summaries_text = "\n\n".join([
            f"**{s.get('title', 'Section')}** ({s.get('timestamp', 'N/A')})\n{s.get('summary', '')}"
            for s in section_summaries
        ])

        prompt = EXECUTIVE_SUMMARY_PROMPT.format(
            video_title=video_title,
            section_summaries=summaries_text
        )

        result = await self._call_llm(prompt, temperature=0.3)

        if "error" in result:
            return {
                "executive_summary": f"Summary of {video_title}",
                "key_takeaways": [],
                "target_audience": "General viewers"
            }

        return result

    async def consolidate_summary(self, raw_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process the summary to remove cross-section redundancy.

        This is the final step that catches any repetition that slipped through
        the section-level summarization.

        Uses gpt-4o for better instruction following on this complex task.
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

            # Use gpt-4o for consolidation - it follows complex delta instructions better
            logger.info("Using gpt-4o for consolidation step...")
            result = await self._call_llm(prompt, temperature=0.2, model_override="gpt-4o")

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
                    "consolidated": True,
                    "consolidation_model": "gpt-4o"
                }
            }

            logger.info("Summary consolidated successfully with gpt-4o")
            return consolidated

        except Exception as e:
            logger.error(f"Error consolidating summary: {e}")
            return raw_summary

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

    # ========================================================================
    # NEW HYBRID ARCHITECTURE METHODS (v2)
    # ========================================================================

    def chunk_transcript(
        self,
        transcript: str,
        chunk_size: int = CHUNK_SIZE_CHARS,
        overlap: int = CHUNK_OVERLAP_CHARS
    ) -> List[Dict[str, Any]]:
        """
        Split transcript into fixed-size chunks with overlap.

        Args:
            transcript: Full video transcript
            chunk_size: Target size of each chunk in characters
            overlap: Number of overlapping characters between chunks

        Returns:
            List of chunk dicts with content, start_pos, end_pos
        """
        chunks = []
        transcript_length = len(transcript)

        if transcript_length <= chunk_size:
            # Short transcript - single chunk
            return [{
                "index": 0,
                "content": transcript,
                "start_pos": 0,
                "end_pos": transcript_length,
                "start_pct": 0.0,
                "end_pct": 1.0
            }]

        pos = 0
        chunk_index = 0

        while pos < transcript_length:
            # Calculate end position
            end_pos = min(pos + chunk_size, transcript_length)

            # Try to break at a sentence boundary (. ! ? followed by space)
            if end_pos < transcript_length:
                # Look for sentence boundary in last 500 chars
                search_start = max(end_pos - 500, pos)
                chunk_text = transcript[search_start:end_pos]

                # Find last sentence boundary
                for boundary in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                    last_boundary = chunk_text.rfind(boundary)
                    if last_boundary > 0:
                        end_pos = search_start + last_boundary + len(boundary)
                        break

            # Extract chunk
            chunk_content = transcript[pos:end_pos].strip()

            if len(chunk_content) >= MIN_CHUNK_SIZE:
                chunks.append({
                    "index": chunk_index,
                    "content": chunk_content,
                    "start_pos": pos,
                    "end_pos": end_pos,
                    "start_pct": pos / transcript_length,
                    "end_pct": end_pos / transcript_length
                })
                chunk_index += 1

            # Move position with overlap
            pos = end_pos - overlap
            if pos >= transcript_length - MIN_CHUNK_SIZE:
                break

        logger.info(f"Chunked transcript into {len(chunks)} chunks (avg {transcript_length // max(len(chunks), 1)} chars each)")
        return chunks

    def _estimate_timestamp(
        self,
        position_pct: float,
        estimated_duration_minutes: int = 60
    ) -> str:
        """
        Estimate timestamp from position percentage.

        Args:
            position_pct: Position as percentage (0.0 to 1.0)
            estimated_duration_minutes: Estimated video duration in minutes

        Returns:
            Timestamp string in MM:SS format
        """
        total_seconds = int(position_pct * estimated_duration_minutes * 60)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    async def summarize_chunk(
        self,
        chunk: Dict[str, Any],
        total_chunks: int
    ) -> Dict[str, Any]:
        """
        Summarize a single chunk (MAP step).

        Args:
            chunk: Chunk dict with content and metadata
            total_chunks: Total number of chunks for context

        Returns:
            Summary dict with summary, key_points, suggested_title, entities
        """
        prompt = CHUNK_SUMMARY_PROMPT.format(
            chunk_index=chunk["index"] + 1,
            total_chunks=total_chunks,
            chunk_content=chunk["content"][:8000]  # Limit content size
        )

        result = await self._call_llm(prompt, temperature=0.3)

        if "error" in result:
            return {
                "summary": f"Chunk {chunk['index'] + 1} summary unavailable.",
                "key_points": [],
                "suggested_title": f"Part {chunk['index'] + 1}",
                "entities": []
            }

        return {
            "index": chunk["index"],
            "summary": result.get("summary", ""),
            "key_points": result.get("key_points", []),
            "suggested_title": result.get("suggested_title", f"Part {chunk['index'] + 1}"),
            "entities": result.get("entities", []),
            "start_pct": chunk["start_pct"],
            "end_pct": chunk["end_pct"]
        }

    async def summarize_chunks_parallel(
        self,
        chunks: List[Dict[str, Any]],
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Summarize all chunks in parallel (MAP step).

        Args:
            chunks: List of chunk dicts
            max_concurrent: Maximum concurrent API calls

        Returns:
            List of chunk summaries
        """
        total_chunks = len(chunks)
        logger.info(f"MAP step: Summarizing {total_chunks} chunks in parallel (max {max_concurrent} concurrent)...")

        # Create semaphore to limit concurrent calls
        semaphore = asyncio.Semaphore(max_concurrent)

        async def summarize_with_semaphore(chunk):
            async with semaphore:
                return await self.summarize_chunk(chunk, total_chunks)

        # Run all summaries in parallel
        tasks = [summarize_with_semaphore(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks)

        # Sort by index to maintain order
        results = sorted(results, key=lambda x: x.get("index", 0))

        logger.info(f"MAP step complete: {len(results)} chunk summaries generated")
        return results

    async def refine_chunk_summaries(
        self,
        chunk_summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sequentially refine chunk summaries into a coherent whole (REFINE step).

        Args:
            chunk_summaries: List of chunk summary dicts from MAP step

        Returns:
            Refined summary with running_summary and all_key_points
        """
        if not chunk_summaries:
            return {"running_summary": "", "all_key_points": []}

        logger.info(f"REFINE step: Assembling {len(chunk_summaries)} chunk summaries sequentially...")

        # Start with first chunk
        running_summary = chunk_summaries[0].get("summary", "")
        all_key_points = chunk_summaries[0].get("key_points", [])[:]

        # Refine with each subsequent chunk
        for i, chunk_summary in enumerate(chunk_summaries[1:], start=2):
            logger.info(f"  Refining with chunk {i}/{len(chunk_summaries)}...")

            prompt = REFINE_ASSEMBLY_PROMPT.format(
                running_summary=running_summary,
                covered_points=json.dumps(all_key_points[:10], indent=2),  # Last 10 points
                chunk_index=i,
                total_chunks=len(chunk_summaries),
                new_chunk_summary=json.dumps({
                    "summary": chunk_summary.get("summary", ""),
                    "key_points": chunk_summary.get("key_points", []),
                    "suggested_title": chunk_summary.get("suggested_title", "")
                }, indent=2)
            )

            result = await self._call_llm(prompt, temperature=0.3)

            if "error" not in result:
                running_summary = result.get("updated_summary", running_summary)
                new_points = result.get("new_points_added", [])
                all_key_points.extend(new_points)

        logger.info(f"REFINE step complete: Summary assembled with {len(all_key_points)} key points")
        return {
            "running_summary": running_summary,
            "all_key_points": all_key_points
        }

    async def group_into_sections(
        self,
        chunk_summaries: List[Dict[str, Any]],
        estimated_duration_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Group chunks into logical sections and generate titles from content.

        Args:
            chunk_summaries: List of chunk summary dicts
            estimated_duration_minutes: Estimated video duration for timestamps

        Returns:
            List of section dicts with titles, timestamps, and summaries
        """
        if not chunk_summaries:
            return []

        logger.info(f"Grouping {len(chunk_summaries)} chunks into sections...")

        # Prepare chunk data for the LLM
        chunk_data = []
        for cs in chunk_summaries:
            chunk_data.append({
                "index": cs.get("index", 0),
                "suggested_title": cs.get("suggested_title", ""),
                "summary": cs.get("summary", ""),
                "key_points": cs.get("key_points", [])[:3],  # Top 3 points
                "start_pct": cs.get("start_pct", 0),
                "end_pct": cs.get("end_pct", 0)
            })

        prompt = SECTION_TITLE_PROMPT.format(
            chunk_summaries_json=json.dumps(chunk_data, indent=2)
        )

        result = await self._call_llm(prompt, temperature=0.3)

        if "error" in result:
            # Fallback: each chunk becomes a section
            logger.warning("Section grouping failed, using fallback")
            sections = []
            for cs in chunk_summaries:
                start_time = self._estimate_timestamp(cs.get("start_pct", 0), estimated_duration_minutes)
                end_time = self._estimate_timestamp(cs.get("end_pct", 0), estimated_duration_minutes)
                sections.append({
                    "title": cs.get("suggested_title", f"Part {cs.get('index', 0) + 1}"),
                    "timestamp": f"{start_time} - {end_time}",
                    "summary": cs.get("summary", ""),
                    "key_points": cs.get("key_points", []),
                    "entities": cs.get("entities", [])
                })
            return sections

        # Process LLM result
        sections = []
        for section_data in result.get("sections", []):
            chunk_indices = section_data.get("chunk_indices", [])

            # Calculate timestamp from chunk positions
            if chunk_indices:
                first_chunk = chunk_summaries[chunk_indices[0]] if chunk_indices[0] < len(chunk_summaries) else {}
                last_chunk = chunk_summaries[chunk_indices[-1]] if chunk_indices[-1] < len(chunk_summaries) else {}
                start_time = self._estimate_timestamp(first_chunk.get("start_pct", 0), estimated_duration_minutes)
                end_time = self._estimate_timestamp(last_chunk.get("end_pct", 0), estimated_duration_minutes)
            else:
                start_time = section_data.get("start_time", "0:00")
                end_time = section_data.get("end_time", "0:00")

            # Collect key points and entities from grouped chunks
            section_key_points = []
            section_entities = []
            for idx in chunk_indices:
                if idx < len(chunk_summaries):
                    section_key_points.extend(chunk_summaries[idx].get("key_points", []))
                    section_entities.extend(chunk_summaries[idx].get("entities", []))

            sections.append({
                "title": section_data.get("title", "Section"),
                "timestamp": f"{start_time} - {end_time}",
                "summary": section_data.get("combined_summary", ""),
                "key_points": section_key_points[:5],  # Limit points per section
                "entities": list(set(section_entities))[:5]
            })

        logger.info(f"Created {len(sections)} sections from {len(chunk_summaries)} chunks")
        return sections

    async def generate_summary_v2(
        self,
        transcript: str,
        video_title: str,
        video_id: Optional[str] = None,
        estimated_duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Generate summary using the new hybrid Map-Reduce + Refine architecture.

        This ensures 100% coverage of the transcript regardless of length.

        Args:
            transcript: Full video transcript
            video_title: Title of the video
            video_id: Optional video ID for reference
            estimated_duration_minutes: Estimated video duration for timestamps

        Returns:
            Structured summary with sections, key points, and executive summary
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Summarization service not available - OpenAI API key not configured"
            }

        try:
            logger.info(f"Generating summary (v2 hybrid) for: {video_title}")
            logger.info(f"Transcript length: {len(transcript)} characters")

            # Step 1: Chunk the transcript
            logger.info("Step 1: Chunking transcript...")
            chunks = self.chunk_transcript(transcript)
            logger.info(f"Created {len(chunks)} chunks")

            # Step 2: MAP - Summarize chunks in parallel
            logger.info("Step 2: MAP - Parallel chunk summarization...")
            chunk_summaries = await self.summarize_chunks_parallel(chunks)

            # Step 3: REFINE - Sequential assembly
            logger.info("Step 3: REFINE - Sequential assembly...")
            refined = await self.refine_chunk_summaries(chunk_summaries)

            # Step 4: Group into sections with generated titles
            logger.info("Step 4: Grouping into sections...")
            sections = await self.group_into_sections(chunk_summaries, estimated_duration_minutes)

            # Step 5: Generate executive summary
            logger.info("Step 5: Generating executive summary...")
            section_text = "\n\n".join([
                f"**{s.get('title', 'Section')}** ({s.get('timestamp', 'N/A')})\n{s.get('summary', '')}"
                for s in sections
            ])

            prompt = FINAL_EXECUTIVE_PROMPT.format(
                video_title=video_title,
                section_summaries=section_text
            )

            executive = await self._call_llm(prompt, temperature=0.3)

            if "error" in executive:
                executive = {
                    "executive_summary": refined.get("running_summary", ""),
                    "key_takeaways": refined.get("all_key_points", [])[:8],
                    "target_audience": "General viewers"
                }

            # Compile result
            result = {
                "success": True,
                "video_id": video_id,
                "video_title": video_title,
                "executive_summary": executive.get("executive_summary", ""),
                "key_takeaways": executive.get("key_takeaways", []),
                "target_audience": executive.get("target_audience", ""),
                "sections": sections,
                "total_sections": len(sections),
                "metadata": {
                    "model": self.settings.llm_model,
                    "method": "hybrid_map_reduce_refine_v2",
                    "transcript_length": len(transcript),
                    "chunks_processed": len(chunks),
                    "coverage": "100%"
                }
            }

            # Step 6: Final consolidation with GPT-4o
            logger.info("Step 6: Final consolidation with GPT-4o...")
            result = await self.consolidate_summary(result)

            logger.info(f"Summary (v2) generated successfully for: {video_title}")
            return result

        except Exception as e:
            logger.error(f"Error generating summary (v2): {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def generate_summary_large_context(
        self,
        transcript: str,
        video_title: str,
        video_id: Optional[str] = None,
        estimated_duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Generate summary using a large context model via OpenRouter.

        This method passes the ENTIRE transcript to a model with a large context window
        (e.g., Gemini 2.0 Flash with 1M tokens) in a single call. This approach:
        - Eliminates chunking complexity
        - Ensures perfect coherence (model sees everything at once)
        - Natural deduplication (model won't repeat itself)
        - Better section discovery (full context available)

        Args:
            transcript: Full video transcript
            video_title: Title of the video
            video_id: Optional video ID for reference
            estimated_duration_minutes: Estimated video duration for timestamp estimation

        Returns:
            Structured summary with sections, key points, and executive summary
        """
        if not self.is_openrouter_available():
            logger.warning("OpenRouter not available, falling back to v2 hybrid")
            return await self.generate_summary_v2(
                transcript=transcript,
                video_title=video_title,
                video_id=video_id,
                estimated_duration_minutes=estimated_duration_minutes
            )

        try:
            logger.info(f"Generating summary (large context) for: {video_title}")
            logger.info(f"Transcript length: {len(transcript)} characters (~{len(transcript) // 4} tokens)")
            logger.info(f"Using model: {self.settings.openrouter_default_model}")

            # Single call with the entire transcript
            prompt = LARGE_CONTEXT_SUMMARY_PROMPT.format(
                video_title=video_title,
                transcript=transcript
            )

            result = await self._call_openrouter(
                prompt=prompt,
                temperature=0.3,
                max_tokens=8000  # Allow detailed output
            )

            if "error" in result:
                logger.warning(f"Large context call failed: {result['error']}, falling back to v2")
                return await self.generate_summary_v2(
                    transcript=transcript,
                    video_title=video_title,
                    video_id=video_id,
                    estimated_duration_minutes=estimated_duration_minutes
                )

            # Format sections with proper structure
            sections = []
            for section in result.get("sections", []):
                sections.append({
                    "title": section.get("title", "Section"),
                    "timestamp": section.get("timestamp", "0:00 - 0:00"),
                    "summary": section.get("summary", ""),
                    "key_points": section.get("key_points", []),
                    "entities": section.get("entities", [])
                })

            # Compile final result
            final_result = {
                "success": True,
                "video_id": video_id,
                "video_title": video_title,
                "executive_summary": result.get("executive_summary", ""),
                "key_takeaways": result.get("key_takeaways", []),
                "target_audience": result.get("target_audience", ""),
                "sections": sections,
                "total_sections": len(sections),
                "metadata": {
                    "model": self.settings.openrouter_default_model,
                    "method": "large_context_single_call",
                    "transcript_length": len(transcript),
                    "estimated_tokens": len(transcript) // 4,
                    "coverage": "100%"
                }
            }

            logger.info(f"Summary (large context) generated successfully for: {video_title}")
            logger.info(f"Generated {len(sections)} sections with {len(result.get('key_takeaways', []))} key takeaways")
            return final_result

        except Exception as e:
            logger.error(f"Error generating summary (large context): {e}")
            # Fallback to v2 hybrid
            logger.info("Falling back to v2 hybrid architecture...")
            return await self.generate_summary_v2(
                transcript=transcript,
                video_title=video_title,
                video_id=video_id,
                estimated_duration_minutes=estimated_duration_minutes
            )

    async def generate_summary(
        self,
        transcript: str,
        video_title: str,
        video_id: Optional[str] = None,
        estimated_duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Generate a complete structured summary.

        Automatically selects the best algorithm based on transcript length and available services:
        - For very large transcripts (>50K chars) with OpenRouter: Uses large context model (Gemini 2.0 Flash)
        - For large transcripts (>50K chars) without OpenRouter: Uses v2 hybrid Map-Reduce + Refine
        - For shorter transcripts: Uses v1 Topic Detection + Chain of Density

        Args:
            transcript: Full video transcript
            video_title: Title of the video
            video_id: Optional video ID for reference
            estimated_duration_minutes: Estimated video duration (used for timestamps)

        Returns:
            Structured summary with sections, key points, and executive summary
        """
        if not self.is_available() and not self.is_openrouter_available():
            return {
                "success": False,
                "error": "Summarization service not available - no API keys configured"
            }

        # Thresholds for routing
        LONG_TRANSCRIPT_THRESHOLD = self.settings.openrouter_large_context_threshold  # Default 50000 chars

        # For long transcripts, prefer large context model if available
        if len(transcript) > LONG_TRANSCRIPT_THRESHOLD:
            if self.is_openrouter_available():
                logger.info(f"Long transcript detected ({len(transcript)} chars), using large context model via OpenRouter")
                return await self.generate_summary_large_context(
                    transcript=transcript,
                    video_title=video_title,
                    video_id=video_id,
                    estimated_duration_minutes=estimated_duration_minutes
                )
            elif self.is_available():
                logger.info(f"Long transcript detected ({len(transcript)} chars), using v2 hybrid architecture (OpenRouter not available)")
                return await self.generate_summary_v2(
                    transcript=transcript,
                    video_title=video_title,
                    video_id=video_id,
                    estimated_duration_minutes=estimated_duration_minutes
                )

        # Check if OpenAI is available for shorter transcripts
        if not self.is_available():
            # Fall back to OpenRouter even for short transcripts if OpenAI unavailable
            if self.is_openrouter_available():
                logger.info("OpenAI not available, using OpenRouter for short transcript")
                return await self.generate_summary_large_context(
                    transcript=transcript,
                    video_title=video_title,
                    video_id=video_id,
                    estimated_duration_minutes=estimated_duration_minutes
                )
            return {
                "success": False,
                "error": "Summarization service not available - OpenAI API key not configured"
            }

        try:
            logger.info(f"Generating summary (v1) for: {video_title}")

            # Step 1: Detect topic sections
            logger.info("Step 1: Detecting topic sections...")
            topics = await self.detect_topics(transcript)
            sections = topics.get("sections", [])

            if not sections:
                sections = [{
                    "title": "Full Video",
                    "start_time": "0:00",
                    "end_time": "99:99",
                    "description": "Complete video content"
                }]

            logger.info(f"Detected {len(sections)} sections")

            # Step 2: Summarize each section with Chain of Density
            logger.info("Step 2: Applying Chain of Density to each section...")
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
                    # Divide transcript roughly among sections
                    chunk_size = len(transcript) // len(sections)
                    start = i * chunk_size
                    end = (i + 1) * chunk_size
                    section_content = transcript[start:end]

                # Apply Chain of Density with context from previous sections
                section_summary = await self.summarize_section(
                    section.get("title", f"Section {i+1}"),
                    section_content,
                    previous_summaries=section_summaries if i > 0 else None
                )

                section_summaries.append({
                    "title": section.get("title", f"Section {i+1}"),
                    "timestamp": f"{section.get('start_time', '0:00')} - {section.get('end_time', '')}",
                    "description": section.get("description", ""),
                    "summary": section_summary.get("summary", ""),
                    "key_points": section_summary.get("key_points", []),
                    "entities": section_summary.get("entities", [])
                })

            # Step 3: Generate executive summary
            logger.info("Step 3: Generating executive summary...")
            executive = await self.generate_executive_summary(video_title, section_summaries)

            # Compile all key points
            all_key_points = []
            for s in section_summaries:
                all_key_points.extend(s.get("key_points", []))

            # Apply MMR-based deduplication to key points
            if len(all_key_points) > 8:
                logger.info(f"Deduplicating {len(all_key_points)} key points...")
                all_key_points = await self.deduplicate_key_points(all_key_points)
                logger.info(f"Reduced to {len(all_key_points)} unique points")

            # Compile final result
            result = {
                "success": True,
                "video_id": video_id,
                "video_title": video_title,
                "executive_summary": executive.get("executive_summary", ""),
                "key_takeaways": executive.get("key_takeaways", []),
                "target_audience": executive.get("target_audience", ""),
                "sections": section_summaries,
                "total_sections": len(section_summaries),
                "metadata": {
                    "model": self.settings.llm_model,
                    "method": "topic_detection_chain_of_density",
                    "transcript_length": len(transcript)
                }
            }

            # Apply post-processing consolidation to remove cross-section redundancy
            logger.info("Step 4: Consolidating summary to remove redundancy...")
            result = await self.consolidate_summary(result)

            logger.info(f"Summary generated successfully for: {video_title}")
            return result

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def generate_podcast_summary(
        self,
        transcript: str,
        podcast_title: str,
        podcast_id: Optional[str] = None,
        podcast_subject: Optional[str] = None,
        podcast_date: Optional[str] = None,
        participants: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a structured summary optimized for podcast/meeting transcripts.

        Extracts:
        - Executive summary
        - Key takeaways
        - Action items
        - Decisions made
        - Topics discussed

        Args:
            transcript: Full podcast transcript
            podcast_title: Title of the podcast/meeting
            podcast_id: Optional podcast ID for reference
            podcast_subject: Optional subject/topic
            podcast_date: Optional date of the podcast
            participants: Optional list of participants

        Returns:
            Structured summary with meeting-specific sections
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Summarization service not available - OpenAI API key not configured"
            }

        try:
            logger.info(f"Generating podcast summary for: {podcast_title}")

            # Prepare context for the summary
            context_parts = [f"Title: {podcast_title}"]
            if podcast_subject:
                context_parts.append(f"Subject: {podcast_subject}")
            if podcast_date:
                context_parts.append(f"Date: {podcast_date}")
            if participants:
                context_parts.append(f"Participants: {', '.join(participants)}")
            context = "\n".join(context_parts)

            # Generate structured summary using a single LLM call
            prompt = f"""You are an expert meeting summarizer. Analyze the following podcast/meeting transcript and provide a comprehensive summary.

Meeting Context:
{context}

Transcript:
{transcript[:15000]}  # Limit to avoid token limits

Please provide the following in JSON format:
{{
    "executive_summary": "A 2-3 sentence overview of what was discussed",
    "key_takeaways": ["List of 3-5 most important points discussed"],
    "action_items": ["List of specific tasks or follow-ups mentioned"],
    "decisions_made": ["List of any decisions that were reached"],
    "topics_discussed": ["List of main topics/themes covered"]
}}

Return ONLY valid JSON, no additional text."""

            response = await self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional meeting summarizer. Always respond with valid JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            # Parse response
            response_text = response.choices[0].message.content.strip()

            # Try to extract JSON from response
            import json
            try:
                # Handle potential markdown code blocks
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    json_lines = []
                    in_json = False
                    for line in lines:
                        if line.startswith("```json"):
                            in_json = True
                            continue
                        elif line.startswith("```"):
                            in_json = False
                            continue
                        if in_json:
                            json_lines.append(line)
                    response_text = "\n".join(json_lines)

                summary_data = json.loads(response_text)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON from LLM response: {response_text[:200]}")
                # Fallback to basic summary
                summary_data = {
                    "executive_summary": f"Summary of {podcast_title}",
                    "key_takeaways": [],
                    "action_items": [],
                    "decisions_made": [],
                    "topics_discussed": []
                }

            # Compile final result
            result = {
                "success": True,
                "podcast_id": podcast_id,
                "podcast_title": podcast_title,
                "podcast_subject": podcast_subject,
                "podcast_date": podcast_date,
                "participants": participants or [],
                "executive_summary": summary_data.get("executive_summary", ""),
                "key_takeaways": summary_data.get("key_takeaways", []),
                "action_items": summary_data.get("action_items", []),
                "decisions_made": summary_data.get("decisions_made", []),
                "topics_discussed": summary_data.get("topics_discussed", []),
                "metadata": {
                    "model": self.settings.llm_model,
                    "method": "podcast_summary",
                    "transcript_length": len(transcript)
                }
            }

            logger.info(f"Podcast summary generated successfully for: {podcast_title}")
            return result

        except Exception as e:
            logger.error(f"Error generating podcast summary: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance
_summarization_service: Optional[SummarizationService] = None


def get_summarization_service() -> SummarizationService:
    """Get or create summarization service singleton"""
    global _summarization_service
    if _summarization_service is None:
        _summarization_service = SummarizationService()
    return _summarization_service
