import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import type { ChatMessage } from "../../api/types";
import { ui } from "../../locale/uiStrings";
import "./ChatPage.css";

interface ChatPageProps {
  messages: ChatMessage[];
  draft: string;
  onDraftChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  error: string | null;
}

function ThinkingIndicator() {
  return (
    <div className="thinking-indicator">
      <div className="thinking-dots" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <span>{ui.thinking}</span>
    </div>
  );
}

export function ChatPage({ messages, draft, onDraftChange, onSend, busy, error }: ChatPageProps) {
  return (
    <div className="chat-page">
      <div className="chat-scroll">
        <MessageList messages={messages} busy={busy} />
      </div>
      {error && <div className="text-error chat-error">{error}</div>}
      {busy && <ThinkingIndicator />}
      <ChatInput value={draft} onChange={onDraftChange} onSubmit={onSend} disabled={busy} />
    </div>
  );
}
