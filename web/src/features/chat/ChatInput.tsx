import { Send } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Textarea } from "../../components/ui/Textarea";
import "./ChatInput.css";

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}

export function ChatInput({ value, onChange, onSubmit, disabled }: ChatInputProps) {
  return (
    <div className="composer">
      <div className="composer-row">
        <Textarea
          rows={3}
          placeholder="Ask your database…"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!disabled && value.trim()) {
                onSubmit();
              }
            }
          }}
        />
        <Button type="button" disabled={disabled || !value.trim()} onClick={onSubmit}>
          <Send size={18} aria-hidden />
          Send
        </Button>
      </div>
    </div>
  );
}
