import type { TextareaHTMLAttributes } from "react";
import "./Textarea.css";

export function Textarea({ className = "", ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`ta ${className}`.trim()} {...rest} />;
}
