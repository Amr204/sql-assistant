import { memo } from "react";
import { ui } from "../../../locale/uiStrings";
import "./ResultsPanels.css";

interface ExplanationPanelProps {
  text: string;
}

export const ExplanationPanel = memo(function ExplanationPanel({ text }: ExplanationPanelProps) {
  return (
    <section className="result-card" aria-label={ui.explanation}>
      <h3 className="result-card-title">{ui.explanation}</h3>
      <p className="explanation-body">{text}</p>
    </section>
  );
});
