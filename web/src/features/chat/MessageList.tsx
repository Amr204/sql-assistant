import { memo, useEffect, useRef } from "react";
import type { ChatMessage } from "../../api/types";
import { ui } from "../../locale/uiStrings";
import { MessageBubble } from "./MessageBubble";
import "./MessageList.css";

interface MessageListProps {
  messages: ChatMessage[];
  busy?: boolean;
}

export const MessageList = memo(function MessageList({ messages, busy }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastMessageId = messages[messages.length - 1]?.id;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lastMessageId, busy]);

  if (messages.length === 0) {
    return (
      <div className="message-list-empty">
        <p className="message-list-empty-title">{ui.emptyTitle}</p>
        <p className="message-list-empty-hint">{ui.emptyHint}</p>
      </div>
    );
  }

  return (
    <div
      className="message-list"
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      aria-busy={busy || undefined}
      aria-label={ui.chatMessages}
    >
      {busy ? (
        <p className="sr-only" role="status">
          {ui.thinking}
        </p>
      ) : null}
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      <div ref={bottomRef} aria-hidden />
    </div>
  );
});
