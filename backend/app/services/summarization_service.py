"""
Summarization Service

Implements a hybrid approach for high-quality video transcript summarization:
1. Topic Detection - Identifies distinct sections/topics in the transcript
2. Chain of Density (CoD) - Iteratively refines summaries for information density

This approach minimizes hallucinations while preserving key details.
"""
import logging
import json
import re
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI

from app.settings import get_settings

logger = logging.getLogger(__name__)

# ============================================================================
# PROMPTS
# ============================================================================

TOPIC_DETECTION_PROMPT = """Analyze this video transcript and identify distinct topic sections.

For each section, provide:
1. A clear title (2-5 words)
2. The approximate timestamp range (start-end in MM:SS format)
3. A brief description of what's covered (1 sentence)

TRANSCRIPT:
{transcript}

Respond in JSON format:
{{
    "sections": [
        {{
            "title": "Section Title",
            "start_time": "0:00",
            "end_time": "2:30",
            "description": "Brief description of this section"
        }}
    ]
}}

Important:
- Identify 3-7 distinct sections based on topic changes
- If timestamps are in the transcript, use them; otherwise estimate based on content
- Keep section titles concise and descriptive
- Output ONLY valid JSON, no additional text"""

CHAIN_OF_DENSITY_PROMPT = """You are an expert summarizer. Generate a summary of the following section using Chain of Density technique.

SECTION TITLE: {section_title}
SECTION CONTENT:
{section_content}

Your task:
1. First, write an initial summary (3-4 sentences) covering the main points
2. Then, identify 2-3 key entities/facts that are missing from your summary
3. Rewrite the summary to include these entities while keeping the same length
4. Repeat step 2-3 one more time (total 3 iterations)

After 3 iterations, provide your final dense summary.

Respond in JSON format:
{{
    "summary": "Your final dense summary (3-4 sentences, information-rich)",
    "key_points": ["Key point 1", "Key point 2", "Key point 3"],
    "entities": ["Important entity/term 1", "Important entity/term 2"]
}}

Important:
- The final summary should be information-dense but readable
- Key points should be actionable or memorable takeaways
- Entities are important names, terms, numbers, or concepts mentioned
- Output ONLY valid JSON"""

EXECUTIVE_SUMMARY_PROMPT = """Based on these section summaries, create an executive summary of the entire video.

VIDEO TITLE: {video_title}

SECTION SUMMARIES:
{section_summaries}

Create:
1. An executive summary (2-3 sentences capturing the essence)
2. 3-5 key takeaways from the entire video
3. Who would benefit from this video (target audience)

Respond in JSON format:
{{
    "executive_summary": "2-3 sentence overview of the entire video",
    "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
    "target_audience": "Brief description of who should watch this"
}}

Output ONLY valid JSON"""


class SummarizationService:
    """Service for generating structured video summaries"""

    def __init__(self):
        """Initialize the summarization service"""
        self.settings = get_settings()
        self.client: Optional[AsyncOpenAI] = None

        if self.settings.openai_api_key:
            self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            logger.info(f"Summarization service initialized with model: {self.settings.llm_model}")
        else:
            logger.warning("OpenAI API key not configured - summarization will not work")

    def is_available(self) -> bool:
        """Check if summarization service is available"""
        return self.client is not None

    async def _call_llm(self, prompt: str, temperature: float = 0.3) -> Dict[str, Any]:
        """Make an LLM call and parse JSON response"""
        if not self.client:
            return {"error": "LLM not configured"}

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.llm_model,
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
        # Truncate transcript if too long (keep first ~8000 chars for topic detection)
        truncated = transcript[:8000] if len(transcript) > 8000 else transcript

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

    async def summarize_section(self, section_title: str, section_content: str) -> Dict[str, Any]:
        """Apply Chain of Density summarization to a section"""
        # Truncate section if too long
        truncated = section_content[:4000] if len(section_content) > 4000 else section_content

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

    async def generate_summary(
        self,
        transcript: str,
        video_title: str,
        video_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete structured summary using Topic Detection + Chain of Density.

        Args:
            transcript: Full video transcript
            video_title: Title of the video
            video_id: Optional video ID for reference

        Returns:
            Structured summary with sections, key points, and executive summary
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Summarization service not available - OpenAI API key not configured"
            }

        try:
            logger.info(f"Generating summary for: {video_title}")

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

                # Apply Chain of Density summarization
                section_summary = await self.summarize_section(
                    section.get("title", f"Section {i+1}"),
                    section_content
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

            logger.info(f"Summary generated successfully for: {video_title}")
            return result

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
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
