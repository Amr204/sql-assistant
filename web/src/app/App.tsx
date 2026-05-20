import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { fetchProfile } from "../api/profile";
import { fetchStatus } from "../api/status";
import { fetchTools } from "../api/tools";
import type { ProfileResponse, StatusResponse, ToolDescriptor } from "../api/types";
import { AppShell } from "../components/layout/AppShell";
import { Sidebar } from "../components/layout/Sidebar";
import { TopBar } from "../components/layout/TopBar";
import { ChatPage } from "../features/chat/ChatPage";
import { ReadinessPanel } from "../features/diagnostics/ReadinessPanel";
import { ToolsDrawer } from "../features/tools/ToolsDrawer";
import { useChat } from "../hooks/useChat";
import { withStartupRetry } from "../lib/fetchRetry";
import { ui } from "../locale/uiStrings";

export function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [tools, setTools] = useState<ToolDescriptor[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const { messages, busy, error: chatError, send, clear } = useChat();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const s = await withStartupRetry(() => fetchStatus());
        if (!cancelled) {
          setStatus(s);
        }
      } catch (e) {
        if (!cancelled) {
          setStatusError(e instanceof ApiError ? e.message : ui.statusFailed);
        }
      }
      try {
        const p = await withStartupRetry(() => fetchProfile());
        if (!cancelled) {
          setProfile(p);
        }
      } catch (e) {
        if (!cancelled) {
          setProfileError(e instanceof ApiError ? e.message : ui.profileFailed);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!toolsOpen) {
      return;
    }
    let cancelled = false;
    setToolsLoading(true);
    setToolsError(null);
    void (async () => {
      try {
        const res = await fetchTools();
        if (!cancelled) {
          setTools(res.tools);
        }
      } catch (e) {
        if (!cancelled) {
          setToolsError(e instanceof ApiError ? e.message : ui.toolsFailed);
        }
      } finally {
        if (!cancelled) {
          setToolsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toolsOpen]);

  const onNewChat = useCallback(() => {
    clear();
    setDraft("");
  }, [clear]);

  const onSend = useCallback(() => {
    const q = draft.trim();
    if (!q) {
      return;
    }
    setDraft("");
    void send(q);
  }, [draft, send]);

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            profile={profile}
            profileError={profileError}
            onNewChat={onNewChat}
            onOpenTools={() => setToolsOpen(true)}
          />
        }
        topbar={<TopBar status={status} statusError={statusError} />}
      >
        <div className="app-main-column">
          <ChatPage
            messages={messages}
            draft={draft}
            onDraftChange={setDraft}
            onSend={onSend}
            busy={busy}
            error={chatError}
          />
          <ReadinessPanel status={status} />
        </div>
      </AppShell>
      <ToolsDrawer
        open={toolsOpen}
        onClose={() => setToolsOpen(false)}
        tools={tools}
        loading={toolsLoading}
        error={toolsError}
      />
    </>
  );
}
