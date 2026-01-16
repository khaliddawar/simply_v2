# Unified Library Architecture Plan

## Executive Summary

This document outlines the plan to reorganize TubeVibe Library from a fragmented video/podcast architecture to a unified **Transcript Library** model. This enables treating all content sources (YouTube, Fireflies, Zoom, PDFs, audio files) as first-class citizens with shared organization, search, and summarization capabilities.

---

## 1. Architecture Decision

### Chosen Approach: Unified `transcripts` Table

**Rationale:**
- Future source types (PDFs, audio uploads) require only a new `source_type` value, not new tables
- Eliminates duplicate code paths for videos vs podcasts
- Single API surface reduces frontend complexity
- Processing pipeline is already unified—data layer should match
- Cleaner mental model for users: "My transcript library"

---

## 2. Database Schema

### 2.1 New `transcripts` Table

```sql
CREATE TABLE transcripts (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id UUID REFERENCES transcript_groups(id) ON DELETE SET NULL,

    -- Source identification
    source_type VARCHAR(50) NOT NULL,  -- 'youtube', 'fireflies', 'zoom', 'manual', 'pdf', 'audio'
    external_id VARCHAR(255),          -- youtube_id, meeting_id, filename, etc.

    -- Core content
    title VARCHAR(500) NOT NULL,
    transcript_text TEXT,
    transcript_length INTEGER,

    -- Pinecone integration
    pinecone_file_id VARCHAR(100),

    -- Summary cache
    summary_data JSONB,
    summary_generated_at TIMESTAMP WITH TIME ZONE,

    -- Source-specific metadata (flexible JSON)
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    UNIQUE(user_id, source_type, external_id)
);

-- Indexes for common queries
CREATE INDEX idx_transcripts_user_id ON transcripts(user_id);
CREATE INDEX idx_transcripts_group_id ON transcripts(group_id);
CREATE INDEX idx_transcripts_source_type ON transcripts(source_type);
CREATE INDEX idx_transcripts_created_at ON transcripts(created_at DESC);
CREATE INDEX idx_transcripts_user_source ON transcripts(user_id, source_type);
```

### 2.2 Rename Groups Table

```sql
-- Rename video_groups to transcript_groups for clarity
ALTER TABLE video_groups RENAME TO transcript_groups;
```

### 2.3 Source Type Enum

```python
class SourceType(str, Enum):
    YOUTUBE = "youtube"
    FIREFLIES = "fireflies"
    ZOOM = "zoom"
    MANUAL = "manual"
    PDF = "pdf"           # Future
    AUDIO = "audio"       # Future
    DOCUMENT = "document" # Future
```

### 2.4 Metadata Schema by Source Type

```python
# YouTube metadata
{
    "youtube_id": "dQw4w9WgXcQ",
    "channel_name": "Channel Name",
    "channel_id": "UC...",
    "thumbnail_url": "https://...",
    "duration_seconds": 212,
    "published_at": "2024-01-15T..."
}

# Fireflies/Zoom metadata
{
    "meeting_id": "abc123",
    "subject": "Weekly Standup",
    "organizer_email": "user@example.com",
    "participants": ["Alice", "Bob", "Charlie"],
    "meeting_date": "2024-01-15T10:00:00Z",
    "duration_minutes": 45,
    "source_url": "https://...",
    "action_items": [...]  # If available
}

# PDF metadata (future)
{
    "filename": "document.pdf",
    "page_count": 15,
    "file_size_bytes": 1024000,
    "author": "John Doe",
    "extracted_at": "2024-01-15T..."
}

# Audio metadata (future)
{
    "filename": "recording.mp3",
    "duration_seconds": 3600,
    "file_size_bytes": 50000000,
    "transcription_service": "whisper",
    "language": "en"
}
```

---

## 3. Backend Implementation

### 3.1 New Pydantic Models

**File:** `backend/app/models/transcript.py`

