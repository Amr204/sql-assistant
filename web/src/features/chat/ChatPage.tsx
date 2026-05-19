import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import type { ChatMessage } from "../../api/types";

interface ChatPageProps {
  messages: ChatMessage[];
  draft: string;
  onDraftChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  error: string | null;
}

export function ChatPage({
  messages,
  draft,
  onDraftChange,
  onSend,
  busy,
  error,
}: ChatPageProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
        maxHeight: "100%",
      }}
    >
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        <MessageList messages={messages} />
      </div>
      {error && (
        <div
          style={{
            color: "var(--color-danger)",
            fontSize: 14,
            marginBottom: 8,
          }}
        >
          {error}
        </div>
      )}
      {busy && (
        <div style={{ fontSize: 14, color: "var(--color-muted)", marginBottom: 8 }}>Thinking…</div>
      )}
      <ChatInput value={draft} onChange={onDraftChange} onSubmit={onSend} disabled={busy} />
    </div>
  );
}
