import type { HTMLAttributes } from "react";
import "./Badge.css";

type Tone = "neutral" | "ok" | "warn" | "err";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className = "", ...rest }: BadgeProps) {
  const toneCls =
    tone === "ok" ? "badge-ok" : tone === "warn" ? "badge-warn" : tone === "err" ? "badge-err" : "";
  return <span className={`badge ${toneCls} ${className}`.trim()} {...rest} />;
}
