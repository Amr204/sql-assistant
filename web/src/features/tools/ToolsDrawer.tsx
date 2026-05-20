import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import type { ToolDescriptor } from "../../api/types";
import { ui } from "../../locale/uiStrings";
import "./ToolsDrawer.css";

interface ToolsDrawerProps {
  open: boolean;
  onClose: () => void;
  tools: ToolDescriptor[];
  loading: boolean;
  error: string | null;
}

export function ToolsDrawer({ open, onClose, tools, loading, error }: ToolsDrawerProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="drawer-head">
          <h2 id={titleId} className="drawer-title">
            {ui.tools}
          </h2>
          <Button type="button" variant="ghost" onClick={onClose} aria-label={ui.closeTools}>
            <X size={18} aria-hidden />
          </Button>
        </div>
        {loading && <Spinner />}
        {error && (
          <p className="text-error" role="alert">
            {error}
          </p>
        )}
        {!loading && !error && (
          <ul className="tool-list" aria-label={ui.tools}>
            {tools.map((t) => (
              <li key={t.name} className="tool-row">
                <div className="tool-name">{t.name}</div>
                <div className="tool-desc">{t.description}</div>
                <div className="tool-groups">
                  {ui.toolsAccess} {t.access_groups.join(", ") || "—"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
