# Summarization Quality Analysis

## Executive Summary

This document analyzes quality issues identified in the multi-step video summarization system, specifically excessive repetition and non-distinct section content. The root causes stem from isolated section processing without cross-section awareness and lack of deduplication logic.

---

## Current Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│  detect_topics  │ ──▶ │  summarize_section  │ ──▶ │ generate_executive   │
│   (1 LLM call)  │     │   (N LLM calls)     │     │     _summary         │
│                 │     │   (isolated)        │     │   (1 LLM call)       │
└─────────────────┘     └─────────────────────┘     └──────────────────────┘
```

**File:** `backend/app/services/summarization_service.py`

---

## Problems Identified

### Problem 1: No Cross-Section Context Passing

**Location:** `summarization_service.py:223-243`

**Current Behavior:**
```python
async def summarize_section(self, section_title: str, section_content: str):
    # Only receives title + content
    # NO context about what other sections already covered
    prompt = CHAIN_OF_DENSITY_PROMPT.format(
        section_title=section_title,
        section_content=section_content
    )
```

**Impact:** Each section is summarized in complete isolation. When the source video repeats key points across segments (common in educational/sales content), each section independently extracts and includes the same information.

**Example:** If "don't exceed 1% of float" is mentioned in 4 different segments, all 4 section summaries will include this point.

---

### Problem 2: No Deduplication of Key Points

**Location:** `summarization_service.py:354-357`

**Current Behavior:**
```python
all_key_points = []
for s in section_summaries:
    all_key_points.extend(s.get("key_points", []))  # Simple concatenation
```

**Impact:** Key points from all sections are concatenated without any deduplication. Semantically identical points appear multiple times in the final output.

---

### Problem 3: Executive Summary Prompt Lacks Consolidation Instructions

**Location:** `summarization_service.py:84-109`

**Current Prompt Excerpt:**
```
- The executive summary should synthesize information from ALL sections coherently
- Key takeaways must be specific, actionable, and directly derived from the content
```

**Missing Instructions:**
- No directive to consolidate duplicate themes
- No instruction to prioritize unique insights over repeated mentions
- No guidance on handling redundant information across sections

---

### Problem 4: Fallback Chunking Creates Arbitrary Boundaries

**Location:** `summarization_service.py:327-333`

**Current Behavior:**
```python
if not section_content or len(section_content) < 100:
    chunk_size = len(transcript) // len(sections)
    start = i * chunk_size
    end = (i + 1) * chunk_size
    section_content = transcript[start:end]
```

**Impact:** When timestamp extraction fails, the transcript is divided into equal chunks regardless of actual topic boundaries. This can:
- Split a single topic across multiple "sections"
- Group unrelated content together
- Create artificial section boundaries where none exist in the source

---

### Problem 5: Topic Detection Truncation

**Location:** `summarization_service.py:203-205`

**Current Behavior:**
```python
truncated = transcript[:16000] if len(transcript) > 16000 else transcript
```

**Impact:** For longer videos, only the first ~10-15 minutes of content is analyzed for topic detection. Later topics may be missed or misidentified, and for repetitive content, the truncated portion may not reveal true topic diversity.

---

### Problem 6: Chain of Density Amplifies Repetition

**Location:** `summarization_service.py:54-82`

The Chain of Density technique iteratively adds "missing entities" to make summaries more information-dense. When source material is repetitive:
- Each section includes the repeated key points (they're in that section's content)
- The "missing entities" identified are often the same across sections
- CoD ensures these repeated points are captured with high fidelity

---

### Problem 7: Source Material Characteristics

Certain video types are inherently repetitive by design:
- **Sales/promotional videos:** Repeat value propositions and CTAs
- **Educational content:** Reinforce key concepts multiple times
- **Course announcements:** Mention pricing/availability throughout

The current system faithfully captures this repetition rather than consolidating it.

---

## Proposed Solutions

### Solution 1: Cross-Section Context Passing (High Impact)

**Approach:** Pass summaries of previous sections to each `summarize_section()` call.

**Implementation:**
```python
async def summarize_section(
    self,
    section_title: str,
    section_content: str,
    previous_summaries: List[Dict[str, Any]] = None  # NEW
) -> Dict[str, Any]:

    context = ""
    if previous_summaries:
        context = "Previously covered points (DO NOT repeat these):\n"
        for ps in previous_summaries:
            context += f"- {ps.get('title')}: {', '.join(ps.get('key_points', []))}\n"

    prompt = CHAIN_OF_DENSITY_PROMPT_WITH_CONTEXT.format(
        section_title=section_title,
        section_content=section_content,
        previous_context=context
    )
