import { useEffect, useState } from "react";
import { ui } from "../../locale/uiStrings";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      return saved;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      title={theme === "dark" ? ui.themeLight : ui.themeDark}
      aria-label={theme === "dark" ? ui.themeLight : ui.themeDark}
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
