import React from "react";
import { ui } from "../locale/uiStrings";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("ErrorBoundary caught:", error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      const showDetail = import.meta.env.DEV && this.state.error?.message;
      return (
        this.props.fallback ?? (
          <div style={{ padding: 24, textAlign: "center" }} role="alert">
            <h2>{ui.errorUnexpected}</h2>
            <p>{showDetail ? this.state.error!.message : ui.errorGeneric}</p>
            <button
              type="button"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
            >
              {ui.reload}
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
