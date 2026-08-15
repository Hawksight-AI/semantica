import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { GRAPH_THEME, withAlpha } from "./graphTheme";
import { GRAPH_LOAD_STAGE_SEQUENCE, createGraphLoadProgress, getGraphLoadStageLabel } from "./graphLoading";
import type { GraphLoadProgress } from "./types";

const LOADING_OVERLAY_CSS = `
  .graph-stage-loader {
    position: absolute;
    inset: 0;
    z-index: 9;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 1;
    transition: opacity 220ms ease, transform 220ms ease;
  }
  .graph-stage-loader[data-exiting="true"] {
    opacity: 0;
    transform: scale(0.985);
  }
  .graph-stage-loader-card {
    width: min(540px, calc(100% - 48px));
    border-radius: 24px;
    padding: 20px 20px 18px;
    border: 1px solid rgba(127, 208, 255, 0.18);
    background:
      radial-gradient(circle at top right, rgba(242, 182, 109, 0.12), transparent 28%),
      radial-gradient(circle at top left, rgba(127, 208, 255, 0.14), transparent 30%),
      linear-gradient(145deg, rgba(7, 17, 31, 0.94), rgba(12, 25, 43, 0.82));
    box-shadow: 0 26px 90px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255,255,255,0.05);
    backdrop-filter: blur(18px) saturate(1.08);
    -webkit-backdrop-filter: blur(18px) saturate(1.08);
  }
  .graph-stage-loader-card[data-live="true"] {
    width: min(500px, calc(100% - 56px));
    background:
      radial-gradient(circle at top right, rgba(242, 182, 109, 0.08), transparent 26%),
      radial-gradient(circle at top left, rgba(127, 208, 255, 0.12), transparent 28%),
      linear-gradient(145deg, rgba(7, 17, 31, 0.84), rgba(11, 24, 40, 0.72));
    box-shadow: 0 18px 54px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255,255,255,0.04);
  }
  .graph-stage-loader-beacon {
    position: relative;
    width: 12px;
    height: 12px;
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(127, 208, 255, 0.98), rgba(242, 182, 109, 0.94));
    box-shadow: 0 0 18px rgba(127, 208, 255, 0.4);
  }
  .graph-stage-loader-beacon::after {
    content: "";
    position: absolute;
    inset: -7px;
    border-radius: inherit;
    border: 1px solid rgba(127, 208, 255, 0.18);
    animation: graph-loader-beacon 1.9s ease-out infinite;
  }
  .graph-stage-loader-track {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 8px;
  }
  .graph-stage-loader-step {
    border-radius: 999px;
    padding: 7px 0;
    text-align: center;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid rgba(127, 208, 255, 0.08);
    color: rgba(143, 168, 198, 0.72);
    background: rgba(255, 255, 255, 0.02);
  }
  .graph-stage-loader-step[data-state="done"] {
    color: rgba(214, 232, 250, 0.92);
    border-color: rgba(127, 208, 255, 0.18);
    background: rgba(89, 155, 220, 0.14);
  }
  .graph-stage-loader-step[data-state="active"] {
    color: #eff7ff;
    border-color: rgba(242, 182, 109, 0.24);
    background: linear-gradient(135deg, rgba(49, 108, 172, 0.28), rgba(242, 182, 109, 0.16));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
  }
  .graph-stage-loader-bar {
    position: relative;
    width: 100%;
    height: 12px;
    overflow: hidden;
    border-radius: 999px;
    border: 1px solid rgba(127, 208, 255, 0.1);
    background: rgba(255, 255, 255, 0.05);
  }
  .graph-stage-loader-bar-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, rgba(74, 163, 255, 0.9), rgba(127, 208, 255, 0.96), rgba(242, 182, 109, 0.92));
    box-shadow: 0 0 30px rgba(74, 163, 255, 0.28);
    transition: width 220ms ease;
  }
  .graph-stage-loader-bar-indeterminate::before {
    content: "";
    position: absolute;
    top: 1px;
    bottom: 1px;
    width: 34%;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(74, 163, 255, 0), rgba(127, 208, 255, 0.94), rgba(242, 182, 109, 0.82), rgba(74, 163, 255, 0));
    box-shadow: 0 0 26px rgba(127, 208, 255, 0.18);
    animation: graph-loader-sweep 1.5s cubic-bezier(0.22, 1, 0.36, 1) infinite;
  }
  @keyframes graph-loader-beacon {
    0% { transform: scale(0.72); opacity: 0.6; }
    100% { transform: scale(1.44); opacity: 0; }
  }
  @keyframes graph-loader-sweep {
    0% { transform: translateX(-120%); }
    100% { transform: translateX(360%); }
  }
  .graph-stage-loader-card[data-error="true"] {
    pointer-events: auto;
    border-color: rgba(255, 123, 114, 0.32);
    background:
      radial-gradient(circle at top left, rgba(255, 123, 114, 0.12), transparent 32%),
      linear-gradient(145deg, rgba(7, 17, 31, 0.96), rgba(24, 14, 18, 0.86));
  }
  .graph-stage-loader-error-mark {
    width: 38px;
    height: 38px;
    flex: 0 0 auto;
    border-radius: 12px;
    display: grid;
    place-items: center;
    color: #ff9e97;
    background: rgba(255, 123, 114, 0.12);
    border: 1px solid rgba(255, 123, 114, 0.28);
  }
  .graph-stage-loader-error-detail {
    padding: 10px 12px;
    border-radius: 10px;
    background: rgba(0, 0, 0, 0.32);
    border: 1px solid rgba(255, 123, 114, 0.18);
    color: #ffb4ae;
    font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
    font-size: 12px;
    line-height: 1.55;
    word-break: break-word;
  }
  .graph-stage-loader-retry {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 9px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    border: 1px solid rgba(127, 208, 255, 0.4);
    background: linear-gradient(135deg, rgba(74, 163, 255, 0.28), rgba(56, 210, 160, 0.16));
    color: #e8f6ff;
    transition: 160ms ease;
  }
  .graph-stage-loader-retry:hover {
    border-color: rgba(127, 208, 255, 0.62);
    background: linear-gradient(135deg, rgba(74, 163, 255, 0.4), rgba(56, 210, 160, 0.24));
    transform: translateY(-1px);
  }
  .graph-stage-loader-retry:focus-visible {
    outline: 2px solid #7fd0ff;
    outline-offset: 2px;
  }
`;