```python
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime

class SourceType(str, Enum):
    YOUTUBE = "youtube"
    FIREFLIES = "fireflies"
    ZOOM = "zoom"
    MANUAL = "manual"
    PDF = "pdf"
    AUDIO = "audio"

class TranscriptCreate(BaseModel):
    source_type: SourceType
    external_id: Optional[str] = None
    title: str
    transcript_text: str
    group_id: Optional[str] = None
    metadata: Dict[str, Any] = {}

class TranscriptResponse(BaseModel):
    id: str
    user_id: str
    group_id: Optional[str]
    source_type: SourceType
    external_id: Optional[str]
    title: str
    transcript_length: Optional[int]
    has_summary: bool
    summary_generated_at: Optional[datetime]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class TranscriptListResponse(BaseModel):
    transcripts: List[TranscriptResponse]
    total: int

class TranscriptSummaryResponse(BaseModel):
    transcript_id: str
    title: str
    source_type: SourceType
    summary: Dict[str, Any]  # Existing summary structure
    generated_at: datetime
```

### 3.2 New Unified Service

**File:** `backend/app/services/transcript_service.py`

```python
class TranscriptService:
    """
    Unified service for all transcript operations.
    Replaces VideoService and PodcastService for new code paths.
    """

    async def create_transcript(
        self,
        user_id: str,
        source_type: SourceType,
        title: str,
        transcript_text: str,
        external_id: Optional[str] = None,
        group_id: Optional[str] = None,
        metadata: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        """Create a new transcript from any source."""
        pass

    async def list_transcripts(
        self,
        user_id: str,
        group_id: Optional[str] = None,      # Filter by group
        source_type: Optional[str] = None,   # Filter by source
        ungrouped_only: bool = False,        # For "Recent" section
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List transcripts with filtering and sorting."""
        pass

    async def get_transcript(
        self,
        user_id: str,
        transcript_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single transcript by ID."""
        pass

    async def delete_transcript(
        self,
        user_id: str,
        transcript_id: str
    ) -> bool:
        """Delete a transcript and its Pinecone data."""
        pass

    async def move_to_group(
        self,
        user_id: str,
        transcript_id: str,
        group_id: Optional[str]  # None = move to Recent
    ) -> bool:
        """Move transcript to a group or back to Recent."""
        pass

    async def get_summary(
        self,
        user_id: str,
        transcript_id: str,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """Get or generate summary for a transcript."""
        pass
```

### 3.3 New API Routes

**File:** `backend/app/routes/transcripts.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])

@router.post("/", response_model=TranscriptResponse)
async def create_transcript(data: TranscriptCreate, user=Depends(get_current_user)):
    """Create a new transcript from any source."""
    pass

@router.get("/", response_model=TranscriptListResponse)
async def list_transcripts(
    user=Depends(get_current_user),
    group_id: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    ungrouped: bool = Query(False),
    sort_by: str = Query("created_at", regex="^(created_at|title|source_type)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """List user's transcripts with filtering and sorting."""
    pass

@router.get("/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(transcript_id: str, user=Depends(get_current_user)):
    """Get a specific transcript."""
    pass

@router.delete("/{transcript_id}")
async def delete_transcript(transcript_id: str, user=Depends(get_current_user)):
    """Delete a transcript."""
    pass

@router.patch("/{transcript_id}/group")
async def move_transcript(
    transcript_id: str,
    group_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Move transcript to a group (or to Recent if group_id is null)."""
    pass

@router.get("/{transcript_id}/summary", response_model=TranscriptSummaryResponse)
async def get_transcript_summary(
    transcript_id: str,
    force: bool = Query(False),
    user=Depends(get_current_user)
):
    """Get or generate summary for a transcript."""
    pass

@router.post("/{transcript_id}/email-summary")
async def email_transcript_summary(
    transcript_id: str,
    user=Depends(get_current_user)
):
    """Email summary to user."""
    pass
```

### 3.4 Backward Compatibility Layer

Keep existing endpoints working during transition by routing to new service:

**File:** `backend/app/routes/videos.py` (modified)

```python
# Add deprecation header
@router.get("/", deprecated=True)
async def list_videos(...):
    """DEPRECATED: Use /api/transcripts?source_type=youtube instead."""
    # Internally call transcript_service with source_type filter
    pass
```

