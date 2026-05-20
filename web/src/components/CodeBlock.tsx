import Prism from "prismjs";
import "prismjs/components/prism-sql";
import "prismjs/themes/prism-tomorrow.css";
import { memo, useMemo } from "react";
import { ui } from "../locale/uiStrings";
import { sanitizePrismHtml } from "./sanitizePrismHtml";
import "./CodeBlock.css";

interface Props {
  code: string;
  language?: string;
}

export const CodeBlock = memo(function CodeBlock({ code, language = "sql" }: Props) {
  const highlighted = useMemo(() => {
    try {
      const grammar = Prism.languages[language] ?? Prism.languages.sql;
      return sanitizePrismHtml(Prism.highlight(code, grammar, language));
    } catch {
      return sanitizePrismHtml(
        code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
      );
    }
  }, [code, language]);

  return (
    <div className="code-block">
      <pre>
        <code dangerouslySetInnerHTML={{ __html: highlighted }} />
      </pre>
      <button
        type="button"
        className="copy-btn"
        onClick={() => void navigator.clipboard.writeText(code)}
        title={ui.copy}
        aria-label={ui.copy}
      >
        📋
      </button>
    </div>
  );
});
