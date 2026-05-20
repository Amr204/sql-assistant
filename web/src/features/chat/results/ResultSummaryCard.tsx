import { memo } from "react";
import { ui } from "../../../locale/uiStrings";
import "./ResultsPanels.css";

interface ResultSummaryCardProps {
  answer: string;
}

export const ResultSummaryCard = memo(function ResultSummaryCard({ answer }: ResultSummaryCardProps) {
  return (
    <section className="result-card" aria-label={ui.summary}>
      <h3 className="result-card-title">{ui.summary}</h3>
      <p className="result-summary">{answer}</p>
    </section>
  );
});