---

## 4. Data Migration

### 4.1 Migration Script

**File:** `backend/scripts/migrate_to_unified_transcripts.py`

```python
"""
Migration script: videos + podcasts → transcripts

Run with: python -m scripts.migrate_to_unified_transcripts
"""

async def migrate():
    # 1. Create new transcripts table
    await create_transcripts_table()

    # 2. Migrate videos
    videos = await db.fetch("SELECT * FROM videos")
    for video in videos:
        await db.execute("""
            INSERT INTO transcripts (
                id, user_id, group_id, source_type, external_id,
                title, transcript_text, transcript_length,
                pinecone_file_id, summary_data, summary_generated_at,
                metadata, created_at, updated_at
            ) VALUES (
                $1, $2, $3, 'youtube', $4,
                $5, $6, $7,
                $8, $9, $10,
                $11, $12, $13
            )
        """,
            video['id'], video['user_id'], video['group_id'], video['youtube_id'],
            video['title'], video['transcript'], video['transcript_length'],
            video['pinecone_file_id'], video['summary_data'], video['summary_generated_at'],
            json.dumps({
                "youtube_id": video['youtube_id'],
                "channel_name": video['channel_name'],
                "duration_seconds": video['duration_seconds'],
                "thumbnail_url": video['thumbnail_url']
            }),
            video['created_at'], video['updated_at']
        )

    # 3. Migrate podcasts
    podcasts = await db.fetch("SELECT * FROM podcasts")
    for podcast in podcasts:
        await db.execute("""
            INSERT INTO transcripts (
                id, user_id, group_id, source_type, external_id,
                title, transcript_text, transcript_length,
                pinecone_file_id, summary_data, summary_generated_at,
                metadata, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10, $11,
                $12, $13, $14
            )
        """,
            podcast['id'], podcast['user_id'], podcast['group_id'],
            podcast['source'], podcast['external_id'],
            podcast['title'], podcast['transcript'], podcast['transcript_length'],
            podcast['pinecone_file_id'], podcast['summary_data'], podcast['summary_generated_at'],
            json.dumps({
                "subject": podcast['subject'],
                "organizer_email": podcast['organizer_email'],
                "meeting_date": podcast['podcast_date'].isoformat() if podcast['podcast_date'] else None,
                "duration_minutes": podcast['duration_minutes'],
                "participants": podcast['participants'],
                "source_metadata": podcast['source_metadata']
            }),
            podcast['created_at'], podcast['updated_at']
        )

    # 4. Rename video_groups to transcript_groups
    await db.execute("ALTER TABLE video_groups RENAME TO transcript_groups")

    # 5. Verify counts
    old_count = await db.fetchval("SELECT COUNT(*) FROM videos") + \
                await db.fetchval("SELECT COUNT(*) FROM podcasts")
    new_count = await db.fetchval("SELECT COUNT(*) FROM transcripts")

    assert old_count == new_count, f"Migration mismatch: {old_count} vs {new_count}"

    print(f"✅ Migrated {new_count} transcripts successfully")
```

### 4.2 Pinecone Considerations

No Pinecone migration needed—existing `pinecone_file_id` values remain valid. The unified table stores the same reference.

---

## 5. Dashboard Implementation

### 5.1 New TypeScript Types

**File:** `dashboard/soft-ui-chat/src/types/api.ts`

```typescript
export type SourceType = 'youtube' | 'fireflies' | 'zoom' | 'manual' | 'pdf' | 'audio';

export interface Transcript {
  id: string;
  user_id: string;
  group_id: string | null;
  source_type: SourceType;
  external_id: string | null;
  title: string;
  transcript_length: number | null;
  has_summary: boolean;
  summary_generated_at: string | null;
  metadata: YouTubeMetadata | MeetingMetadata | FileMetadata;
  created_at: string;
  updated_at: string;
}

export interface YouTubeMetadata {
  youtube_id: string;
  channel_name: string;
  duration_seconds: number;
  thumbnail_url: string;
}

export interface MeetingMetadata {
  subject?: string;
  organizer_email?: string;
  participants?: string[];
  meeting_date?: string;
  duration_minutes?: number;
}

export interface FileMetadata {
  filename: string;
  file_size_bytes?: number;
  page_count?: number;  // For PDFs
  duration_seconds?: number;  // For audio
}

export interface TranscriptGroup {
  id: string;
  name: string;
  description: string | null;
  color: string;
  transcript_count: number;
  created_at: string;
}
```

