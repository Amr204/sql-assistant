import { memo } from "react";
import type { ChatMessage } from "../../api/types";
import { ui } from "../../locale/uiStrings";
import { ExplanationPanel } from "./results/ExplanationPanel";
import { GeneratedSqlPanel } from "./results/GeneratedSqlPanel";
import { ResultSummaryCard } from "./results/ResultSummaryCard";
import { ResultsTable } from "./results/ResultsTable";
import { StatusBadge } from "./results/StatusBadge";
import "./MessageBubble.css";

interface MessageBubbleProps {
  message: ChatMessage;
}

export const MessageBubble = memo(function MessageBubble({ message }: MessageBubbleProps) {
  const cls = message.role === "user" ? "bubble bubble-user" : "bubble bubble-assistant";
  const label = message.role === "user" ? ui.you : ui.assistant;
  const timeLabel =
    message.timestamp != null
      ? new Date(message.timestamp).toLocaleTimeString("ar-SA", {
          hour: "2-digit",
          minute: "2-digit",
        })
      : null;

  if (message.role === "user") {
    return (
      <article className={cls}>
        <div className="bubble-meta">
          <span>{label}</span>
          {timeLabel ? (
            <time dateTime={new Date(message.timestamp!).toISOString()}>{timeLabel}</time>
          ) : null}
        </div>
        <div className="bubble-content">{message.content}</div>
      </article>
    );
  }

  const warnCount = message.warnings?.length ?? 0;

  return (
    <article className={cls}>
      <div className="bubble-meta">
        <span>{label}</span>
        {timeLabel ? (
          <time dateTime={new Date(message.timestamp!).toISOString()}>{timeLabel}</time>
        ) : null}
      </div>
      <StatusBadge
        executionMs={message.execution_ms}
        confidence={message.confidence}
        warningCount={warnCount}
        path={message.path}
        timings={message.timings}
      />
      <ResultSummaryCard answer={message.content} />
      {message.sql ? <GeneratedSqlPanel sql={message.sql} /> : null}
      {message.table ? <ResultsTable table={message.table} /> : null}
      {message.explanation ? <ExplanationPanel text={message.explanation} /> : null}
    </article>
  );
});
