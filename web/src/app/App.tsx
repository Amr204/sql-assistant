import { useCallback, useEffect, useState } from "react";
import { sendChatMessage } from "../api/chat";
import { ApiError } from "../api/client";
import { fetchProfile } from "../api/profile";
import { fetchStatus } from "../api/status";
import { fetchTools } from "../api/tools";
import type { ChatMessage, ProfileResponse, StatusResponse, ToolDescriptor } from "../api/types";
import { AppShell } from "../components/layout/AppShell";
import { Sidebar } from "../components/layout/Sidebar";
import { TopBar } from "../components/layout/TopBar";
import { ChatPage } from "../features/chat/ChatPage";
import { ReadinessPanel } from "../features/diagnostics/ReadinessPanel";
import { ToolsDrawer } from "../features/tools/ToolsDrawer";

export function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [tools, setTools] = useState<ToolDescriptor[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetchStatus();
        if (!cancelled) {
          setStatus(s);
        }
      } catch (e) {
        if (!cancelled) {
          setStatusError(e instanceof ApiError ? e.message : "Status request failed");
        }
      }
      try {
        const p = await fetchProfile();
        if (!cancelled) {
          setProfile(p);
        }
      } catch (e) {
        if (!cancelled) {
          setProfileError(e instanceof ApiError ? e.message : "Profile request failed");
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
          setToolsError(e instanceof ApiError ? e.message : "Tools request failed");
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
    setMessages([]);
    setConversationId(null);
    setDraft("");
    setChatError(null);
  }, []);

  const onSend = useCallback(async () => {
    const q = draft.trim();
    if (!q || busy) {
      return;
    }
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: q,
    };
    setMessages((m) => [...m, userMsg]);
    setDraft("");
    setBusy(true);
    setChatError(null);
    try {
      const res = await sendChatMessage({
        question: q,
        conversation_id: conversationId,
      });
      setConversationId(res.conversation_id);
      const assistant: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.answer || "(No text reply)",
        sql: res.sql,
        table: res.table,
        explanation: res.explanation ?? undefined,
        confidence: res.confidence ?? undefined,
        execution_ms: res.execution_ms ?? undefined,
        warnings: res.warnings,
        path: res.path ?? undefined,
        timings: res.timings ?? undefined,
      };
      setMessages((m) => [...m, assistant]);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.payload === "object" && e.payload && "detail" in (e.payload as object)
            ? JSON.stringify((e.payload as { detail: unknown }).detail)
            : e.message
          : "Request failed";
      setChatError(msg);
    } finally {
      setBusy(false);
    }
  }, [busy, conversationId, draft]);

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
        children={
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 24,
              maxWidth: 960,
              flex: 1,
              minHeight: 0,
            }}
          >
            <ChatPage
              messages={messages}
              draft={draft}
              onDraftChange={setDraft}
              onSend={() => void onSend()}
              busy={busy}
              error={chatError}
            />
            <ReadinessPanel status={status} />
          </div>
        }
      />
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
