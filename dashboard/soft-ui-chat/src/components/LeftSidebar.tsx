import { useState, useEffect } from "react";
import {
  Home,
  Settings,
  FileText,
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  Clock,
  Plus,
  Mic,
  Youtube,
  AudioLines,
} from "lucide-react";
import { useLibrary, useMoveTranscript, useDeleteTranscript } from "@/hooks/useLibrary";
import { useGroups, useCreateGroup, useUpdateGroup, useDeleteGroup } from "@/hooks/useGroups";
import { useSelectedTranscript } from "@/hooks/useSelectedTranscript";
import { useChatStore } from "@/hooks/useChat";
import { CreateGroupDialog } from "./CreateGroupDialog";
import { TranscriptContextMenu } from "./TranscriptContextMenu";
import { GroupContextMenu } from "./GroupContextMenu";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import type { Transcript, SourceType } from "@/types/api";

/**
 * Helper to convert Tailwind color class to hex for API
 * CreateGroupDialog uses Tailwind classes like "bg-blue-500"
 */
const tailwindToHex: Record<string, string> = {
  "bg-blue-500": "#3B82F6",
  "bg-green-500": "#22C55E",
  "bg-purple-500": "#A855F7",
  "bg-amber-500": "#F59E0B",
  "bg-rose-500": "#F43F5E",
  "bg-teal-500": "#14B8A6",
  "bg-red-500": "#EF4444",
  "bg-pink-500": "#EC4899",
};

/**
 * Helper to convert hex color to Tailwind class for display
 * Used for GroupContextMenu which expects Tailwind classes
 */
const hexToTailwind: Record<string, string> = {
  "#3B82F6": "bg-blue-500",
  "#22C55E": "bg-green-500",
  "#A855F7": "bg-purple-500",
  "#F59E0B": "bg-amber-500",
  "#F43F5E": "bg-rose-500",
  "#14B8A6": "bg-teal-500",
  "#EF4444": "bg-red-500",
  "#EC4899": "bg-pink-500",
};

/**
 * Get display-friendly color class from hex
 */
function getColorClass(hexColor: string): string {
  return hexToTailwind[hexColor] || "bg-gray-500";
}

/**
 * Format duration for display based on transcript source type and metadata
 * YouTube videos use seconds, meetings use minutes
 */
function formatTranscriptDuration(transcript: Transcript): string | null {
  const meta = transcript.metadata;

  // YouTube videos have duration in seconds
  if (transcript.source_type === "youtube" && "duration_seconds" in meta) {
    const s = meta.duration_seconds;
    if (!s) return null;
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
  }

  // Meetings (Fireflies, Zoom) have duration in minutes
  if (
    ["fireflies", "zoom"].includes(transcript.source_type) &&
    "duration_minutes" in meta
  ) {
    const mins = meta.duration_minutes;
    if (!mins) return null;
    return `${mins} min`;
  }

  return null;
}

/**
 * Get the appropriate icon for a transcript based on its source type
 */
function getSourceIcon(sourceType: SourceType, isSelected: boolean): React.ReactNode {
  const baseClass = isSelected
    ? "text-foreground"
    : "text-muted-foreground group-hover:text-foreground";

  switch (sourceType) {
    case "youtube":
      return <Youtube className={`w-3.5 h-3.5 ${baseClass}`} />;
    case "fireflies":
    case "zoom":
      return <Mic className={`w-3.5 h-3.5 ${baseClass}`} />;
    case "pdf":
      return <FileText className={`w-3.5 h-3.5 ${baseClass}`} />;
    case "audio":
      return <AudioLines className={`w-3.5 h-3.5 ${baseClass}`} />;
    default:
      return <FileText className={`w-3.5 h-3.5 ${baseClass}`} />;
  }
}

/**
 * Get the subtitle text for a transcript (channel name, subject, etc.)
 */
function getTranscriptSubtitle(transcript: Transcript): string {
  const meta = transcript.metadata;

  if (transcript.source_type === "youtube" && "channel_name" in meta) {
    return meta.channel_name || "Unknown";
  }

  if (
    ["fireflies", "zoom"].includes(transcript.source_type) &&
    "subject" in meta
  ) {
    return meta.subject || transcript.source_type;
  }

  return transcript.source_type;
}

/**
 * Sidebar skeleton component for loading state
 */
