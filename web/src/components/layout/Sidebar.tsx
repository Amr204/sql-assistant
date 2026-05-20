import { Database, Wrench } from "lucide-react";
import type { ProfileResponse } from "../../api/types";
import { ProfileCard } from "../../features/profile/ProfileCard";
import { ui } from "../../locale/uiStrings";
import { Button } from "../ui/Button";
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
        <div className="sidebar-brand">{ui.appTitle}</div>
        <div className="sidebar-nav">
          <Button type="button" onClick={onNewChat}>
            {ui.newChat}
          </Button>
          <Button type="button" variant="ghost" onClick={onOpenTools}>
            <Wrench size={16} aria-hidden />
            {ui.tools}
          </Button>
        </div>
      </div>
      <ProfileCard profile={profile} error={profileError} />
      <div className="sidebar-muted">
        <Database size={14} className="sidebar-muted-icon" aria-hidden />
        {ui.profileTagline}
      </div>
    </>
  );
}
