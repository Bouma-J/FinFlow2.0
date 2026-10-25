import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "@/components/ui";

type Props = { children: ReactNode };
type State = { hasError: boolean; message: string };

/**
 * Filet de sécurité UI : une exception React n'écrase plus toute l'app.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error?.message || "Une erreur inattendue est survenue.",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="page-shell" style={{ paddingTop: 48 }}>
          <ErrorState
            message={this.state.message}
            onRetry={() => {
              this.setState({ hasError: false, message: "" });
              window.location.reload();
            }}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
