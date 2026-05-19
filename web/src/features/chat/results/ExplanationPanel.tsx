import "./ResultsPanels.css";

interface ExplanationPanelProps {
  text: string;
}

export function ExplanationPanel({ text }: ExplanationPanelProps) {
  return (
    <section className="result-card" aria-label="Explanation">
      <h3 className="result-card-title">Explanation</h3>
      <p className="explanation-body">{text}</p>
    </section>
  );
}
