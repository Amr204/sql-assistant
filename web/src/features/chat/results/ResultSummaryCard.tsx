import "./ResultsPanels.css";

interface ResultSummaryCardProps {
  answer: string;
}

export function ResultSummaryCard({ answer }: ResultSummaryCardProps) {
  return (
    <section className="result-card" aria-label="Answer summary">
      <h3 className="result-card-title">Summary</h3>
      <p className="result-summary">{answer}</p>
    </section>
  );
}
