import { ReactNode } from "react";
import { Trash2, Palette, Edit2 } from "lucide-react";
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

// Type for group data
export interface Group {
  id: string | number;
  name: string;
  color: string;
}

// Predefined color options for groups
const COLOR_OPTIONS = [
  { name: "Blue", value: "bg-blue-500" },
  { name: "Green", value: "bg-green-500" },
  { name: "Purple", value: "bg-purple-500" },
  { name: "Red", value: "bg-red-500" },
  { name: "Amber", value: "bg-amber-500" },
  { name: "Pink", value: "bg-pink-500" },
] as const;

export interface GroupContextMenuProps {
  children: ReactNode;
  group: Group;
  onRename: (groupId: string | number) => void;
  onChangeColor: (groupId: string | number, color: string) => void;
  onDelete: (groupId: string | number) => void;
}

/**
 * Context menu for group items.
 * Provides options to rename, change color, or delete a group.
 */
export function GroupContextMenu({
  children,
  group,
  onRename,
  onChangeColor,
  onDelete,
}: GroupContextMenuProps) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        {/* Rename option */}
        <ContextMenuItem
          className="gap-2 cursor-pointer"
          onClick={() => onRename(group.id)}
        >
          <Edit2 className="w-4 h-4" />
          <span>Rename</span>
        </ContextMenuItem>

        {/* Change Color submenu */}
        <ContextMenuSub>
          <ContextMenuSubTrigger className="gap-2">
            <Palette className="w-4 h-4" />
            <span>Change Color</span>
          </ContextMenuSubTrigger>
          <ContextMenuSubContent className="w-36">
            {COLOR_OPTIONS.map((colorOption) => (
              <ContextMenuItem
                key={colorOption.value}
                className="gap-2 cursor-pointer"
                onClick={() => onChangeColor(group.id, colorOption.value)}
              >
                <div
                  className={`w-3 h-3 rounded-full ${colorOption.value}`}
                  aria-hidden="true"
                />
                <span>{colorOption.name}</span>
              </ContextMenuItem>
            ))}
          </ContextMenuSubContent>
        </ContextMenuSub>

        <ContextMenuSeparator />

        {/* Delete Group option with destructive styling */}
        <ContextMenuItem
          className="gap-2 cursor-pointer text-destructive focus:text-destructive focus:bg-destructive/10"
          onClick={() => onDelete(group.id)}
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete Group</span>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}