### 5.2 Unified Data Hook

**File:** `dashboard/soft-ui-chat/src/hooks/useLibrary.ts`

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

interface UseLibraryOptions {
  groupId?: string | null;
  sourceType?: SourceType | null;
  ungroupedOnly?: boolean;
  sortBy?: 'created_at' | 'title' | 'source_type';
  sortOrder?: 'asc' | 'desc';
}

export function useLibrary(options: UseLibraryOptions = {}) {
  const {
    groupId,
    sourceType,
    ungroupedOnly = false,
    sortBy = 'created_at',
    sortOrder = 'desc'
  } = options;

  return useQuery({
    queryKey: ['library', { groupId, sourceType, ungroupedOnly, sortBy, sortOrder }],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (groupId) params.set('group_id', groupId);
      if (sourceType) params.set('source_type', sourceType);
      if (ungroupedOnly) params.set('ungrouped', 'true');
      params.set('sort_by', sortBy);
      params.set('sort_order', sortOrder);

      const response = await fetch(`/api/transcripts?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      return response.json();
    }
  });
}

export function useMoveTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ transcriptId, groupId }: { transcriptId: string; groupId: string | null }) => {
      await fetch(`/api/transcripts/${transcriptId}/group`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: groupId })
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] });
      queryClient.invalidateQueries({ queryKey: ['groups'] });
    }
  });
}

export function useDeleteTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (transcriptId: string) => {
      await fetch(`/api/transcripts/${transcriptId}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] });
      queryClient.invalidateQueries({ queryKey: ['groups'] });
    }
  });
}
```

### 5.3 Unified Selection Store

**File:** `dashboard/soft-ui-chat/src/hooks/useSelectedTranscript.ts`

```typescript
import { create } from 'zustand';
import { Transcript } from '@/types/api';

interface SelectedTranscriptState {
  selected: Transcript | null;
  setSelected: (transcript: Transcript | null) => void;
}

export const useSelectedTranscript = create<SelectedTranscriptState>((set) => ({
  selected: null,
  setSelected: (transcript) => set({ selected: transcript })
}));
```

### 5.4 New LeftSidebar Structure

**File:** `dashboard/soft-ui-chat/src/components/LeftSidebar.tsx`

Key changes to implement:

```tsx
// Replace separate video/podcast queries with unified library query
const { data: recentTranscripts } = useLibrary({ ungroupedOnly: true });
const { data: groups } = useGroups();

// Remove podcasts section entirely
// Recent section now shows all ungrouped transcripts

// Helper to get source icon
const getSourceIcon = (sourceType: SourceType) => {
  switch (sourceType) {
    case 'youtube': return <Youtube className="h-4 w-4 text-red-500" />;
    case 'fireflies':
    case 'zoom': return <Mic className="h-4 w-4 text-purple-500" />;
    case 'pdf': return <FileText className="h-4 w-4 text-blue-500" />;
    case 'audio': return <AudioLines className="h-4 w-4 text-green-500" />;
    default: return <FileText className="h-4 w-4" />;
  }
};

// Helper to format duration
const formatDuration = (transcript: Transcript) => {
  if (transcript.source_type === 'youtube') {
    const seconds = transcript.metadata.duration_seconds;
    return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, '0')}`;
  }
  if (['fireflies', 'zoom'].includes(transcript.source_type)) {
    return `${transcript.metadata.duration_minutes} min`;
  }
  return null;
};
```

### 5.5 Sorting & Filtering UI

**Minimal UI approach—dropdown in section header:**