```

**Modified Prompt Addition:**
```
IMPORTANT: The following points have already been covered in previous sections.
Focus on NEW information unique to this section. Do not repeat these points:
{previous_context}
```

**Trade-offs:**
- (+) Eliminates cross-section repetition
- (+) Each section focuses on unique content
- (-) Slightly longer prompts
- (-) Sequential processing required (can't parallelize section summaries)

---

### Solution 2: Semantic Deduplication of Key Points (Medium Impact)

**Approach:** Use embeddings or LLM to identify and merge semantically similar key points.

**Implementation Option A - LLM-based:**
```python
async def deduplicate_key_points(self, all_points: List[str]) -> List[str]:
    prompt = f"""Given these key points, consolidate duplicates and near-duplicates
    into a unified list. Merge similar points into single, comprehensive statements.

    Points:
    {json.dumps(all_points, indent=2)}

    Return JSON: {{"deduplicated_points": ["point1", "point2", ...]}}
    """
    result = await self._call_llm(prompt)
    return result.get("deduplicated_points", all_points)
```

**Implementation Option B - Embedding-based:**
```python
async def deduplicate_key_points(self, all_points: List[str]) -> List[str]:
    embeddings = await self.get_embeddings(all_points)
    clusters = cluster_by_similarity(embeddings, threshold=0.85)
    return [pick_best_from_cluster(c) for c in clusters]
