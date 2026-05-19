import type { ChatMessage } from "../../api/types";
import { MessageBubble } from "./MessageBubble";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: "grid",
          placeItems: "center",
          color: "var(--color-muted)",
          textAlign: "center",
          padding: "32px",
        }}
      >
        <div>
          <p style={{ fontSize: 20, fontWeight: 600, color: "var(--color-text)", marginBottom: 8 }}>
            Start a conversation
          </p>
          <p style={{ maxWidth: 420, margin: 0 }}>Ask your database a clear question in natural language.</p>
        </div>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