```tsx
// Sort dropdown (small, unobtrusive)
<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <Button variant="ghost" size="sm" className="h-6 px-2">
      <ArrowUpDown className="h-3 w-3" />
    </Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent align="end">
    <DropdownMenuLabel>Sort by</DropdownMenuLabel>
    <DropdownMenuItem onClick={() => setSortBy('created_at')}>
      Date added {sortBy === 'created_at' && '✓'}
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => setSortBy('title')}>
      Title {sortBy === 'title' && '✓'}
    </DropdownMenuItem>
    <DropdownMenuSeparator />
    <DropdownMenuLabel>Filter by source</DropdownMenuLabel>
    <DropdownMenuItem onClick={() => setSourceFilter(null)}>
      All sources {!sourceFilter && '✓'}
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => setSourceFilter('youtube')}>
      YouTube only {sourceFilter === 'youtube' && '✓'}
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => setSourceFilter('fireflies')}>
      Meetings only {sourceFilter === 'fireflies' && '✓'}
    </DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

---

## 6. Extension Updates

### 6.1 Background.js Changes

Update API calls to use new unified endpoint:

```javascript
// OLD
const response = await fetch(`${API_BASE_URL}/api/videos`, {
  method: 'POST',
  body: JSON.stringify({
    youtube_id: videoId,
    title: title,
    // ...
  })
});

