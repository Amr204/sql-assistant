import { memo } from "react";
import type { ChatMessage } from "../../api/types";
import { hasDisplayableResults } from "../../api/validate";
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
  const apiErrorCount = message.apiErrors?.length ?? 0;
  const showResults = hasDisplayableResults(message);

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
      {!showResults ? (
        <section className="result-card result-card--warn" role="alert">
          <h3 className="result-card-title">{ui.noSqlResults}</h3>
          <p className="result-summary">{ui.noSqlResultsHint}</p>
        </section>
      ) : null}
      {message.sql ? <GeneratedSqlPanel sql={message.sql} /> : null}
      {message.table ? <ResultsTable table={message.table} /> : null}
      {message.explanation ? <ExplanationPanel text={message.explanation} /> : null}
      {warnCount > 0 ? (
        <ul className="chat-warnings" role="note">
          {message.warnings!.map((w, i) => (
            <li key={`warn-${i}`}>{w}</li>
          ))}
        </ul>
      ) : null}
      {apiErrorCount > 0 ? (
        <ul className="chat-api-errors" role="alert">
          {message.apiErrors!.map((err, i) => (
            <li key={`${err.code}-${i}`}>
              {err.code}: {err.message}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
});
