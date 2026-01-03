"""
Search Routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.pinecone_service import get_pinecone_service
from app.routes.auth import get_current_user_id_optional

router = APIRouter()


class SearchRequest(BaseModel):
    """Search request schema"""
    query: str
    group_id: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request with history"""
    query: str
    group_id: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None


class SummaryRequest(BaseModel):
    """Summary generation request"""
    video_id: str


class SearchResponse(BaseModel):
    """Search response schema"""
    answer: str
    citations: List[Dict[str, Any]] = []


class SummaryResponse(BaseModel):
    """Summary response schema"""
    summary: str
    key_points: List[str] = []
    video_id: str


@router.post("", response_model=SearchResponse)
async def search_knowledge(
    request: SearchRequest,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Search across the user's video knowledge base.

    Uses Pinecone Assistant to find relevant information
    and generate an AI-powered answer with citations.
    """
    pinecone_service = get_pinecone_service()

    result = await pinecone_service.search_knowledge(
        user_id=user_id,
        query=request.query,
        group_id=request.group_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return SearchResponse(
        answer=result["answer"],
        citations=result.get("citations", [])
    )


@router.post("/chat", response_model=SearchResponse)
async def chat_with_knowledge(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Multi-turn chat with the knowledge base.

    Supports conversation history for contextual responses.
    """
    pinecone_service = get_pinecone_service()

    result = await pinecone_service.search_knowledge(
        user_id=user_id,
        query=request.query,
        group_id=request.group_id,
        chat_history=request.history
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return SearchResponse(
        answer=result["answer"],
        citations=result.get("citations", [])
    )


@router.post("/summary", response_model=SummaryResponse)
async def generate_summary(
    request: SummaryRequest,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Generate a summary for a specific video.

    Uses Pinecone's context API to get relevant chunks
    and generates a comprehensive summary.
    """
    pinecone_service = get_pinecone_service()

    # Get context snippets for the video
    context_result = await pinecone_service.get_context_for_summary(
        user_id=user_id,
        video_id=request.video_id
    )

    if not context_result.get("success"):
        raise HTTPException(status_code=400, detail=context_result.get("error"))

    snippets = context_result.get("snippets", [])

    if not snippets:
        raise HTTPException(status_code=404, detail="No content found for this video")

    # Combine snippets into a summary prompt
    combined_context = "\n\n".join([s.get("text", "") for s in snippets])

    # Use Pinecone chat to generate summary
    summary_result = await pinecone_service.search_knowledge(
        user_id=user_id,
        query=f"Based on the following video content, provide a comprehensive summary with key points:\n\n{combined_context[:5000]}"  # Limit context size
    )

    if not summary_result.get("success"):
        raise HTTPException(status_code=400, detail=summary_result.get("error"))

    # Extract key points (simple extraction from the answer)
    answer = summary_result.get("answer", "")
    key_points = []

    # Simple extraction of bullet points
    for line in answer.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*", "•", "1.", "2.", "3.")):
            key_points.append(line.lstrip("-*•0123456789. "))

    return SummaryResponse(
        summary=answer,
        key_points=key_points[:10],  # Limit to 10 key points
        video_id=request.video_id
    )
