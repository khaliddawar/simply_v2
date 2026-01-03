import { useState, useEffect } from "react";
import { Check } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Available color options for groups.
 * Each color has a display name and Tailwind CSS class.
 */
const COLOR_OPTIONS = [
  { name: "Blue", value: "bg-blue-500" },
  { name: "Green", value: "bg-green-500" },
  { name: "Purple", value: "bg-purple-500" },
  { name: "Amber", value: "bg-amber-500" },
  { name: "Rose", value: "bg-rose-500" },
  { name: "Teal", value: "bg-teal-500" },
] as const;

export interface CreateGroupDialogProps {
  /** Controls dialog visibility */
  open: boolean;
  /** Callback when dialog open state changes */
  onOpenChange: (open: boolean) => void;
  /** Callback when a new group is created with name and color */
  onCreateGroup: (name: string, color: string) => void;
}

/**
 * Dialog component for creating a new group.
 * Allows users to enter a group name and select a color.
 */
export function CreateGroupDialog({
  open,
  onOpenChange,
  onCreateGroup,
}: CreateGroupDialogProps) {
  const [groupName, setGroupName] = useState("");
  const [selectedColor, setSelectedColor] = useState(COLOR_OPTIONS[0].value);
  const [error, setError] = useState("");

  // Reset form state when dialog opens/closes
  useEffect(() => {
    if (open) {
      setGroupName("");
      setSelectedColor(COLOR_OPTIONS[0].value);
      setError("");
    }
  }, [open]);

  /**
   * Handles form submission.
   * Validates that name is not empty before calling onCreateGroup.
   */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedName = groupName.trim();
    if (!trimmedName) {
      setError("Group name is required");
      return;
    }

    onCreateGroup(trimmedName, selectedColor);
    onOpenChange(false);
  };

  /**
   * Handles input change and clears error state.
   */
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setGroupName(e.target.value);
    if (error) {
      setError("");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px] rounded-2xl font-sans">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold">
            Create New Group
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Group Name Input */}
          <div className="space-y-2">
            <Label htmlFor="group-name" className="text-sm font-medium">
              Group Name
            </Label>
            <Input
              id="group-name"
              type="text"
              placeholder="Enter group name..."
              value={groupName}
              onChange={handleNameChange}
              className={cn(
                "rounded-xl",
                error && "border-destructive focus-visible:ring-destructive"
              )}
              autoFocus
            />
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
          </div>

          {/* Color Picker */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">Color</Label>
            <div className="flex items-center gap-3">
              {COLOR_OPTIONS.map((colorOption) => (
                <button
                  key={colorOption.value}
                  type="button"
                  onClick={() => setSelectedColor(colorOption.value)}
                  className={cn(
                    "w-8 h-8 rounded-full transition-all duration-200 flex items-center justify-center",
                    colorOption.value,
                    selectedColor === colorOption.value
                      ? "ring-2 ring-offset-2 ring-offset-background ring-foreground/50 scale-110"
                      : "hover:scale-105 opacity-80 hover:opacity-100"
                  )}
                  title={colorOption.name}
                  aria-label={`Select ${colorOption.name} color`}
                >
                  {selectedColor === colorOption.value && (
                    <Check className="w-4 h-4 text-white" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Dialog Footer with Actions */}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="rounded-xl"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              className="rounded-xl"
            >
              Create Group
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
