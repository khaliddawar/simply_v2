/**
 * User Profile Dropdown Component
 *
 * Displays the authenticated user's avatar and provides
 * a dropdown menu with user info and logout option.
 */
import { LogOut, User, Crown, Sparkles } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { PlanType } from "@/types/api";

/**
 * Get user initials from name or email
 */
function getUserInitials(firstName?: string | null, lastName?: string | null, email?: string): string {
  if (firstName && lastName) {
    return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
  }
  if (firstName) {
    return firstName.charAt(0).toUpperCase();
  }
  if (email) {
    return email.charAt(0).toUpperCase();
  }
  return "U";
}

/**
 * Get display name from user data
 */
function getDisplayName(firstName?: string | null, lastName?: string | null, email?: string): string {
  if (firstName && lastName) {
    return `${firstName} ${lastName}`;
  }
  if (firstName) {
    return firstName;
  }
  return email || "User";
}

/**
 * Plan badge configuration
 */
const planConfig: Record<PlanType, { label: string; className: string; icon: typeof Crown }> = {
  free: {
    label: "Free",
    className: "bg-muted text-muted-foreground",
    icon: User,
  },
  premium: {
    label: "Premium",
    className: "bg-accent-purple/10 text-accent-purple",
    icon: Crown,
  },
  enterprise: {
    label: "Enterprise",
    className: "bg-amber-500/10 text-amber-600",
    icon: Sparkles,
  },
};

/**
 * User Profile Dropdown
 *
 * Shows avatar with user initials, clicking opens dropdown with:
 * - User name and email
 * - Plan badge
 * - Logout option
 */
export function UserProfileDropdown() {
  const { user, logout } = useAuth();

  if (!user) {
    return null;
  }

  const initials = getUserInitials(user.first_name, user.last_name, user.email);
  const displayName = getDisplayName(user.first_name, user.last_name, user.email);
  const planInfo = planConfig[user.plan_type] || planConfig.free;
  const PlanIcon = planInfo.icon;

  const handleLogout = () => {
    logout();
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex items-center gap-2 rounded-full hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-accent-purple focus:ring-offset-2"
          aria-label="User menu"
        >
          <Avatar className="h-8 w-8 cursor-pointer">
            <AvatarFallback className="bg-accent-purple text-white text-xs font-medium">
              {initials}
            </AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {/* User info section */}
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">{displayName}</p>
            <p className="text-xs leading-none text-muted-foreground truncate">
              {user.email}
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {/* Plan badge */}
        <div className="px-2 py-1.5">
          <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${planInfo.className}`}>
            <PlanIcon className="h-3 w-3" />
            {planInfo.label} Plan
          </div>
        </div>
        <DropdownMenuSeparator />

        {/* Logout */}
        <DropdownMenuItem
          onClick={handleLogout}
          className="text-destructive focus:text-destructive cursor-pointer"
        >
          <LogOut className="mr-2 h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