function formatLayoutSource(source: GraphLoadProgress["layoutSource"]) {
  switch (source) {
    case "provided":
      return "Persisted layout";
    case "carried":
      return "Preserved layout";
    case "runtime":
      return "Runtime layout";
    default:
      return null;
  }
}

function formatLayoutState(state: GraphLoadProgress["layoutState"]) {
  switch (state) {
    case "bootstrapping":
      return "Bootstrapping";
    case "running":
      return "Settling";
    case "interactive":
      return "Interactive";
    case "stabilized":
      return "Stable";
    case "failed":
      return "Fallback";
    default:
      return null;
  }
}

const loadingMetricStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "7px 10px",
  borderRadius: 999,
  border: "1px solid rgba(127, 208, 255, 0.12)",
  background: "rgba(255, 255, 255, 0.03)",
  color: "#b8cade",
  fontSize: 11,
  fontWeight: 600,
} satisfies CSSProperties;

export function GraphLoadingOverlay({
  progress,
  visible,
  showGraphBehind,
  error = null,
  onRetry,
}: {
  progress: GraphLoadProgress | null;
  visible: boolean;
  showGraphBehind: boolean;
  error?: string | null;
  onRetry?: () => void;
}) {
  const [renderVisible, setRenderVisible] = useState(visible);
  const [exiting, setExiting] = useState(false);
  const [displayProgress, setDisplayProgress] = useState<GraphLoadProgress>(
    progress ?? createGraphLoadProgress({
      phase: "bootstrapping",
      message: "Preparing graph session",
      progressKind: "indeterminate",
    }),
  );
  const exitTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (progress) {
      setDisplayProgress(progress);
    }
  }, [progress]);

  useEffect(() => {
    if (visible) {
      if (exitTimerRef.current !== null) {
        window.clearTimeout(exitTimerRef.current);
        exitTimerRef.current = null;
      }
      setRenderVisible(true);
      setExiting(false);
      return;
    }

    if (!renderVisible) {
      return;
    }

    setExiting(true);
    exitTimerRef.current = window.setTimeout(() => {
      setRenderVisible(false);
      setExiting(false);
      exitTimerRef.current = null;
    }, 220);

    return () => {
      if (exitTimerRef.current !== null) {
        window.clearTimeout(exitTimerRef.current);
        exitTimerRef.current = null;
      }
    };
  }, [renderVisible, visible]);

  if (!renderVisible) {
    return null;
  }

  if (error) {
    return (
      <div
        className="graph-stage-loader"
        data-exiting={exiting}
        style={{ background: "linear-gradient(180deg, rgba(1,4,9,0.22), rgba(1,4,9,0.5))" }}
      >
        <style>{LOADING_OVERLAY_CSS}</style>
        <div className="graph-stage-loader-card" data-error="true" role="alert">
          <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 14 }}>
            <div className="graph-stage-loader-error-mark" aria-hidden="true">
              <AlertTriangle size={18} strokeWidth={2.2} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ color: "#ffffff", fontSize: 20, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 6 }}>
                Could not load the graph
              </div>
              <div style={{ color: "#8fa8c6", fontSize: 13, lineHeight: 1.5 }}>
                The Explorer API did not return graph data. Check that the backend is running and reachable, then try again.
              </div>
            </div>
          </div>

          <div className="graph-stage-loader-error-detail">{error}</div>

          {onRetry ? (
            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              <button type="button" className="graph-stage-loader-retry" onClick={onRetry}>
                <RefreshCw size={14} strokeWidth={2.2} aria-hidden />
                Retry
              </button>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const activeProgress = progress ?? displayProgress;
  const isLiveStage = activeProgress.phase === "stabilizing_layout" || activeProgress.showGraphBehind || showGraphBehind;
  const overlayBackground = isLiveStage
    ? "linear-gradient(180deg, rgba(1,4,9,0.04), rgba(1,4,9,0.18))"
    : "linear-gradient(180deg, rgba(1,4,9,0.22), rgba(1,4,9,0.5))";
  const determinateRatio = activeProgress.progressKind === "determinate" && activeProgress.total
    ? Math.max(0.05, Math.min(activeProgress.loaded ?? 0, activeProgress.total) / Math.max(activeProgress.total, 1))
    : null;
  const layoutSource = formatLayoutSource(activeProgress.layoutSource);
  const layoutState = formatLayoutState(activeProgress.layoutState);

  return (
    <div
      className="graph-stage-loader"
      data-exiting={exiting}
      style={{ background: overlayBackground }}
    >
      <style>{LOADING_OVERLAY_CSS}</style>
      <div className="graph-stage-loader-card" data-live={isLiveStage}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14, marginBottom: 14 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ color: "#ffffff", fontSize: 20, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 6 }}>
              {activeProgress.title}
            </div>
            <div style={{ color: "#8fa8c6", fontSize: 13, lineHeight: 1.5 }}>
              {activeProgress.message}
            </div>
          </div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
            <div className="graph-stage-loader-beacon" aria-hidden="true" />
            <div style={{ color: "#d7e9fb", fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Stage {activeProgress.stageIndex ?? 1}/{activeProgress.stageCount ?? GRAPH_LOAD_STAGE_SEQUENCE.length}
            </div>
          </div>
        </div>

        <div className="graph-stage-loader-track" style={{ marginBottom: 14 }}>
          {GRAPH_LOAD_STAGE_SEQUENCE.map((phase, index) => {
            const current = activeProgress.stageIndex ?? 1;
            const state = index + 1 < current ? "done" : index + 1 === current ? "active" : "upcoming";
            return (
              <div key={phase} className="graph-stage-loader-step" data-state={state}>
                {getGraphLoadStageLabel(phase)}
              </div>
            );
          })}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", marginBottom: 8 }}>
          <div style={{ color: "#dce9f6", fontSize: 12, fontWeight: 600 }}>
            {activeProgress.progressKind === "determinate" && activeProgress.total
              ? `${(activeProgress.loaded ?? 0).toLocaleString()} / ${activeProgress.total.toLocaleString()} in current stage`
              : "Working through this stage"}
          </div>
          <div style={{ color: "#90a8c5", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            {activeProgress.progressKind === "determinate" && determinateRatio !== null
              ? `${Math.round(determinateRatio * 100)}%`
              : "Live"}
          </div>
        </div>

        <div className={`graph-stage-loader-bar ${activeProgress.progressKind === "indeterminate" ? "graph-stage-loader-bar-indeterminate" : ""}`}>
          {activeProgress.progressKind === "determinate" && determinateRatio !== null ? (
            <span className="graph-stage-loader-bar-fill" style={{ width: `${Math.round(determinateRatio * 100)}%` }} />
          ) : null}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 14 }}>
          <span style={loadingMetricStyle}>
            {activeProgress.nodesLoaded.toLocaleString()}
            {activeProgress.nodesTotal ? ` / ${activeProgress.nodesTotal.toLocaleString()}` : ""} nodes
          </span>
          <span style={loadingMetricStyle}>
            {activeProgress.edgesLoaded.toLocaleString()}
            {activeProgress.edgesTotal ? ` / ${activeProgress.edgesTotal.toLocaleString()}` : ""} relationships
          </span>
          {layoutSource ? (
            <span style={{ ...loadingMetricStyle, color: "#a9ddff", borderColor: withAlpha(GRAPH_THEME.palette.accent.hovered, 0.22) }}>
              {layoutSource}
              {layoutState ? ` · ${layoutState}` : ""}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
