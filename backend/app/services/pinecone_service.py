"""
Pinecone Assistant Service

Handles all interactions with Pinecone Assistant API for:
- Uploading video transcripts
- Searching knowledge base (RAG)
- Getting context for summary generation
- Managing files
"""
import os
import logging
from typing import Dict, Any, List, Optional
from io import BytesIO
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(env_path)

logger = logging.getLogger(__name__)


class PineconeService:
    """Service for Pinecone Assistant operations"""

    def __init__(self):
        """Initialize Pinecone service"""
        self.api_key = os.getenv("PINECONE_API_KEY")
        self.assistant_name = os.getenv("PINECONE_ASSISTANT_NAME", "tubevibe-library")
        self.initialized = False
        self.pc = None
        self.assistant = None

        self._initialize_client()

    def _initialize_client(self):
        """Initialize Pinecone client and assistant"""
        if not self.api_key:
            logger.warning("PINECONE_API_KEY not set - Pinecone service disabled")
            return

        try:
            from pinecone import Pinecone

            self.pc = Pinecone(api_key=self.api_key)
            # In SDK v7+, assistant is built-in
            self.assistant = self.pc.assistant.Assistant(
                assistant_name=self.assistant_name
            )
            self.initialized = True
            logger.info(f"Pinecone service initialized with assistant: {self.assistant_name}")

        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}")
            self.initialized = False

    async def upload_transcript(
        self,
        user_id: str,
        video_id: str,
        title: str,
        transcript: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload a video transcript to Pinecone Assistant.

        The transcript is converted to markdown format and uploaded as a file.
        Pinecone handles chunking, embedding, and indexing automatically.

        Args:
            user_id: User's unique ID (for namespace isolation)
            video_id: YouTube video ID
            title: Video title
            transcript: Full transcript text
            metadata: Additional metadata (group_id, channel_name, etc.)

        Returns:
            Dict with success status and file_id if successful
        """
        if not self.initialized:
            return {"success": False, "error": "Pinecone service not initialized"}

        try:
            # Create markdown content with metadata header
            content = f"# {title}\n\n"
            content += f"**Video ID:** {video_id}\n"
            if metadata:
                if metadata.get("channel_name"):
                    content += f"**Channel:** {metadata['channel_name']}\n"
                if metadata.get("duration_seconds"):
                    duration_mins = metadata['duration_seconds'] // 60
                    content += f"**Duration:** {duration_mins} minutes\n"
            content += "\n---\n\n"
            content += "## Transcript\n\n"
            content += transcript

            # Convert to bytes stream
            stream = BytesIO(content.encode("utf-8"))

            # Prepare metadata for Pinecone filtering
            file_metadata = {
                "user_id": user_id,
                "video_id": video_id,
                "title": title
            }

            # Add optional metadata
            if metadata:
                if metadata.get("group_id"):
                    file_metadata["group_id"] = metadata["group_id"]
                if metadata.get("channel_name"):
                    file_metadata["channel_name"] = metadata["channel_name"]

            # Upload to Pinecone Assistant
            response = self.assistant.upload_bytes_stream(
                stream=stream,
                file_name=f"{video_id}.md",
                metadata=file_metadata
            )

            logger.info(f"Uploaded transcript for video {video_id}, file_id: {response.id}")

            return {
                "success": True,
                "file_id": response.id,
                "status": response.status
            }

        except Exception as e:
            logger.error(f"Error uploading transcript to Pinecone: {e}")
            return {"success": False, "error": str(e)}

    async def search_knowledge(
        self,
        user_id: str,
        query: str,
        group_id: Optional[str] = None,
        video_id: Optional[str] = None,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Search user's video knowledge base using RAG.

        Args:
            user_id: User's unique ID
            query: Natural language question
            group_id: Optional group to search within
            video_id: Optional specific video to search within
            chat_history: Optional conversation history for context

        Returns:
            Dict with answer and citations
        """
        if not self.initialized:
            return {"success": False, "error": "Pinecone service not initialized"}

        try:
            from pinecone_plugins.assistant.models.chat import Message

            # Build metadata filter for user isolation using Pinecone's operator syntax
            # Pinecone Assistant requires $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin operators
            filter_dict = {"user_id": {"$eq": user_id}}

            # Add group filter if specified
            if group_id:
                filter_dict["group_id"] = {"$eq": group_id}

            # Add video filter if specified (overrides group filter for specificity)
            if video_id:
                filter_dict["video_id"] = {"$eq": video_id}

            logger.info(f"RAG search - user_id: {user_id}, video_id: {video_id}, group_id: {group_id}")
            logger.info(f"RAG search - full filter: {filter_dict}")
            logger.info(f"RAG search - query: {query[:100]}...")

            # Build message list
            messages = []

            # Add chat history if provided (filter out empty messages)
            if chat_history:
                for msg in chat_history[-5:]:  # Keep last 5 messages for context
                    content = msg.get("content", "").strip()
                    if content:  # Only add non-empty messages
                        messages.append(Message(
                            role=msg.get("role", "user"),
                            content=content
                        ))

            # Add current query
            messages.append(Message(role="user", content=query))

            # Chat with assistant
            logger.info(f"RAG search - calling assistant.chat with {len(messages)} messages")
            response = self.assistant.chat(
                messages=messages,
                filter=filter_dict
            )
            logger.info(f"RAG search - response received, citations: {len(response.citations) if hasattr(response, 'citations') and response.citations else 0}")

            # Extract citations if available
            citations = []
            if hasattr(response, 'citations') and response.citations:
                for citation in response.citations:
                    citations.append({
                        "file_id": citation.file_id if hasattr(citation, 'file_id') else None,
                        "text": citation.text if hasattr(citation, 'text') else None,
                        "metadata": citation.metadata if hasattr(citation, 'metadata') else {}
                    })

            return {
                "success": True,
                "answer": response.message.content,
                "citations": citations
            }

        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return {"success": False, "error": str(e)}

    async def get_context_for_summary(
        self,
        user_id: str,
        video_id: str
    ) -> Dict[str, Any]:
        """
        Get context snippets for generating a video summary.

        Uses Pinecone's Context API to retrieve relevant chunks
        that can be used with any LLM for summary generation.

        Args:
            user_id: User's unique ID
            video_id: YouTube video ID

        Returns:
            Dict with context snippets and references
        """
        if not self.initialized:
            return {"success": False, "error": "Pinecone service not initialized"}

        try:
            # Filter for specific video using Pinecone's operator syntax
            filter_dict = {
                "user_id": {"$eq": user_id},
                "video_id": {"$eq": video_id}
            }

            # Use context API
            response = self.assistant.context(
                query="Provide a comprehensive summary of the main topics, key points, and important insights from this video",
                filter=filter_dict
            )

            # Extract snippets
            snippets = []
            if hasattr(response, 'snippets'):
                for snippet in response.snippets:
                    snippets.append({
                        "text": snippet.text if hasattr(snippet, 'text') else str(snippet),
                        "score": snippet.score if hasattr(snippet, 'score') else None
                    })

            return {
                "success": True,
                "snippets": snippets,
                "total_snippets": len(snippets)
            }

        except Exception as e:
            logger.error(f"Error getting context for summary: {e}")
            return {"success": False, "error": str(e)}

    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """
        Delete a file from Pinecone Assistant.

        Args:
            file_id: Pinecone file ID

        Returns:
            Dict with success status
        """
        if not self.initialized:
            return {"success": False, "error": "Pinecone service not initialized"}

        try:
            self.assistant.delete_file(file_id=file_id)
            logger.info(f"Deleted file {file_id} from Pinecone")
            return {"success": True}

        except Exception as e:
            logger.error(f"Error deleting file from Pinecone: {e}")
            return {"success": False, "error": str(e)}

    async def list_user_files(
        self,
        user_id: str,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all files for a user.

        Args:
            user_id: User's unique ID
            group_id: Optional group filter

        Returns:
            Dict with list of files
        """
        if not self.initialized:
            return {"success": False, "error": "Pinecone service not initialized"}

        try:
            # Note: Pinecone Assistant list_files might not support filtering
            # List all files and filter client-side
            files = self.assistant.list_files()
            logger.info(f"Pinecone list_files returned {len(files) if files else 0} total files")

            file_list = []
            for f in files:
                metadata = f.metadata if hasattr(f, 'metadata') else {}
                file_user_id = metadata.get("user_id") if isinstance(metadata, dict) else None

                # Log each file for debugging
                logger.debug(f"File: {f.name}, user_id: {file_user_id}, metadata: {metadata}")

                # Filter by user_id client-side
                if file_user_id == user_id:
                    file_list.append({
                        "id": f.id,
                        "name": f.name,
                        "status": f.status,
                        "metadata": metadata
                    })

            logger.info(f"Found {len(file_list)} files for user {user_id}")

            return {
                "success": True,
                "files": file_list,
                "total": len(file_list)
            }

        except Exception as e:
            logger.error(f"Error listing files from Pinecone: {e}")
            return {"success": False, "error": str(e)}

    def is_initialized(self) -> bool:
        """Check if Pinecone service is initialized"""
        return self.initialized


# Singleton instance
_pinecone_service: Optional[PineconeService] = None


def get_pinecone_service() -> PineconeService:
    """Get or create Pinecone service singleton"""
    global _pinecone_service
    if _pinecone_service is None:
        _pinecone_service = PineconeService()
    return _pinecone_service
