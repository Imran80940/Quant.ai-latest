import React from 'react';

/**
 * Wraps a component subtree so a render-time exception only kills that
 * component, not the whole page. Used around Chart, Screener, AI panels
 * so a single breakage never produces a white screen.
 */
interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  label?: string;
}
interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error(`[ErrorBoundary${this.props.label ? ' ' + this.props.label : ''}]`, error, info);
  }
  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="panel rounded-md p-4 text-xs leading-snug">
          <div style={{ color: 'var(--red)' }} className="font-semibold mb-1">
            {this.props.label ? `${this.props.label} crashed` : 'Component crashed'}
          </div>
          <div className="text-text2 mb-2">{this.state.error?.message || 'Unknown error'}</div>
          <button className="btn" onClick={() => this.setState({ hasError: false, error: undefined })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
