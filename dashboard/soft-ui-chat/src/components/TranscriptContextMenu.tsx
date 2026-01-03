import { ReactNode } from "react";
import { Trash2, FolderInput, FolderMinus } from "lucide-react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";

// Types for transcript and group data
export interface Transcript {
  id: string | number;
  title: string;
  groupId: string | number | null;
}

export interface Group {
  id: string | number;
  name: string;
  color: string;
}

export interface TranscriptContextMenuProps {
  children: ReactNode;
  transcript: Transcript;
  groups: Group[];
  onMove: (transcriptId: string | number, groupId: string | number) => void;
  onDelete: (transcriptId: string | number) => void;
}

/**
 * Context menu for transcript items.
 * Provides options to move transcript to a group, remove from group, or delete.
 */
export function TranscriptContextMenu({
  children,
  transcript,
  groups,
  onMove,
  onDelete,
}: TranscriptContextMenuProps) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        {/* Move to Group submenu */}
        <ContextMenuSub>
          <ContextMenuSubTrigger className="gap-2">
            <FolderInput className="w-4 h-4" />
            <span>Move to Group</span>
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="w-44">
            {groups.length > 0 ? (
              groups.map((group) => (
                <ContextMenuItem
                  key={group.id}
                  className="gap-2 cursor-pointer"
                  onClick={() => onMove(transcript.id, group.id)}
                >
                  <div
                    className={`w-2.5 h-2.5 rounded-full ${group.color}`}
                    aria-hidden="true"
                  />
                  <span className="truncate">{group.name}</span>
                </ContextMenuItem>
              ))
            ) : (
              <ContextMenuItem disabled className="text-muted-foreground">
                No groups available
              </ContextMenuItem>
            )}
          </ContextMenuSubContent>
        </ContextMenuSub>

        {/* Remove from Group - only shown if transcript is in a group */}
        {transcript.groupId !== null && (
          <ContextMenuItem
            className="gap-2 cursor-pointer"
            onClick={() => onMove(transcript.id, null as unknown as string | number)}
          >
            <FolderMinus className="w-4 h-4" />
            <span>Remove from Group</span>
          </ContextMenuItem>
        )}

        <ContextMenuSeparator />

        {/* Delete option with destructive styling */}
        <ContextMenuItem
          className="gap-2 cursor-pointer text-destructive focus:text-destructive focus:bg-destructive/10"
          onClick={() => onDelete(transcript.id)}
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete</span>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}
