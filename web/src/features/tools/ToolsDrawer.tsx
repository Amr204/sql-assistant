import { X } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import type { ToolDescriptor } from "../../api/types";
import "./ToolsDrawer.css";

interface ToolsDrawerProps {
  open: boolean;
  onClose: () => void;
  tools: ToolDescriptor[];
  loading: boolean;
  error: string | null;
}

export function ToolsDrawer({ open, onClose, tools, loading, error }: ToolsDrawerProps) {
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
      <aside className="drawer-panel" role="dialog" aria-label="Tools">
        <div className="drawer-head">
          <h2 style={{ margin: 0, fontSize: 21, fontWeight: 600 }}>Tools</h2>
          <Button type="button" variant="ghost" onClick={onClose} aria-label="Close tools">
            <X size={18} />
          </Button>
        </div>
        {loading && <Spinner />}
        {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
        {!loading &&
          !error &&
          tools.map((t) => (
            <div key={t.name} className="tool-row">
              <div className="tool-name">{t.name}</div>
              <div className="tool-desc">{t.description}</div>
              <div className="tool-groups">Access: {t.access_groups.join(", ") || "—"}</div>
            </div>
          ))}
      </aside>
    </div>
  );
}