```

**Trade-offs:**
- (+) Produces cleaner final output
- (+) Works regardless of source repetition
- (-) Additional LLM call or embedding computation
- (-) Risk of over-consolidating distinct but similar points

---

### Solution 3: Enhanced Executive Summary Prompt (Low Cost)

**Approach:** Add explicit instructions for handling redundancy.

**Modified Prompt:**
```python
EXECUTIVE_SUMMARY_PROMPT = """Based on these section summaries, create a comprehensive executive summary.

VIDEO TITLE: {video_title}

SECTION SUMMARIES:
{section_summaries}

IMPORTANT INSTRUCTIONS:
1. If the same point appears across multiple sections, mention it ONCE in your summary
2. Consolidate repeated themes into single, comprehensive statements
3. Prioritize unique insights over frequently repeated points
4. The video may be promotional/educational with intentional repetition - synthesize, don't echo

Create:
1. A thorough executive summary (4-6 sentences) - CONSOLIDATE repeated themes
2. 5-8 UNIQUE key takeaways - NO duplicate or near-duplicate points
3. Who would benefit from this video

...[rest of prompt]...
"""
```

**Trade-offs:**
- (+) No additional API calls
- (+) Simple to implement
- (-) LLM may not always follow instructions perfectly
- (-) Doesn't fix section-level repetition

---

### Solution 4: Post-Processing Consolidation Step (High Quality)

**Approach:** Add a final LLM call to review and deduplicate the entire summary.

**Implementation:**
```python
async def consolidate_summary(self, raw_summary: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""Review this video summary and consolidate any repetitive content.

    Current Summary:
    {json.dumps(raw_summary, indent=2)}

    Tasks:
    1. Identify points that appear in multiple sections
    2. Keep detailed version in ONE section, reference briefly in others
    3. Merge duplicate key_takeaways into single comprehensive points
    4. Ensure each section adds unique value

    Return the consolidated summary in the same JSON structure.
    """
    return await self._call_llm(prompt)
```

**Trade-offs:**
- (+) Comprehensive deduplication
- (+) Maintains full context for decisions
- (-) Additional LLM call (cost + latency)
- (-) May alter section structure

---

### Solution 5: Repetition Detection & Adaptive Strategy (Advanced)

**Approach:** Detect repetitive source material and switch summarization strategy.

**Implementation:**
```python
async def analyze_content_structure(self, transcript: str) -> str:
    """Detect if content is repetitive/promotional vs. structured/educational"""
    prompt = """Analyze this transcript structure:

    {transcript[:8000]}

    Classify as:
    - "structured": Clear topic progression, minimal repetition
    - "repetitive": Sales pitch, repeated themes, promotional
    - "mixed": Some structure with repeated elements

    Return JSON: {{"type": "structured|repetitive|mixed", "reason": "..."}}
    """
    result = await self._call_llm(prompt)
    return result.get("type", "structured")

async def generate_summary(self, transcript: str, ...):
    content_type = await self.analyze_content_structure(transcript)

    if content_type == "repetitive":
        # Use single-pass summarization for repetitive content
        return await self.generate_single_pass_summary(transcript, ...)
    else:
        # Use multi-step for structured content
        return await self.generate_multi_step_summary(transcript, ...)
```

**Trade-offs:**
- (+) Optimal strategy per content type
- (+) Avoids over-processing simple content
- (-) Additional classification step
- (-) More complex codebase

---

### Solution 6: Improved Section Extraction

**Approach:** Better timestamp parsing and semantic boundary detection.

**Implementation:**
```python
async def detect_topic_boundaries(self, transcript: str) -> List[int]:
    """Use embeddings to find natural topic transitions"""
    sentences = split_into_sentences(transcript)
    embeddings = await self.get_embeddings(sentences)

    # Find points where embedding similarity drops significantly
    boundaries = []
    for i in range(1, len(embeddings)):
        similarity = cosine_similarity(embeddings[i-1], embeddings[i])
        if similarity < 0.7:  # Topic shift threshold
            boundaries.append(i)

    return boundaries
```

**Trade-offs:**
- (+) More accurate section boundaries
- (+) Works without timestamps
- (-) Requires embedding API calls
- (-) More complex implementation

---

## Recommended Implementation Priority

| Priority | Solution | Effort | Impact |
|----------|----------|--------|--------|
| 1 | Solution 3: Enhanced Executive Prompt | Low | Medium |
| 2 | Solution 1: Cross-Section Context | Medium | High |
| 3 | Solution 2: Key Points Deduplication | Medium | Medium |
| 4 | Solution 4: Post-Processing Step | Low | High |
| 5 | Solution 5: Adaptive Strategy | High | High |
| 6 | Solution 6: Semantic Boundaries | High | Medium |

**Recommended Starting Point:** Implement Solutions 1 and 3 together for maximum impact with moderate effort.

---

## Testing Strategy

To validate fixes:

1. **Create test cases with known repetitive content**
   - Sales/promotional videos
   - Course announcements
   - Educational content with reinforced concepts

2. **Metrics to track:**
   - Unique key points ratio: `unique_points / total_points`
   - Cross-section similarity score
   - User satisfaction ratings

3. **A/B testing:**
   - Compare current vs. improved summarization
   - Measure user engagement with summaries

---

## Appendix: Example Problematic Output

**Observed Issues in Sample Summary:**

| Section | Repeated Content |
|---------|-----------------|
| Introduction | "1% of float rule", "8 figures in 2021", "pre-sale" |
| Course Pre-Sale | "1% of float rule", "pre-sale", "volume analysis" |
| Risk Management | "1% of float rule", "8 figures in 2021", "pre-sale" |
| Market Trend | "1% of float rule", "volume analysis" |
| Statistical Tracking | "1% of float rule", "volume analysis" |
| Conclusion | "pre-sale", "course release" |

**Root Cause:** Each section was summarized in isolation, faithfully extracting the repeated points from each segment of a promotional video.

---

---

## Research Validation (External Sources)

Based on external research, our proposed solutions align with established techniques while revealing additional approaches we should consider.

### Validated Approaches

#### 1. Cross-Section Context Passing ✅ Validated

Research on hierarchical summarization confirms that **context-aware processing is critical**:

> "Hierarchical Merging is a technique commonly used to summarize very long texts by breaking down the input into smaller sections, summarizing those sections individually, and then merging. However, the recursive merging process can amplify LLM hallucinations."
> — [Context-Aware Hierarchical Merging for Long Document Summarization](https://arxiv.org/abs/2502.00977)

**Our Solution 1 directly addresses this by passing previous section context.**

#### 2. Information Fusion ✅ Validated

Multi-document summarization research establishes sentence fusion as a core technique:

> "Sentence fusion helps to remove redundancy by fusing sentences into a single abstract sentence. This moves an extractive summary to an abstractive summary."
> — [Multi-document Summarization via Deep Learning](https://arxiv.org/pdf/2011.04843)

**Our Solution 4 (post-processing consolidation) aligns with this approach.**

#### 3. Chain of Density Strengths and Limitations

Research shows CoD already reduces redundancy **within a single iteration**:

> "From the first to second iteration step, the LLM reduces the summary length by removing redundant words. The technique makes space with fusion, compression, and removal of uninformative phrases."
> — [From Sparse to Dense: GPT-4 Summarization with Chain of Density](https://arxiv.org/abs/2309.04269)

**However**, CoD operates on single documents/sections. It doesn't help with cross-section redundancy, confirming our diagnosis.

---

### New Techniques Discovered

#### A. MMR (Maximal Marginal Relevance)

A classic algorithm that balances relevance with novelty:

> "The MMR-MD algorithm addresses anti-redundancy by setting parameters to balance query relevance with redundancy reduction."
> — [Multi-Document Summarization By Sentence Extraction](https://aclanthology.org/W00-0405.pdf)

**Application:** When selecting key points, score each by: `λ * relevance - (1-λ) * similarity_to_already_selected`

#### B. SoftDedup (Reweighting vs. Removing)

Instead of removing duplicates, reweight them:

> "SoftDeDup deduplicates by reweighting samples, where samples with higher commonness are assigned lower sampling weights... achieving comparable results with at least a 26% reduction in required training steps."
> — [SoftDedup: Efficient Data Reweighting](https://arxiv.org/html/2407.06654v1)

**Application:** Instead of removing repeated points, assign lower "importance scores" and let the executive summary prioritize unique content.

#### C. Chain-of-Thought with Hierarchical Segmentation

> "A novel framework integrates hierarchical input segmentation with Chain-of-Thought (CoT) prompting to guide LLMs through structured, interpretable reasoning... On PubMed, hierarchical methods improve ROUGE-2 by +6.13 points."
> — [CoTHSSum: Structured long-document summarization](https://link.springer.com/article/10.1007/s44443-025-00041-2)

**Application:** Add explicit reasoning steps in our prompts about what's new vs. what's been covered.

#### D. Entailment Graph for Redundancy Detection

> "One approach generates an entailment graph where nodes are linked sentences and edges are entailment relations between nodes; such relations help to identify non-redundant and informative sentences."
> — [Neural sentence fusion for abstractive summarization](https://www.sciencedirect.com/science/article/abs/pii/S0885230818303449)

**Application:** Use LLM to check if new key points are "entailed by" (already covered by) previous points.

---

### Refined Solution Priority

Based on research validation:

| Priority | Solution | Research Support | Implementation |
|----------|----------|------------------|----------------|
| **1** | Cross-Section Context (Solution 1) | Strong - hierarchical research | Medium effort |
| **2** | Post-Processing Fusion (Solution 4) | Strong - MDS research | Low effort |
| **3** | MMR-based Key Point Selection | Strong - classic algorithm | Medium effort |
| **4** | Enhanced Prompts (Solution 3) | Moderate | Low effort |
| **5** | SoftDedup Weighting | Novel approach | Medium effort |
| **6** | Entailment Checking | Research-backed | High effort |

---

### Recommended Implementation Strategy

Based on research, implement a **two-phase approach**:

**Phase 1: Quick Wins (Low Effort, High Impact)**
1. Enhanced Executive Summary Prompt (Solution 3)
2. Post-Processing Consolidation Step (Solution 4)

**Phase 2: Architectural Improvements (Medium Effort, Highest Impact)**
1. Cross-Section Context Passing (Solution 1)
2. MMR-based Key Point Selection (new)

**Phase 3: Advanced Optimizations (Optional)**
1. Entailment-based redundancy detection
2. SoftDedup weighting system
3. Semantic boundary detection

---

### Key Research Sources

- [Context-Aware Hierarchical Merging for Long Document Summarization](https://arxiv.org/abs/2502.00977)
- [Systematically Exploring Redundancy Reduction in Summarizing Long Documents](https://arxiv.org/abs/2012.00052)
- [Multi-document Summarization via Deep Learning Techniques](https://arxiv.org/pdf/2011.04843)
- [From Sparse to Dense: GPT-4 Summarization with Chain of Density](https://arxiv.org/abs/2309.04269)
- [CoTHSSum: Structured long-document summarization](https://link.springer.com/article/10.1007/s44443-025-00041-2)
- [SoftDedup: Efficient Data Reweighting for Language Model Pre-training](https://arxiv.org/html/2407.06654v1)
- [Information Fusion in Multi-Document Summarization](https://files01.core.ac.uk/download/pdf/161444057.pdf)

---

*Document created: 2026-01-10*
*Updated with research validation: 2026-01-10*
*Related file: `backend/app/services/summarization_service.py`*