function SidebarSkeleton() {
  return (
    <div className="px-2 space-y-3 mt-4">
      <Skeleton className="h-4 w-16 mb-2" />
      {/* Recent section skeleton */}
      <div className="space-y-2">
        <Skeleton className="h-8 w-full rounded-lg" />
        <div className="ml-4 space-y-2">
          <Skeleton className="h-10 w-full rounded-lg" />
          <Skeleton className="h-10 w-full rounded-lg" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      </div>
      {/* Groups skeleton */}
      <div className="space-y-2 mt-4">
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-lg" />
      </div>
    </div>
  );
}

export function LeftSidebar() {
  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);
  const [recentExpanded, setRecentExpanded] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch ALL transcripts (we'll filter client-side for Recent vs Groups)
  const {
    data: allTranscriptsData,
    isLoading: transcriptsLoading,
    error: transcriptsError,
  } = useLibrary({ limit: 500 });  // Fetch all transcripts

  // Fetch groups for sidebar navigation
  const { data: groups = [], isLoading: groupsLoading, error: groupsError } = useGroups();

  // Filter transcripts: ungrouped for Recent section
  const allTranscripts = allTranscriptsData?.transcripts ?? [];
  const recentTranscripts = allTranscripts.filter(t => !t.group_id);
  const totalTranscripts = allTranscriptsData?.total ?? 0;

  // Selected transcript state management (unified - no separate podcast selection)
  const { selectedTranscript, setSelectedTranscript } = useSelectedTranscript();

  // Chat video filter - sync transcript selection with RAG context
  const setVideoFilter = useChatStore((state) => state.setVideoFilter);

  // Auto-select the first (most recent) transcript when data loads
  useEffect(() => {
    if (!transcriptsLoading && allTranscripts.length > 0 && !selectedTranscript) {
      // Transcripts are sorted by most recent first from API
      setSelectedTranscript(allTranscripts[0] as any); // Cast for now until Video type is updated
      setVideoFilter(allTranscripts[0].id);  // Set transcript context for RAG chat
    }
  }, [transcriptsLoading, allTranscripts, selectedTranscript, setSelectedTranscript, setVideoFilter]);

  // Handle transcript selection (unified - works for any source type)
  const handleSelectTranscript = (transcript: Transcript) => {
    console.log('handleSelectTranscript called:', transcript.id, transcript.title);
    setSelectedTranscript(transcript as any); // Cast for now until Video type is updated
    setVideoFilter(transcript.id);  // Set transcript context for RAG chat
    console.log('videoFilter set to:', transcript.id);
  };

  // Check if a transcript is currently selected
  const isSelected = (transcriptId: string): boolean => {
    return selectedTranscript?.id === transcriptId;
  };

  // Mutation hooks for data modifications
  const moveTranscriptMutation = useMoveTranscript();
  const deleteTranscriptMutation = useDeleteTranscript();
  const createGroupMutation = useCreateGroup();
  const updateGroupMutation = useUpdateGroup();
  const deleteGroupMutation = useDeleteGroup();

  // Combined loading state
  const isLoading = transcriptsLoading || groupsLoading;
  const hasError = transcriptsError || groupsError;

  // Get transcripts for a specific group by filtering allTranscripts
  const getGroupTranscripts = (groupId: string): Transcript[] => {
    return allTranscripts.filter(t => t.group_id === groupId);
  };

  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) =>
      prev.includes(groupId)
        ? prev.filter((id) => id !== groupId)
        : [...prev, groupId]
    );
  };

  const handleCreateGroup = (name: string, color: string) => {
    // Convert Tailwind class to hex for API
    const hexColor = tailwindToHex[color] || "#3B82F6";
    createGroupMutation.mutate(
      { name, color: hexColor },
      {
        onSuccess: () => {
          toast.success(`Group "${name}" created`);
        },
        onError: () => {
          toast.error("Failed to create group");
        },
      }
    );
  };

  const handleMoveTranscript = (transcriptId: string | number, groupId: string | number | null) => {
    const id = String(transcriptId);
    const targetGroupId = groupId === null ? null : String(groupId);

    moveTranscriptMutation.mutate(
      { transcriptId: id, groupId: targetGroupId },
      {
        onSuccess: () => {
          const groupName = targetGroupId
            ? groups.find((g) => g.id === targetGroupId)?.name
            : "Recent";
          toast.success(`Moved to ${groupName}`);
        },
        onError: () => {
          toast.error("Failed to move transcript");
        },
      }
    );
  };

  const handleDeleteTranscript = (transcriptId: string | number) => {
    const id = String(transcriptId);
    deleteTranscriptMutation.mutate(id, {
      onSuccess: () => {
        toast.success("Transcript deleted");
      },
      onError: () => {
        toast.error("Failed to delete transcript");
      },
    });
  };

  const handleRenameGroup = (groupId: string | number) => {
    const id = String(groupId);
    const group = groups.find((g) => g.id === id);
    const newName = prompt("Enter new name:", group?.name);
    if (newName && newName.trim()) {
      updateGroupMutation.mutate(
        { id, name: newName.trim() },
        {
          onSuccess: () => {
            toast.success("Group renamed");
          },
          onError: () => {
            toast.error("Failed to rename group");
          },
        }
      );
    }
  };

  const handleChangeGroupColor = (groupId: string | number, color: string) => {
    const id = String(groupId);
    // Convert Tailwind class to hex for API
    const hexColor = tailwindToHex[color] || "#3B82F6";
    updateGroupMutation.mutate(
      { id, color: hexColor },
      {
        onSuccess: () => {
          toast.success("Group color updated");
        },
        onError: () => {
          toast.error("Failed to update group color");
        },
      }
    );
  };

  const handleDeleteGroup = (groupId: string | number) => {
    const id = String(groupId);
    const group = groups.find((g) => g.id === id);
    if (confirm(`Delete group "${group?.name}"? Transcripts will be moved to Recent.`)) {
      deleteGroupMutation.mutate(id, {
        onSuccess: () => {
          toast.success("Group deleted");
        },
        onError: () => {
          toast.error("Failed to delete group");
        },
      });
    }
  };

  return (
    <aside className="w-60 h-full shrink-0 bg-card border-r border-border/50 flex flex-col overflow-hidden rounded-l-2xl">
      {/* Header */}
      <div className="p-3 flex items-center gap-2">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-rose-400" />
          <div className="w-3 h-3 rounded-full bg-amber-400" />
          <div className="w-3 h-3 rounded-full bg-green-400" />
        </div>
        <span className="text-xs text-muted-foreground ml-2">
          {isLoading ? "Loading..." : `${totalTranscripts} transcripts`}
        </span>
      </div>

      {/* Navigation */}
      <nav className="px-2 space-y-0.5">
        <div className="sidebar-item sidebar-item-active">
          <Home className="w-4 h-4" />
          <span className="font-medium text-foreground text-sm">Home</span>
        </div>
        <div className="sidebar-item">
          <Settings className="w-4 h-4" />
          <span className="text-sm">Settings</span>
        </div>
      </nav>

      {/* Universe Section */}
      <div className="px-2 mt-4 flex-1 overflow-y-auto scrollbar-hide">
        <h3 className="text-xs font-normal text-muted-foreground mb-2 px-1">
          Universe
        </h3>

        {/* Loading skeleton */}
        {isLoading && <SidebarSkeleton />}

        {/* Error state */}
        {hasError && !isLoading && (
          <div className="px-3 py-4 text-center">
            <p className="text-sm text-destructive">Failed to load data</p>
            <button
              onClick={() => window.location.reload()}
              className="text-xs text-muted-foreground hover:text-foreground mt-2 underline"
            >
              Retry
            </button>
          </div>
        )}

        {/* Content when loaded */}
        {!isLoading && !hasError && (
          <>
            {/* Recent Transcripts */}
            <div className="mb-2">
              <button
                onClick={() => setRecentExpanded(!recentExpanded)}
                className="sidebar-item w-full justify-between py-1.5"
              >
                <div className="flex items-center gap-3">
                  <Clock className="w-4 h-4 text-accent-amber" />
                  <span className="text-sm font-medium">Recent</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {recentTranscripts.length}
                  </span>
                  {recentExpanded ? (
                    <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                  )}
                </div>
              </button>
              {recentExpanded && (
                <div className="ml-4 mt-1 space-y-0.5">
                  {recentTranscripts.length === 0 ? (
                    <p className="text-xxs text-muted-foreground px-3 py-2 italic">
                      No transcripts
                    </p>
                  ) : (
                    recentTranscripts.map((transcript) => (
                      <TranscriptContextMenu
                        key={transcript.id}
                        transcript={{
                          id: transcript.id,
                          title: transcript.title,
                          groupId: transcript.group_id,
                        }}
                        groups={groups.map((g) => ({
                          id: g.id,
                          name: g.name,
                          color: getColorClass(g.color),
                        }))}
                        onMove={handleMoveTranscript}
                        onDelete={handleDeleteTranscript}
                      >
                        <div
                          onClick={() => handleSelectTranscript(transcript)}
                          className={`sidebar-item py-1.5 group cursor-pointer ${
                            isSelected(transcript.id)
                              ? "bg-accent/50 text-accent-foreground"
                              : ""
                          }`}
                        >
                          {getSourceIcon(transcript.source_type, isSelected(transcript.id))}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm truncate">{transcript.title}</p>
                            <p className="text-xxs text-muted-foreground truncate">
                              {getTranscriptSubtitle(transcript)}
                              {formatTranscriptDuration(transcript) && ` · ${formatTranscriptDuration(transcript)}`}
                            </p>
                          </div>
                        </div>
                      </TranscriptContextMenu>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* Groups */}
            <div className="space-y-1">
              {groups.map((group) => {
                const isExpanded = expandedGroups.includes(group.id);
                const colorClass = getColorClass(group.color);
                const groupTranscripts = getGroupTranscripts(group.id);

                return (
                  <div key={group.id}>
                    <GroupContextMenu
                      group={{
                        id: group.id,
                        name: group.name,
                        color: colorClass,
                      }}
                      onRename={handleRenameGroup}
                      onChangeColor={handleChangeGroupColor}
                      onDelete={handleDeleteGroup}
                    >
                      <button
                        onClick={() => toggleGroup(group.id)}
                        className="sidebar-item w-full justify-between py-1.5"
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: group.color }}
                          />
                          {isExpanded ? (
                            <FolderOpen className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <Folder className="w-4 h-4 text-muted-foreground" />
                          )}
                          <span className="text-sm font-medium">{group.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">
                            {group.video_count}
                          </span>
                          {isExpanded ? (
                            <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                          )}
                        </div>
                      </button>
                    </GroupContextMenu>
                    {isExpanded && (
                      <div className="ml-6 mt-1 space-y-0.5">
                        {groupTranscripts.map((transcript) => (
                          <TranscriptContextMenu
                            key={transcript.id}
                            transcript={{
                              id: transcript.id,
                              title: transcript.title,
                              groupId: transcript.group_id,
                            }}
                            groups={groups.map((g) => ({
                              id: g.id,
                              name: g.name,
                              color: getColorClass(g.color),
                            }))}
                            onMove={handleMoveTranscript}
                            onDelete={handleDeleteTranscript}
                          >
                            <div
                              onClick={() => handleSelectTranscript(transcript)}
                              className={`sidebar-item py-1.5 group cursor-pointer ${
                                isSelected(transcript.id)
                                  ? "bg-accent/50 text-accent-foreground"
                                  : ""
                              }`}
                            >
                              {getSourceIcon(transcript.source_type, isSelected(transcript.id))}
                              <div className="flex-1 min-w-0">
                                <p className="text-sm truncate">{transcript.title}</p>
                                <p className="text-xxs text-muted-foreground">
                                  {getTranscriptSubtitle(transcript)}
                                  {formatTranscriptDuration(transcript) && ` · ${formatTranscriptDuration(transcript)}`}
                                </p>
                              </div>
                            </div>
                          </TranscriptContextMenu>
                        ))}
                        {groupTranscripts.length === 0 && (
                          <p className="text-xxs text-muted-foreground px-3 py-2 italic">
                            No transcripts
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* New Group Button */}
            <button
              onClick={() => setCreateDialogOpen(true)}
              className="sidebar-item w-full py-2 mt-2 text-muted-foreground hover:text-foreground"
            >
              <Plus className="w-4 h-4" />
              <span className="text-sm">New Group</span>
            </button>
          </>
        )}
      </div>

      {/* Create Group Dialog */}
      <CreateGroupDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreateGroup={handleCreateGroup}
      />
    </aside>
  );
}