// NEW
const response = await fetch(`${API_BASE_URL}/api/transcripts`, {
  method: 'POST',
  body: JSON.stringify({
    source_type: 'youtube',
    external_id: videoId,
    title: title,
    transcript_text: transcript,
    metadata: {
      youtube_id: videoId,
      channel_name: channelName,
      duration_seconds: duration,
      thumbnail_url: thumbnailUrl
    }
  })
});
```

---

## 7. Implementation Phases

### Phase 1: Backend Foundation (Days 1-2)
- [ ] Create `transcripts` table with migration script
- [ ] Implement `TranscriptService` with core CRUD
- [ ] Create `/api/transcripts` routes
- [ ] Add sorting and filtering support
- [ ] Run migration on staging database

### Phase 2: Dashboard Update (Days 3-4)
- [ ] Add new TypeScript types
- [ ] Implement `useLibrary` hook
- [ ] Update `useSelectedTranscript` to unified store
- [ ] Refactor `LeftSidebar.tsx` to new structure
- [ ] Remove separate Podcasts section
- [ ] Add source icons and duration formatting
- [ ] Implement sort/filter dropdown

### Phase 3: Integration & Testing (Day 5)
- [ ] Update extension to use new API
- [ ] Test all source types (YouTube, Fireflies, Zoom)
- [ ] Verify RAG search works with migrated data
- [ ] Verify summaries work with migrated data
- [ ] Test grouping operations

### Phase 4: Cleanup & Deploy (Day 6)
- [ ] Add deprecation headers to old endpoints
- [ ] Run migration on production
- [ ] Deploy backend changes
- [ ] Deploy dashboard changes
- [ ] Deploy extension update
- [ ] Monitor for issues

### Phase 5: Future Sources (Post-launch)
- [ ] Add PDF upload endpoint
- [ ] Add audio upload endpoint with transcription
- [ ] Add document parsing support

---

## 8. File Changes Summary

### Backend Files to Create
```
backend/app/models/transcript.py          # New unified models
backend/app/services/transcript_service.py # New unified service
backend/app/routes/transcripts.py         # New unified routes
backend/scripts/migrate_to_unified.py     # Migration script
```

### Backend Files to Modify
```
backend/app/main.py                       # Add new router
backend/app/services/database_service.py  # Add transcripts table model
backend/app/routes/videos.py              # Add deprecation header
backend/app/routes/podcasts.py            # Add deprecation header
```

### Dashboard Files to Create
```
dashboard/soft-ui-chat/src/hooks/useLibrary.ts  # Unified data hook
```

### Dashboard Files to Modify
```
dashboard/soft-ui-chat/src/types/api.ts              # Add Transcript types
dashboard/soft-ui-chat/src/hooks/useSelectedTranscript.ts  # Simplify to unified
dashboard/soft-ui-chat/src/components/LeftSidebar.tsx      # Major refactor
```

### Dashboard Files to Delete (after migration)
```
dashboard/soft-ui-chat/src/hooks/useSelectedPodcast.ts  # Merged into unified
dashboard/soft-ui-chat/src/hooks/usePodcasts.ts         # Merged into useLibrary
```

### Extension Files to Modify
```
extension/background.js           # Update API calls
extension/contents/embedded-popup.js  # Update API calls if any
```

---

## 9. Rollback Plan

If issues arise post-migration:

1. **Database**: Old tables (`videos`, `podcasts`) are preserved—migration script does not delete them
2. **API**: Old endpoints still functional with deprecation headers
3. **Dashboard**: Can revert to previous commit
4. **Pinecone**: No changes made, fully backward compatible

---

## 10. Success Metrics

- [ ] All existing transcripts accessible in new unified view
- [ ] Groups work with mixed content types
- [ ] Recent shows all ungrouped content sorted by date
- [ ] RAG search returns results from all source types
- [ ] Summaries generate correctly for all source types
- [ ] No increase in API error rates
- [ ] No increase in page load times

---

## Appendix A: Visual Mockup

```
┌─────────────────────────────────────────────────────────────────┐
│  ● ● ●  TubeVibe Library                                        │
│         12 transcripts                                          │
├─────────────────────────────────────────────────────────────────┤
│  🏠 Home                                                        │
│  ⚙️ Settings                                                    │
├─────────────────────────────────────────────────────────────────┤
│  📂 LIBRARY                                          [↕ Sort ▾] │
│                                                                 │
│  ▼ 🕐 Recent (5)                                               │
│     │                                                           │
│     ├─ 🎬 How to Build APIs with FastAPI          12:34        │
│     ├─ 🎙️ Weekly Team Standup                     45 min       │
│     ├─ 🎬 React 19 New Features                   28:15        │
│     ├─ 📄 Q4 Strategy Document.pdf                15 pages     │  ← Future
│     └─ 🎵 Customer Interview Recording            1:23:00      │  ← Future
│                                                                 │
│  ▼ 📁 Work Projects (3)                                        │
│     │                                                           │
│     ├─ 🎬 Project Architecture Overview           45:00        │
│     ├─ 🎙️ Sprint Planning Meeting                 30 min       │
│     └─ 🎙️ Client Requirements Call                60 min       │
│                                                                 │
│  ▶ 📁 Learning (4)                                             │
│                                                                 │
│  ▶ 📁 Personal (0)                                             │
│                                                                 │
│  [+ New Group]                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix B: API Response Examples

### List Transcripts Response

```json
{
  "transcripts": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "user-uuid",
      "group_id": null,
      "source_type": "youtube",
      "external_id": "dQw4w9WgXcQ",
      "title": "How to Build APIs with FastAPI",
      "transcript_length": 15420,
      "has_summary": true,
      "summary_generated_at": "2024-01-15T10:30:00Z",
      "metadata": {
        "youtube_id": "dQw4w9WgXcQ",
        "channel_name": "Tech With Tim",
        "duration_seconds": 754,
        "thumbnail_url": "https://i.ytimg.com/vi/..."
      },
      "created_at": "2024-01-15T09:00:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "user_id": "user-uuid",
      "group_id": null,
      "source_type": "fireflies",
      "external_id": "meeting-abc123",
      "title": "Weekly Team Standup",
      "transcript_length": 8200,
      "has_summary": false,
      "summary_generated_at": null,
      "metadata": {
        "subject": "Weekly Standup",
        "organizer_email": "manager@company.com",
        "participants": ["Alice", "Bob", "Charlie"],
        "meeting_date": "2024-01-15T10:00:00Z",
        "duration_minutes": 45
      },
      "created_at": "2024-01-15T11:00:00Z",
      "updated_at": "2024-01-15T11:00:00Z"
    }
  ],
  "total": 12
}
```
