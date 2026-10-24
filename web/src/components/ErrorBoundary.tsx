import { Component, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode; label?: string }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  componentDidCatch(error: Error) { console.error("Floorwise view failed", error); }
  render() {
    if (!this.state.error) return this.props.children;
    return <div role="alert" className="recovery"><h2>{this.props.label ?? "This view could not be displayed"}</h2>
      <p>Your building is still available. Recover the view or reload to start a fresh session.</p>
      <button onClick={() => this.setState({ error: false })}>Recover view</button>
      <button onClick={() => window.location.reload()}>Reload</button></div>;
  }
}
