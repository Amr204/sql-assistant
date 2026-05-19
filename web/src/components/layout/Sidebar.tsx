import { Database, Wrench } from "lucide-react";
import type { ProfileResponse } from "../../api/types";
import { Button } from "../ui/Button";
import { ProfileCard } from "../../features/profile/ProfileCard";
import "./Sidebar.css";

interface SidebarProps {
  profile: ProfileResponse | null;
  profileError: string | null;
  onNewChat: () => void;
  onOpenTools: () => void;
}

export function Sidebar({ profile, profileError, onNewChat, onOpenTools }: SidebarProps) {
  return (
    <>
      <div>
        <div className="sidebar-brand">SQL Assistant</div>
        <div className="sidebar-nav">
          <Button type="button" onClick={onNewChat}>
            New Chat
          </Button>
          <Button type="button" variant="ghost" onClick={onOpenTools}>
            <Wrench size={16} aria-hidden />
            Tools
          </Button>
        </div>
      </div>
      <ProfileCard profile={profile} error={profileError} />
      <div className="sidebar-muted">
        <Database size={14} style={{ verticalAlign: "text-top", marginRight: 6 }} aria-hidden />
        Profile-driven answers
      </div>
    </>
  );
}
