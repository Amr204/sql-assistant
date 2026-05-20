import { ui } from "../../locale/uiStrings";
import "./Spinner.css";

export function Spinner() {
  return (
    <div role="status" aria-label={ui.loading}>
      <div className="spinner" />
      <span className="sr-only">{ui.loading}</span>
    </div>
  );
}
