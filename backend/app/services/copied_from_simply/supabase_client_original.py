import os
import logging
import json
import time
from datetime import datetime
import traceback
from typing import List, Dict, Any, Optional, Union
import uuid

# Import Supabase libraries
from supabase import create_client, Client

logger = logging.getLogger("bpt-supabase-service")

# Mock storage when Supabase is not available
mock_storage = {
    "transcripts": {},
    "transcript_chunks": [],
    "key_points": {},
    "subscribers": [],
    "trades": []
}

class SupabaseService:
    """Service for interacting with Supabase and pgvector"""
    
    def __init__(self):
        """Initialize Supabase client with environment variables"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        # Check for key in multiple environment variable names
        # Prioritize service role key for backend operations
        self.supabase_key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY") or 
            os.getenv("SUPABASE_KEY") or 
            os.getenv("SUPABASE_ANON_KEY")
        )
        self.client = None
        self.initialized = False
        self.use_mock = (os.getenv("USE_MOCK_SUPABASE", "false").lower() == "true")
        
        # Try to initialize the client
        self._initialize_client()
        
    def _get_key_type(self, key: str) -> str:
        """Determine the type of Supabase key by decoding the JWT payload"""
        try:
            import base64
            import json
            
            # JWT format: header.payload.signature
            parts = key.split('.')
            if len(parts) != 3:
                return "unknown"
                
            # Decode the payload (second part)
            payload = parts[1]
            # Add padding if needed for base64 decoding
            payload += '=' * (4 - len(payload) % 4)
            
            decoded = base64.b64decode(payload)
            payload_data = json.loads(decoded)
            
            # Get the role from the payload
            role = payload_data.get('role', 'unknown')
            return role
            
        except Exception as e:
            logger.warning(f"Could not decode JWT key: {e}")
            return "unknown"
        
    def _initialize_client(self):
        """Initialize the Supabase client"""
        if self.use_mock:
            logger.info("Using mock Supabase service")
            self.initialized = True
            return
        
        try:
            if not self.supabase_url or not self.supabase_key:
                logger.error("Supabase URL or key not provided. Set SUPABASE_URL and one of: SUPABASE_KEY, SUPABASE_ANON_KEY, or SUPABASE_SERVICE_ROLE_KEY environment variables.")
                self.initialized = False
                return
            
            # Create Supabase client
            self.client = create_client(self.supabase_url, self.supabase_key)
            
            # Test connection by running a simple query
            try:
                # Use a simple select query to test connection
                result = self.client.table("transcripts").select("transcript_id").limit(1).execute()
                # Decode JWT to check role
                key_type = self._get_key_type(self.supabase_key)
                logger.info(f"Supabase connection successful. Using key type: {key_type}")
                self.initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {str(e)}")
                if hasattr(e, 'json'):
                    logger.error(f"Error details: {e.json()}")
                self.initialized = False
                self.use_mock = True
                logger.warning("Falling back to mock Supabase mode due to connection error")
        except Exception as e:
            logger.error(f"Error initializing Supabase client: {str(e)}")
            self.initialized = False
            self.use_mock = True
            logger.warning("Falling back to mock Supabase mode due to initialization error")
    
    def check_connection(self) -> Dict[str, Any]:
        """Check if the Supabase connection is working"""
        if self.use_mock:
            return {
                "success": True,
                "is_mock": True,
                "message": "Using mock storage"
            }
            
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Supabase client not initialized"
            }
            
        try:
            result = self.client.table("transcripts").select("transcript_id").limit(1).execute()
            
            if hasattr(result, 'error') and result.error is not None:
                return {
                    "success": False,
                    "error": f"Supabase query error: {result.error}"
                }
                
            key_type = self._get_key_type(self.supabase_key)
            return {
                "success": True,
                "message": f"Supabase connection successful using {key_type} key"
            }
            
        except Exception as e:
            logger.error(f"Error checking Supabase connection: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def store_transcript(self, transcript_id: str, metadata: Dict[str, Any], chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Store transcript metadata and chunks in Supabase"""
        start_time = time.time()
        
        try:
            # If using mock storage
            if self.use_mock:
                # Store in mock data
                mock_storage["transcripts"][transcript_id] = {
                    "transcript_id": transcript_id,
                    "metadata": metadata,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Store chunks
                for chunk in chunks:
                    chunk_id = str(uuid.uuid4())
                    chunk_data = {
                        "id": chunk_id,
                        "transcript_id": transcript_id,
                        "chunk_index": chunk.get("chunk_index", 0),
                        "text": chunk.get("text", ""),
                        "position": chunk.get("position", 0),
                        "is_first": chunk.get("is_first", False),
                        "is_last": chunk.get("is_last", False),
                        "metadata": chunk.get("metadata", {})
                    }
                    mock_storage["transcript_chunks"].append(chunk_data)
                
                logger.info(f"Stored transcript {transcript_id} in mock storage with {len(chunks)} chunks")
                
                end_time = time.time()
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "chunks_stored": len(chunks),
                    "processing_time": end_time - start_time,
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Format transcript data
            transcript_data = {
                "transcript_id": transcript_id,
                "title": metadata.get("title", f"Transcript {transcript_id}"),
                "meeting_id": metadata.get("meeting_id", ""),
                "date": metadata.get("date", datetime.now().isoformat()),
                "word_count": metadata.get("word_count", 0),
                "duration_seconds": metadata.get("duration_seconds", 0),
                "source": metadata.get("source", "fireflies"),
                "metadata": json.dumps(metadata)
            }
            
            # Store transcript metadata
            transcript_result = self.client.table("transcripts").insert(transcript_data).execute()
            
            if hasattr(transcript_result, 'error') and transcript_result.error is not None:
                logger.error(f"Error storing transcript: {transcript_result.error}")
                return {
                    "success": False,
                    "error": f"Error storing transcript: {transcript_result.error}"
                }
                
            # Store chunks
            chunks_data = []
            for chunk in chunks:
                chunk_data = {
                    "transcript_id": transcript_id,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "text": chunk.get("text", ""),
                    "position": chunk.get("position", 0),
                    "is_first": chunk.get("is_first", False),
                    "is_last": chunk.get("is_last", False),
                    "metadata": json.dumps(chunk.get("metadata", {}))
                }
                chunks_data.append(chunk_data)
                
            # Insert chunks in batches to avoid hitting payload limits
            batch_size = 50
            for i in range(0, len(chunks_data), batch_size):
                batch = chunks_data[i:i+batch_size]
                chunks_result = self.client.table("transcript_chunks").insert(batch).execute()
                
                if hasattr(chunks_result, 'error') and chunks_result.error is not None:
                    logger.error(f"Error storing chunks batch {i//batch_size}: {chunks_result.error}")
                    # Continue with next batch despite errors
            
            end_time = time.time()
            logger.info(f"Stored transcript {transcript_id} with {len(chunks)} chunks in {end_time - start_time:.2f}s")
            
            return {
                "success": True,
                "transcript_id": transcript_id,
                "chunks_stored": len(chunks),
                "processing_time": end_time - start_time
            }
                
        except Exception as e:
            logger.error(f"Error storing transcript: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
            
    async def get_transcript_by_id(self, transcript_id: str) -> Dict[str, Any]:
        """Get transcript metadata and chunks by ID"""
        try:
            # If using mock storage
            if self.use_mock:
                if transcript_id not in mock_storage["transcripts"]:
                    return {
                        "success": False,
                        "error": f"Transcript {transcript_id} not found in mock storage"
                    }
                    
                transcript = mock_storage["transcripts"][transcript_id]
                
                # Get chunks for this transcript
                chunks = [
                    chunk for chunk in mock_storage["transcript_chunks"] 
                    if chunk.get("transcript_id") == transcript_id
                ]
                
                # Sort chunks by index
                chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))
                
                return {
                    "success": True,
                    "transcript": transcript,
                    "chunks": chunks,
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Get transcript metadata
            transcript_result = self.client.table("transcripts").select("*").eq("transcript_id", transcript_id).execute()
            
            if hasattr(transcript_result, 'error') and transcript_result.error is not None:
                logger.error(f"Error getting transcript: {transcript_result.error}")
                return {
                    "success": False,
                    "error": f"Error getting transcript: {transcript_result.error}"
                }
                
            # Check if transcript exists
            if not transcript_result.data or len(transcript_result.data) == 0:
                return {
                    "success": False,
                    "error": f"Transcript {transcript_id} not found"
                }
                
            transcript = transcript_result.data[0]
            
            # Parse JSON metadata
            if "metadata" in transcript and isinstance(transcript["metadata"], str):
                try:
                    transcript["metadata"] = json.loads(transcript["metadata"])
                except:
                    transcript["metadata"] = {}
            
            # Get chunks
            chunks_result = self.client.table("transcript_chunks").select("*").eq("transcript_id", transcript_id).order("chunk_index").execute()
            
            if hasattr(chunks_result, 'error') and chunks_result.error is not None:
                logger.error(f"Error getting chunks: {chunks_result.error}")
                return {
                    "success": False,
                    "error": f"Error getting chunks: {chunks_result.error}"
                }
                
            chunks = chunks_result.data
            
            # Parse JSON metadata in chunks
            for chunk in chunks:
                if "metadata" in chunk and isinstance(chunk["metadata"], str):
                    try:
                        chunk["metadata"] = json.loads(chunk["metadata"])
                    except:
                        chunk["metadata"] = {}
            
            return {
                "success": True,
                "transcript": transcript,
                "chunks": chunks
            }
                
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
            
    async def get_transcripts(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Get all transcripts accessible to the current user
        
        With Row Level Security (RLS) policies in place, this will only return
        transcripts that the current user has access to.
        """
        if not self.is_connected():
            return {
                "success": False,
                "error": "Supabase client not connected"
            }
        
        try:
            # Query transcripts table
            response = self.client.table("transcripts").select("*").range(offset, offset + limit - 1).execute()
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                return {
                    "success": False,
                    "error": f"Error getting transcripts: {response.error}"
                }
            
            return {
                "success": True,
                "data": response.data,
                "count": len(response.data)
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Error getting transcripts: {str(e)}"
            }
    
    async def share_transcript(self, transcript_id: str, user_id: Optional[str] = None, 
                             company_id: Optional[str] = None, access_level: str = "read") -> Dict[str, Any]:
        """
        Share a transcript with a user or company
        
        Args:
            transcript_id: ID of the transcript to share
            user_id: ID of the user to share with (optional)
            company_id: ID of the company to share with (optional)
            access_level: Access level to grant (read, write, owner)
            
        Returns:
            Dict with success status and error message if any
        """
        if not self.is_connected():
            return {
                "success": False,
                "error": "Supabase client not connected"
            }
        
        if not user_id and not company_id:
            return {
                "success": False,
                "error": "Either user_id or company_id must be provided"
            }
        
        try:
            # Check if transcript exists
            transcript_check = await self.get_transcript_by_id(transcript_id)
            if not transcript_check.get("success"):
                return {
                    "success": False,
                    "error": f"Transcript not found: {transcript_id}"
                }
            
            # Prepare data for insertion
            share_data = {
                "transcript_id": transcript_id,
                "access_level": access_level,
            }
            
            # Add either user_id or company_id
            if user_id:
                share_data["user_id"] = user_id
            if company_id:
                share_data["company_id"] = company_id
            
            # Insert into transcript_access table
            # Use upsert to update if already exists
            response = self.client.table("transcript_access").upsert(
                share_data,
                on_conflict=["transcript_id", "user_id" if user_id else "company_id"]
            ).execute()
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                return {
                    "success": False,
                    "error": f"Error sharing transcript: {response.error}"
                }
            
            return {
                "success": True,
                "data": response.data[0] if response.data else None
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Error sharing transcript: {str(e)}"
            }
    
    async def remove_transcript_share(self, transcript_id: str, user_id: Optional[str] = None, 
                                    company_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Remove transcript sharing from a user or company
        
        Args:
            transcript_id: ID of the transcript
            user_id: ID of the user to remove sharing from (optional)
            company_id: ID of the company to remove sharing from (optional)
            
        Returns:
            Dict with success status and error message if any
        """
        if not self.is_connected():
            return {
                "success": False,
                "error": "Supabase client not connected"
            }
        
        if not user_id and not company_id:
            return {
                "success": False,
                "error": "Either user_id or company_id must be provided"
            }
        
        try:
            # Build query to delete the access record
            query = self.client.table("transcript_access").delete().eq("transcript_id", transcript_id)
            
            # Add filter for either user_id or company_id
            if user_id:
                query = query.eq("user_id", user_id)
            if company_id:
                query = query.eq("company_id", company_id)
            
            # Execute the query
            response = query.execute()
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                return {
                    "success": False,
                    "error": f"Error removing transcript share: {response.error}"
                }
            
            # Check if any records were deleted
            if not response.data or len(response.data) == 0:
                return {
                    "success": False,
                    "error": "No matching share record found"
                }
            
            return {
                "success": True,
                "message": "Share removed successfully"
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Error removing transcript share: {str(e)}"
            }
    
    async def get_transcript_access(self, transcript_id: str) -> Dict[str, Any]:
        """
        Get all users and companies that have access to a transcript
        
        Args:
            transcript_id: ID of the transcript
            
        Returns:
            Dict with access information
        """
        if not self.is_connected():
            return {
                "success": False,
                "error": "Supabase client not connected"
            }
        
        try:
            # Query transcript_access table
            response = self.client.table("transcript_access").select("*").eq("transcript_id", transcript_id).execute()
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                return {
                    "success": False,
                    "error": f"Error getting transcript access: {response.error}"
                }
            
            # Process the data into separate lists for users and companies
            users = []
            companies = []
            
            for access in response.data:
                if "user_id" in access and access["user_id"]:
                    users.append({
                        "user_id": access["user_id"],
                        "access_level": access["access_level"],
                        "created_at": access["created_at"]
                    })
                elif "company_id" in access and access["company_id"]:
                    companies.append({
                        "company_id": access["company_id"],
                        "access_level": access["access_level"],
                        "created_at": access["created_at"]
                    })
            
            return {
                "success": True,
                "users": users,
                "companies": companies,
                "count": len(response.data)
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Error getting transcript access: {str(e)}"
            }
            
    async def get_similar_chunks(self, 
                             embedding: List[float], 
                             transcript_id: Optional[str] = None, 
                             limit: int = 5,
                             similarity_threshold: float = 0.5) -> Dict[str, Any]:
        """Get chunks similar to the embedding vector"""
        try:
            # If using mock storage
            if self.use_mock:
                # In mock mode, just return some random chunks
                chunks = []
                if transcript_id:
                    chunks = [
                        chunk for chunk in mock_storage["transcript_chunks"] 
                        if chunk.get("transcript_id") == transcript_id
                    ]
                else:
                    chunks = mock_storage["transcript_chunks"]
                
                # Sort by chunk index and take the most recent ones
                chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))
                result_chunks = chunks[:min(limit, len(chunks))]
                
                # Add similarity scores (mock scores between 0.7 and 0.95)
                for i, chunk in enumerate(result_chunks):
                    chunk["similarity"] = 0.95 - (i * 0.05)
                
                return {
                    "success": True,
                    "data": result_chunks,
                    "is_mock": True
                }
                
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Build the query based on whether transcript_id is provided
            query = self.client.rpc(
                "match_chunks", 
                {
                    "query_embedding": embedding,
                    "match_threshold": similarity_threshold,
                    "match_count": limit
                }
            )
            
            # Add transcript_id filter if provided
            if transcript_id:
                query = query.eq("transcript_id", transcript_id)
                
            # Execute the query
            result = query.execute()
            
            if hasattr(result, 'error') and result.error is not None:
                logger.error(f"Error getting similar chunks: {result.error}")
                return {
                    "success": False,
                    "error": f"Error getting similar chunks: {result.error}"
                }
                
            chunks = result.data
            
            # Parse JSON metadata
            for chunk in chunks:
                if "metadata" in chunk and isinstance(chunk["metadata"], str):
                    try:
                        chunk["metadata"] = json.loads(chunk["metadata"])
                    except:
                        chunk["metadata"] = {}
            
            return {
                "success": True,
                "data": chunks
            }
                
        except Exception as e:
            logger.error(f"Error getting similar chunks: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
            
    async def store_key_points(self, transcript_id: str, analysis: str) -> Dict[str, Any]:
        """Store key points analysis for a transcript"""
        try:
            # If using mock storage
            if self.use_mock:
                mock_storage["key_points"][transcript_id] = {
                    "transcript_id": transcript_id,
                    "analysis": analysis,
                    "created_at": datetime.now().isoformat()
                }
                
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "is_mock": True
                }
                
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Format data
            key_points_data = {
                "transcript_id": transcript_id,
                "analysis": analysis,
                "created_at": datetime.now().isoformat()
            }
            
            # Insert or update
            result = self.client.table("transcript_key_points").upsert(key_points_data).execute()
            
            if hasattr(result, 'error') and result.error is not None:
                logger.error(f"Error storing key points: {result.error}")
                return {
                    "success": False,
                    "error": f"Error storing key points: {result.error}"
                }
                
            return {
                "success": True,
                "transcript_id": transcript_id
            }
                
        except Exception as e:
            logger.error(f"Error storing key points: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
            
    async def get_key_points(self, transcript_id: str) -> Dict[str, Any]:
        """Get key points analysis for a transcript"""
        try:
            # If using mock storage
            if self.use_mock:
                if transcript_id not in mock_storage["key_points"]:
                    return {
                        "success": False,
                        "error": f"Key points for transcript {transcript_id} not found in mock storage"
                    }
                    
                return {
                    "success": True,
                    "data": mock_storage["key_points"][transcript_id],
                    "is_mock": True
                }
                
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Get key points
            result = self.client.table("transcript_key_points").select("*").eq("transcript_id", transcript_id).execute()
            
            if hasattr(result, 'error') and result.error is not None:
                logger.error(f"Error getting key points: {result.error}")
                return {
                    "success": False,
                    "error": f"Error getting key points: {result.error}"
                }
                
            # Check if key points exist
            if not result.data or len(result.data) == 0:
                return {
                    "success": False,
                    "error": f"Key points for transcript {transcript_id} not found"
                }
                
            return {
                "success": True,
                "data": result.data[0]
            }
                
        except Exception as e:
            logger.error(f"Error getting key points: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

    def is_connected(self) -> bool:
        """Check if the Supabase client is connected and initialized"""
        return self.initialized and not self.use_mock
        
    async def setup_pgvector(self) -> Dict[str, Any]:
        """
        Run the SQL setup script to initialize pgvector extension and create tables
        This should be run once when setting up a new Supabase project
        """
        try:
            # If using mock storage, just return success
            if self.use_mock:
                return {
                    "success": True,
                    "message": "Mock mode - skipping pgvector setup",
                    "is_mock": True
                }
                
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Check if pgvector extension is available
            pgvector_check = await self.check_pgvector()
            if not pgvector_check["success"]:
                return pgvector_check
                
            # Read the SQL setup script
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                      "scripts", "supabase_setup.sql")
            
            if not os.path.exists(script_path):
                logger.error(f"SQL setup script not found at: {script_path}")
                return {
                    "success": False,
                    "error": "SQL setup script not found"
                }
                
            with open(script_path, 'r') as f:
                sql_script = f.read()
                
            # Split the script into individual statements
            statements = sql_script.split(';')
            results = []
            
            # Execute each statement
            for statement in statements:
                statement = statement.strip()
                if not statement:
                    continue
                    
                try:
                    # Execute the SQL statement
                    result = self.client.rpc("exec_sql", {"sql": statement}).execute()
                    
                    if hasattr(result, 'error') and result.error is not None:
                        logger.warning(f"SQL execution warning: {result.error}")
                        results.append({
                            "status": "warning",
                            "message": str(result.error)
                        })
                    else:
                        results.append({
                            "status": "success",
                            "statement": statement[:50] + "..." if len(statement) > 50 else statement
                        })
                except Exception as e:
                    logger.warning(f"Error executing SQL statement: {str(e)}")
                    results.append({
                        "status": "error",
                        "message": str(e),
                        "statement": statement[:50] + "..." if len(statement) > 50 else statement
                    })
            
            # Check for critical errors
            errors = [r for r in results if r["status"] == "error"]
            if errors:
                return {
                    "success": False,
                    "error": "Some SQL statements failed to execute",
                    "details": errors
                }
                
            return {
                "success": True,
                "message": "pgvector setup completed successfully",
                "details": results
            }
                
        except Exception as e:
            logger.error(f"Error setting up pgvector: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
            
    async def check_pgvector(self) -> Dict[str, Any]:
        """Check if pgvector extension is installed in Supabase"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "is_enabled": True,
                "is_mock": True
            }
        
        try:
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
            
            # First try using the safer check_extension_exists function
            try:
                result = self.client.rpc("check_extension_exists", {"extension_name": "vector"}).execute()
                
                if hasattr(result, 'data'):
                    return {
                        "success": True,
                        "is_enabled": result.data.get("exists", False)
                    }
            except Exception as e:
                logger.warning(f"check_extension_exists function not available: {str(e)}")
                # Fall back to exec_sql if check_extension_exists is not available
            
            # Try using exec_sql as fallback
            query = "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');"
            result = self.client.rpc("exec_sql", {"sql": query}).execute()
            
            if hasattr(result, 'data') and result.data.get("success", False):
                # Extract the boolean result from the response
                return {
                    "success": True,
                    "is_enabled": True,  # If we get here, it means the extension exists
                    "message": "Extension found via exec_sql"
                }
            else:
                return {
                    "success": False,
                    "is_enabled": False,
                    "error": "Failed to check pgvector extension status"
                }
        except Exception as e:
            logger.error(f"Error checking pgvector extension: {str(e)}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def store_transcript_embeddings(self, transcript_id: str, chunk_embeddings: List[List[float]]) -> Dict[str, Any]:
        """
        Store embeddings for transcript chunks
        This updates existing chunks with embedding vectors
        """
        start_time = time.time()
        
        try:
            # If using mock storage, just return success
            if self.use_mock:
                # Update mock chunks with embeddings
                chunks = mock_storage["transcript_chunks"]
                chunks_for_transcript = [chunk for chunk in chunks if chunk.get("transcript_id") == transcript_id]
                
                for i, chunk in enumerate(chunks_for_transcript):
                    if i < len(chunk_embeddings):
                        chunk["embedding"] = chunk_embeddings[i]
                
                logger.info(f"Stored {len(chunk_embeddings)} mock embeddings for transcript {transcript_id}")
                
                end_time = time.time()
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "chunks_updated": min(len(chunks_for_transcript), len(chunk_embeddings)),
                    "processing_time": end_time - start_time,
                    "is_mock": True
                }
                
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Get chunks for the transcript
            chunks_result = await self.get_transcript_by_id(transcript_id)
            
            if not chunks_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to get transcript chunks: {chunks_result.get('error')}"
                }
                
            chunks = chunks_result.get("chunks", [])
            
            if not chunks:
                return {
                    "success": False,
                    "error": f"No chunks found for transcript {transcript_id}"
                }
                
            # Check if we have enough embeddings
            if len(chunks) != len(chunk_embeddings):
                logger.warning(f"Chunk count ({len(chunks)}) doesn't match embedding count ({len(chunk_embeddings)})")
                # Truncate to the shorter of the two
                chunk_count = min(len(chunks), len(chunk_embeddings))
                chunks = chunks[:chunk_count]
                chunk_embeddings = chunk_embeddings[:chunk_count]
            
            # Update each chunk with its embedding
            updated_count = 0
            for i, chunk in enumerate(chunks):
                chunk_id = chunk.get("id")
                
                if not chunk_id:
                    logger.warning(f"Chunk at index {i} has no ID, skipping")
                    continue
                
                # Update the chunk with embedding
                update_result = self.client.table("transcript_chunks").update({
                    "embedding": chunk_embeddings[i]
                }).eq("id", chunk_id).execute()
                
                if hasattr(update_result, 'error') and update_result.error is not None:
                    logger.warning(f"Error updating chunk {chunk_id}: {update_result.error}")
                else:
                    updated_count += 1
            
            end_time = time.time()
            logger.info(f"Updated {updated_count}/{len(chunks)} chunks with embeddings in {end_time - start_time:.2f}s")
            
            return {
                "success": True,
                "transcript_id": transcript_id,
                "chunks_updated": updated_count,
                "processing_time": end_time - start_time
            }
                
        except Exception as e:
            logger.error(f"Error storing transcript embeddings: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def create_transcript_with_embeddings(self, 
                                            transcript_id: str, 
                                            metadata: Dict[str, Any], 
                                            chunks: List[Dict[str, Any]], 
                                            embeddings: List[List[float]]) -> Dict[str, Any]:
        """
        Create a transcript record with chunks and embeddings in one operation
        This is more efficient than separate calls for storage and embedding updates
        """
        start_time = time.time()
        
        try:
            # If using mock storage
            if self.use_mock:
                # Store in mock data
                mock_storage["transcripts"][transcript_id] = {
                    "transcript_id": transcript_id,
                    "metadata": metadata,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Ensure chunk_ids and attach embeddings
                chunk_data = []
                for i, chunk in enumerate(chunks):
                    chunk_id = str(uuid.uuid4())
                    chunk_with_embedding = {
                        "id": chunk_id,
                        "transcript_id": transcript_id,
                        "chunk_index": chunk.get("chunk_index", i),
                        "text": chunk.get("text", ""),
                        "position": chunk.get("position", i),
                        "is_first": chunk.get("is_first", i == 0),
                        "is_last": chunk.get("is_last", i == len(chunks) - 1),
                        "metadata": chunk.get("metadata", {}),
                        "embedding": embeddings[i] if i < len(embeddings) else None
                    }
                    chunk_data.append(chunk_with_embedding)
                    
                mock_storage["transcript_chunks"].extend(chunk_data)
                
                logger.info(f"Stored transcript {transcript_id} in mock storage with {len(chunks)} chunks and embeddings")
                
                end_time = time.time()
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "chunks_stored": len(chunks),
                    "processing_time": end_time - start_time,
                    "is_mock": True
                }
                
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Format transcript data
            transcript_data = {
                "transcript_id": transcript_id,
                "title": metadata.get("title", f"Transcript {transcript_id}"),
                "meeting_id": metadata.get("meeting_id", ""),
                "date": metadata.get("date", datetime.now().isoformat()),
                "word_count": metadata.get("word_count", 0),
                "duration_seconds": metadata.get("duration_seconds", 0),
                "source": metadata.get("source", "fireflies")
            }
            
            # Store transcript metadata
            transcript_result = self.client.table("transcripts").insert(transcript_data).execute()
            
            if hasattr(transcript_result, 'error') and transcript_result.error is not None:
                logger.error(f"Error storing transcript: {transcript_result.error}")
                return {
                    "success": False,
                    "error": f"Error storing transcript: {transcript_result.error}"
                }
                
            # Prepare chunks data with embeddings
            chunks_data = []
            
            # Truncate to the shorter of chunks or embeddings
            chunk_count = min(len(chunks), len(embeddings))
            
            for i in range(chunk_count):
                chunk = chunks[i]
                embedding = embeddings[i]
                
                chunk_data = {
                    "transcript_id": transcript_id,
                    "chunk_index": chunk.get("chunk_index", i),
                    "text": chunk.get("text", ""),
                    "position": chunk.get("position", i),
                    "is_first": chunk.get("is_first", i == 0),
                    "is_last": chunk.get("is_last", i == chunk_count - 1),
                    "metadata": json.dumps(chunk.get("metadata", {})),
                    "embedding": embedding
                }
                chunks_data.append(chunk_data)
                
            # Insert chunks in batches to avoid hitting payload limits
            batch_size = 20  # Smaller batch size due to embeddings
            inserted_count = 0
            
            for i in range(0, len(chunks_data), batch_size):
                batch = chunks_data[i:i+batch_size]
                chunks_result = self.client.table("transcript_chunks").insert(batch).execute()
                
                if hasattr(chunks_result, 'error') and chunks_result.error is not None:
                    logger.warning(f"Error inserting chunk batch: {chunks_result.error}")
                else:
                    inserted_count += len(batch)
            
            end_time = time.time()
            logger.info(f"Stored transcript {transcript_id} with {inserted_count}/{len(chunks_data)} chunks and embeddings in {end_time - start_time:.2f}s")
            
            return {
                "success": True,
                "transcript_id": transcript_id,
                "chunks_stored": inserted_count,
                "processing_time": end_time - start_time
            }
                
        except Exception as e:
            logger.error(f"Error creating transcript with embeddings: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def create_transcript_record(self, transcript_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a transcript record (without chunks)
        This is used by the ingestion service to create the transcript first, then add chunks separately
        """
        try:
            # If using mock storage
            if self.use_mock:
                mock_storage["transcripts"][transcript_id] = {
                    "transcript_id": transcript_id,
                    "metadata": metadata,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                logger.info(f"Created transcript record {transcript_id} in mock storage")
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # First, check if transcript already exists
            existing_check = self.client.table("transcripts").select("transcript_id").eq("transcript_id", transcript_id).execute()
            
            if existing_check.data and len(existing_check.data) > 0:
                logger.warning(f"Transcript {transcript_id} already exists, skipping creation")
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "already_exists": True,
                    "message": "Transcript already exists, skipping creation"
                }
            
            # Format transcript data
            transcript_data = {
                "transcript_id": transcript_id,
                "title": metadata.get("title", f"Transcript {transcript_id}"),
                "meeting_id": metadata.get("meeting_id", ""),
                "date": metadata.get("date", datetime.now().isoformat()),
                "word_count": metadata.get("word_count", 0),
                "duration_seconds": metadata.get("duration_seconds", 0),
                "source": metadata.get("source", "fireflies"),
                "user_id": metadata.get("user_id"),  # Include user_id if provided
                "metadata": json.dumps(metadata)
            }
            
            # Store transcript metadata
            transcript_result = self.client.table("transcripts").insert(transcript_data).execute()
            
            if hasattr(transcript_result, 'error') and transcript_result.error is not None:
                logger.error(f"Error creating transcript record: {transcript_result.error}")
                return {
                    "success": False,
                    "error": f"Error creating transcript record: {transcript_result.error}"
                }
                
            logger.info(f"Created transcript record {transcript_id}")
            return {
                "success": True,
                "transcript_id": transcript_id
            }
                
        except Exception as e:
            logger.error(f"Error creating transcript record: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def store_transcript_chunks(self, transcript_id: str, chunks: List[Dict[str, Any]], embeddings: Optional[List[List[float]]] = None) -> Dict[str, Any]:
        """
        Store transcript chunks (and optionally embeddings) for an existing transcript
        This is used by the ingestion service after creating the transcript record
        """
        start_time = time.time()
        
        try:
            # If using mock storage
            if self.use_mock:
                # Store chunks
                for i, chunk in enumerate(chunks):
                    chunk_id = str(uuid.uuid4())
                    chunk_data = {
                        "id": chunk_id,
                        "transcript_id": transcript_id,
                        "chunk_index": chunk.get("chunk_index", i),
                        "text": chunk.get("text", ""),
                        "position": chunk.get("position", i),
                        "is_first": chunk.get("is_first", i == 0),
                        "is_last": chunk.get("is_last", i == len(chunks) - 1),
                        "metadata": chunk.get("metadata", {}),
                        "embedding": embeddings[i] if embeddings and i < len(embeddings) else None
                    }
                    mock_storage["transcript_chunks"].append(chunk_data)
                
                logger.info(f"Stored {len(chunks)} chunks for transcript {transcript_id} in mock storage")
                
                end_time = time.time()
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "count": len(chunks),
                    "processing_time": end_time - start_time,
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Prepare chunks data
            chunks_data = []
            for i, chunk in enumerate(chunks):
                chunk_data = {
                    "transcript_id": transcript_id,
                    "chunk_index": chunk.get("chunk_index", i),
                    "text": chunk.get("text", ""),
                    "position": chunk.get("position", i),
                    "is_first": chunk.get("is_first", i == 0),
                    "is_last": chunk.get("is_last", i == len(chunks) - 1),
                    "metadata": json.dumps(chunk.get("metadata", {}))
                }
                
                # Add embedding if provided
                if embeddings and i < len(embeddings):
                    chunk_data["embedding"] = embeddings[i]
                    
                chunks_data.append(chunk_data)
                
            # Insert chunks in batches to avoid hitting payload limits
            batch_size = 20 if embeddings else 50  # Smaller batch size if embeddings included
            inserted_count = 0
            
            for i in range(0, len(chunks_data), batch_size):
                batch = chunks_data[i:i+batch_size]
                chunks_result = self.client.table("transcript_chunks").insert(batch).execute()
                
                if hasattr(chunks_result, 'error') and chunks_result.error is not None:
                    logger.error(f"Error storing chunks batch {i//batch_size}: {chunks_result.error}")
                    # Continue with next batch despite errors
                else:
                    inserted_count += len(batch)
            
            end_time = time.time()
            logger.info(f"Stored {inserted_count}/{len(chunks)} chunks for transcript {transcript_id} in {end_time - start_time:.2f}s")
            
            return {
                "success": True,
                "transcript_id": transcript_id,
                "count": inserted_count,
                "processing_time": end_time - start_time
            }
                
        except Exception as e:
            logger.error(f"Error storing transcript chunks: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def update_transcript_record(self, transcript_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing transcript record with new data
        This is used by the ingestion service to add summary, etc.
        """
        try:
            # If using mock storage
            if self.use_mock:
                if transcript_id not in mock_storage["transcripts"]:
                    return {
                        "success": False,
                        "error": f"Transcript {transcript_id} not found in mock storage"
                    }
                
                # Update the transcript
                mock_storage["transcripts"][transcript_id].update(updates)
                mock_storage["transcripts"][transcript_id]["updated_at"] = datetime.now().isoformat()
                
                logger.info(f"Updated transcript record {transcript_id} in mock storage")
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Prepare update data
            update_data = {**updates}
            update_data["updated_at"] = datetime.now().isoformat()
            
            # CRITICAL FIX: Handle PostgreSQL btree index size limits
            # The "summary" field has an index that can't exceed ~2.7KB
            if "summary" in update_data:
                summary_content = update_data["summary"]
                if isinstance(summary_content, str):
                    summary_bytes = len(summary_content.encode('utf-8'))
                    
                    # PostgreSQL btree index limit is ~2704 bytes, use 2500 for safety
                    MAX_INDEXED_SUMMARY_SIZE = 2500
                    
                    if summary_bytes > MAX_INDEXED_SUMMARY_SIZE:
                        logger.warning(f"Summary size ({summary_bytes} bytes) exceeds index limit, truncating for storage")
                        
                        # Store full summary in a separate field that's not indexed
                        # Column has been added via migration
                        update_data["detailed_summary"] = summary_content
                        
                        # Truncate summary for indexed field (preserve structure)
                        truncated_summary = self._truncate_summary_smartly(summary_content, MAX_INDEXED_SUMMARY_SIZE - 100)  # Leave buffer
                        update_data["summary"] = truncated_summary
                        
                        logger.info(f"Stored full summary ({len(summary_content.encode('utf-8'))} bytes) in detailed_summary and truncated version ({len(truncated_summary.encode('utf-8'))} bytes) in summary")
            
            # Update transcript record
            update_result = self.client.table("transcripts").update(update_data).eq("transcript_id", transcript_id).execute()
            
            if hasattr(update_result, 'error') and update_result.error is not None:
                logger.error(f"Error updating transcript record: {update_result.error}")
                return {
                    "success": False,
                    "error": f"Error updating transcript record: {update_result.error}"
                }
                
            logger.info(f"Updated transcript record {transcript_id}")
            return {
                "success": True,
                "transcript_id": transcript_id
            }
                
        except Exception as e:
            logger.error(f"Error updating transcript record: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    def _truncate_summary_smartly(self, summary: str, max_bytes: int) -> str:
        """
        Intelligently truncate a summary to fit within byte limits while preserving structure.
        
        Args:
            summary: The full summary content
            max_bytes: Maximum bytes allowed
            
        Returns:
            Truncated summary that fits within the limit
        """
        try:
            # If already within limit, return as-is
            if len(summary.encode('utf-8')) <= max_bytes:
                return summary
            
            # Try to preserve the executive summary and first few sections
            lines = summary.split('\n')
            truncated_lines = []
            current_bytes = 0
            
            # Always try to include the first line (title/header)
            if lines:
                first_line = lines[0]
                first_line_bytes = len(first_line.encode('utf-8')) + 1  # +1 for newline
                if first_line_bytes < max_bytes:
                    truncated_lines.append(first_line)
                    current_bytes += first_line_bytes
            
            # Add remaining lines until we hit the limit
            for line in lines[1:]:
                line_bytes = len(line.encode('utf-8')) + 1  # +1 for newline
                if current_bytes + line_bytes > max_bytes - 50:  # Leave room for truncation notice
                    break
                truncated_lines.append(line)
                current_bytes += line_bytes
            
            # Add truncation notice
            truncated_summary = '\n'.join(truncated_lines)
            if current_bytes < len(summary.encode('utf-8')):
                truncated_summary += "\n\n[Content truncated - full summary available in detailed view]"
            
            return truncated_summary
            
        except Exception as e:
            logger.error(f"Error truncating summary: {str(e)}")
            # Fallback: simple character-based truncation
            max_chars = max_bytes // 2  # Rough estimate assuming average 2 bytes per char
            if len(summary) > max_chars:
                return summary[:max_chars-50] + "\n\n[Content truncated]"
            return summary
    
    async def get_subscribers(self) -> Dict[str, Any]:
        """
        Get email subscribers for notifications
        This method provides compatibility with FileStorageService interface
        """
        try:
            # If using mock storage
            if self.use_mock:
                return {
                    "success": True,
                    "subscribers": mock_storage.get("subscribers", []),
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Try to get subscribers from database (assuming a subscribers table exists)
            try:
                subscribers_result = self.client.table("subscribers").select("*").execute()
                
                if hasattr(subscribers_result, 'error') and subscribers_result.error is not None:
                    logger.warning(f"No subscribers table found or error: {subscribers_result.error}")
                    subscribers = []
                else:
                    subscribers = subscribers_result.data or []
                    
            except Exception as e:
                logger.warning(f"Could not fetch subscribers from database: {str(e)}")
                subscribers = []
                
            logger.info(f"Retrieved {len(subscribers)} subscribers")
            return {
                "success": True,
                "subscribers": subscribers
            }
                
        except Exception as e:
            logger.error(f"Error getting subscribers: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def create_trade_record(self, transcript_id: str, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a trade record in the database
        This method provides compatibility with FileStorageService interface
        """
        try:
            # If using mock storage
            if self.use_mock:
                trade_id = str(uuid.uuid4())
                trade_record = {
                    "id": trade_id,
                    "transcript_id": transcript_id,
                    "created_at": datetime.now().isoformat(),
                    **trade_data
                }
                
                if "trades" not in mock_storage:
                    mock_storage["trades"] = []
                    
                mock_storage["trades"].append(trade_record)
                
                logger.info(f"Created trade record for transcript {transcript_id} in mock storage")
                return {
                    "success": True,
                    "data": trade_record,
                    "is_mock": True
                }
            
            # Check if client is initialized
            if not self.initialized:
                self._initialize_client()
                
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
                
            # Prepare trade data for database
            trade_record = {
                "transcript_id": transcript_id,
                "symbol": trade_data.get("symbol", ""),
                "action": trade_data.get("action", ""),
                "price": trade_data.get("price", ""),
                "quantity": trade_data.get("quantity", ""),
                "confidence": trade_data.get("confidence", 0.0),
                "reasoning": trade_data.get("reasoning", trade_data.get("rationale", "")),
                "timestamp_mentioned": trade_data.get("timestamp_mentioned", ""),
                "metadata": json.dumps(trade_data),
                "created_at": datetime.now().isoformat()
            }
            
            # Try to insert into trades table (assuming it exists)
            try:
                trade_result = self.client.table("trades").insert(trade_record).execute()
                
                if hasattr(trade_result, 'error') and trade_result.error is not None:
                    logger.error(f"Error creating trade record: {trade_result.error}")
                    return {
                        "success": False,
                        "error": f"Error creating trade record: {trade_result.error}"
                    }
                    
                logger.info(f"Created trade record for transcript {transcript_id}")
                return {
                    "success": True,
                    "data": trade_result.data[0] if trade_result.data else trade_record
                }
                
            except Exception as e:
                logger.warning(f"Could not store trade in database (table may not exist): {str(e)}")
                # Fallback to successful response without actual storage
                return {
                    "success": True,
                    "data": trade_record,
                    "note": "Trade record created but not stored (trades table may not exist)"
                }
                
        except Exception as e:
            logger.error(f"Error creating trade record: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_transcript_text(self, transcript_id: str) -> Dict[str, Any]:
        """Get transcript text by concatenating all chunks in order"""
        try:
            if self.use_mock:
                if transcript_id in mock_storage["transcripts"]:
                    # Get chunks for this transcript
                    chunks = [chunk for chunk in mock_storage["transcript_chunks"] 
                             if chunk.get("transcript_id") == transcript_id]
                    
                    # Sort by chunk_index
                    chunks.sort(key=lambda x: x.get("chunk_index", 0))
                    
                    # Concatenate text
                    full_text = " ".join([chunk.get("text", "") for chunk in chunks])
                    
                    return {
                        "success": True,
                        "transcript_id": transcript_id,
                        "text": full_text,
                        "chunk_count": len(chunks),
                        "is_mock": True
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Transcript {transcript_id} not found in mock storage"
                    }
            
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
            
            # Get chunks ordered by chunk_index
            chunks_result = self.client.table("transcript_chunks")\
                .select("text, chunk_index")\
                .eq("transcript_id", transcript_id)\
                .order("chunk_index")\
                .execute()
            
            if hasattr(chunks_result, 'error') and chunks_result.error is not None:
                logger.error(f"Error fetching chunks: {chunks_result.error}")
                return {
                    "success": False,
                    "error": f"Error fetching chunks: {chunks_result.error}"
                }
            
            chunks = chunks_result.data
            if not chunks:
                return {
                    "success": False,
                    "error": f"No chunks found for transcript {transcript_id}"
                }
            
            # Concatenate all chunk text
            full_text = " ".join([chunk["text"] for chunk in chunks])
            
            return {
                "success": True,
                "transcript_id": transcript_id,
                "text": full_text,
                "chunk_count": len(chunks)
            }
            
        except Exception as e:
            logger.error(f"Error getting transcript text: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def delete_transcript(self, transcript_id: str) -> Dict[str, Any]:
        """
        Safely delete a transcript and all its related data.
        
        This method deletes in the proper order to respect foreign key constraints:
        1. Delete semantic chunks (if they exist)
        2. Delete transcript chunks  
        3. Delete transcript shares (access control)
        4. Delete key points analysis
        5. Delete the main transcript record
        
        Args:
            transcript_id: The ID of the transcript to delete
            
        Returns:
            Dict containing success status and deletion summary
        """
        start_time = time.time()
        deleted_items = {
            "semantic_chunks": 0,
            "transcript_chunks": 0,
            "transcript_shares": 0, 
            "key_points": 0,
            "transcript": 0
        }
        
        try:
            # Handle mock storage
            if self.use_mock:
                # Delete from mock storage
                if transcript_id in mock_storage["transcripts"]:
                    del mock_storage["transcripts"][transcript_id]
                    deleted_items["transcript"] = 1
                
                # Delete transcript chunks
                original_chunks_count = len(mock_storage["transcript_chunks"])
                mock_storage["transcript_chunks"] = [
                    chunk for chunk in mock_storage["transcript_chunks"] 
                    if chunk.get("transcript_id") != transcript_id
                ]
                deleted_items["transcript_chunks"] = original_chunks_count - len(mock_storage["transcript_chunks"])
                
                # Delete key points
                if transcript_id in mock_storage["key_points"]:
                    del mock_storage["key_points"][transcript_id]
                    deleted_items["key_points"] = 1
                
                end_time = time.time()
                logger.info(f"Deleted transcript {transcript_id} from mock storage in {end_time - start_time:.2f}s")
                
                return {
                    "success": True,
                    "transcript_id": transcript_id,
                    "deleted_items": deleted_items,
                    "processing_time": end_time - start_time,
                    "is_mock": True
                }
            
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Supabase client not initialized"
                }
            
            # First, check if transcript exists
            transcript_check = self.client.table("transcripts")\
                .select("transcript_id")\
                .eq("transcript_id", transcript_id)\
                .execute()
            
            if hasattr(transcript_check, 'error') and transcript_check.error is not None:
                return {
                    "success": False,
                    "error": f"Error checking transcript existence: {transcript_check.error}"
                }
            
            if not transcript_check.data:
                return {
                    "success": False,
                    "error": f"Transcript {transcript_id} not found"
                }
            
            logger.info(f"Starting deletion of transcript {transcript_id} and all related data...")
            
            # Step 1: Delete semantic chunks (if semantic_chunks table exists)
            try:
                semantic_result = self.client.table("semantic_chunks")\
                    .delete()\
                    .eq("transcript_id", transcript_id)\
                    .execute()
                
                if hasattr(semantic_result, 'error') and semantic_result.error is not None:
                    logger.warning(f"Could not delete semantic chunks (table may not exist): {semantic_result.error}")
                else:
                    deleted_items["semantic_chunks"] = len(semantic_result.data) if semantic_result.data else 0
                    logger.info(f"Deleted {deleted_items['semantic_chunks']} semantic chunks")
            except Exception as e:
                logger.warning(f"Could not delete semantic chunks: {str(e)}")
            
            # Step 2: Delete transcript chunks
            try:
                chunks_result = self.client.table("transcript_chunks")\
                    .delete()\
                    .eq("transcript_id", transcript_id)\
                    .execute()
                
                if hasattr(chunks_result, 'error') and chunks_result.error is not None:
                    logger.error(f"Error deleting transcript chunks: {chunks_result.error}")
                    return {
                        "success": False,
                        "error": f"Error deleting transcript chunks: {chunks_result.error}"
                    }
                
                deleted_items["transcript_chunks"] = len(chunks_result.data) if chunks_result.data else 0
                logger.info(f"Deleted {deleted_items['transcript_chunks']} transcript chunks")
            except Exception as e:
                logger.error(f"Error deleting transcript chunks: {str(e)}")
                return {
                    "success": False,
                    "error": f"Error deleting transcript chunks: {str(e)}"
                }
            
            # Step 3: Delete transcript shares (access control)
            try:
                shares_result = self.client.table("transcript_shares")\
                    .delete()\
                    .eq("transcript_id", transcript_id)\
                    .execute()
                
                if hasattr(shares_result, 'error') and shares_result.error is not None:
                    logger.warning(f"Could not delete transcript shares (table may not exist): {shares_result.error}")
                else:
                    deleted_items["transcript_shares"] = len(shares_result.data) if shares_result.data else 0
                    logger.info(f"Deleted {deleted_items['transcript_shares']} transcript shares")
            except Exception as e:
                logger.warning(f"Could not delete transcript shares: {str(e)}")
            
            # Step 4: Delete key points analysis
            try:
                key_points_result = self.client.table("key_points")\
                    .delete()\
                    .eq("transcript_id", transcript_id)\
                    .execute()
                
                if hasattr(key_points_result, 'error') and key_points_result.error is not None:
                    logger.warning(f"Could not delete key points (table may not exist): {key_points_result.error}")
                else:
                    deleted_items["key_points"] = len(key_points_result.data) if key_points_result.data else 0
                    logger.info(f"Deleted {deleted_items['key_points']} key points records")
            except Exception as e:
                logger.warning(f"Could not delete key points: {str(e)}")
            
            # Step 5: Delete the main transcript record
            try:
                transcript_result = self.client.table("transcripts")\
                    .delete()\
                    .eq("transcript_id", transcript_id)\
                    .execute()
                
                if hasattr(transcript_result, 'error') and transcript_result.error is not None:
                    logger.error(f"Error deleting transcript: {transcript_result.error}")
                    return {
                        "success": False,
                        "error": f"Error deleting transcript: {transcript_result.error}"
                    }
                
                deleted_items["transcript"] = len(transcript_result.data) if transcript_result.data else 0
                logger.info(f"Deleted {deleted_items['transcript']} transcript record")
            except Exception as e:
                logger.error(f"Error deleting transcript: {str(e)}")
                return {
                    "success": False,
                    "error": f"Error deleting transcript: {str(e)}"
                }
            
            end_time = time.time()
            total_deleted = sum(deleted_items.values())
            
            logger.info(f"✅ Successfully deleted transcript {transcript_id} and all related data:")
            logger.info(f"   - Transcript record: {deleted_items['transcript']}")
            logger.info(f"   - Transcript chunks: {deleted_items['transcript_chunks']}")
            logger.info(f"   - Semantic chunks: {deleted_items['semantic_chunks']}")
            logger.info(f"   - Key points: {deleted_items['key_points']}")
            logger.info(f"   - Transcript shares: {deleted_items['transcript_shares']}")
            logger.info(f"   - Total items deleted: {total_deleted}")
            logger.info(f"   - Processing time: {end_time - start_time:.2f}s")
            
            return {
                "success": True,
                "transcript_id": transcript_id,
                "deleted_items": deleted_items,
                "total_deleted": total_deleted,
                "processing_time": end_time - start_time
            }
            
        except Exception as e:
            logger.error(f"Error deleting transcript {transcript_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "deleted_items": deleted_items  # Return what was deleted before the error
            }

# Global instance for easy access
_supabase_service = None

def get_supabase_client():
    """Get a global Supabase client instance"""
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service.client if _supabase_service.initialized else None 