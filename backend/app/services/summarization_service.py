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

EXECUTIVE_SUMMARY_PROMPT = """Based on these section summaries, create a comprehensive executive summary of the entire video.

VIDEO TITLE: {video_title}

SECTION SUMMARIES:
{section_summaries}

Create:
1. A thorough executive summary (4-6 sentences capturing the main narrative, key arguments, and conclusions)
2. 5-8 key takeaways from the entire video (actionable insights and important learnings)
3. Who would benefit from this video (target audience with specific characteristics)

Respond in JSON format:
{{
    "executive_summary": "4-6 sentence comprehensive overview covering the main narrative, arguments, and conclusions",
    "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3", "Takeaway 4", "Takeaway 5"],
    "target_audience": "Detailed description of who should watch this and why they would benefit"
}}

Critical requirements:
- The executive summary should synthesize information from ALL sections coherently
- Key takeaways must be specific, actionable, and directly derived from the content
- ONLY include information that appears in the section summaries - no external knowledge or speculation
- If the video mentions specific methods, frameworks, or recommendations, include them
- Do NOT generalize beyond what is explicitly stated in the summaries
- Output ONLY valid JSON"""


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

    async def summarize_section(self, section_title: str, section_content: str) -> Dict[str, Any]:
        """Apply Chain of Density summarization to a section"""
        # Truncate section if too long (increased from 4000 to 8000 for richer summaries)
        # This allows more context per section while staying within model limits
        truncated = section_content[:8000] if len(section_content) > 8000 else section_content

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
