import { useEffect } from "react";
import { LeftSidebar } from "@/components/LeftSidebar";
import { ChatFeed } from "@/components/ChatFeed";
import { RightPanel } from "@/components/RightPanel";
import { LoginDialog } from "@/components/LoginDialog";
import { useAuth } from "@/hooks/useAuth";

/**
 * Loading spinner component
 */
function LoadingScreen() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#e0e5ec]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    </div>
  );
}

/**
 * Main Index page component
 *
 * Features:
 * - Authentication check on mount
 * - Shows LoginDialog if not authenticated
 * - Shows loading state while checking auth
 * - Main dashboard layout with sidebar, chat feed, and right panel
 */
const Index = () => {
  const { isAuthenticated, isLoading, token, fetchUser } = useAuth();

  // Check authentication status on mount
  useEffect(() => {
    if (token && !isAuthenticated) {
      fetchUser();
    }
  }, [token, isAuthenticated, fetchUser]);

  // Show loading while checking auth
  if (token && isLoading) {
    return <LoadingScreen />;
  }

  // Show login dialog if not authenticated
  if (!isAuthenticated) {
    return <LoginDialog />;
  }

  // Main dashboard layout
  return (
    <>
      {/* SEO Meta Tags */}
      <title>TubeVibe - Video Transcript Library</title>
      <meta
        name="description"
        content="Search and organize your YouTube video transcripts with AI-powered knowledge search."
      />

      <div className="flex h-full w-full bg-background overflow-hidden rounded-2xl shadow-2xl border border-black/5">
        <LeftSidebar />
        <ChatFeed />
        <RightPanel />
      </div>
    </>
  );
};

export default Index;
