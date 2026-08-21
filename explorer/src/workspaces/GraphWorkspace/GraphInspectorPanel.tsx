import type { CSSProperties } from "react";
import { Loader2 } from "lucide-react";
import { graph } from "../../store/graphStore";
import { GRAPH_THEME, withAlpha } from "./graphTheme";
import type { GraphSelectedNodeKind } from "./types";
import { useI18n } from "../../i18n";
import { localizeReason, translateEdgeType } from "./plugins";

export type LinkPrediction = {
  target: string;
  type: string;
  label?: string;
  score: number;
};

export type PathResponse = {
  path: string[];
  edge_ids?: string[];
  total_weight: number;
  hop_count: number;
  distance_band: "direct" | "near" | "mid-range" | "distant";
  // FR-1 distance intelligence enrichment
  semantic_similarity?: number | null;
  path_coherence_score?: number | null;
  confidence_decay?: number | null;
  bottleneck_node?: string | null;
  alternative_path_count?: number;
  interpretation?: string;
};

export interface GraphInspectorPanelProps {
  nodeId: string;
  inspectableNodeId?: string | null;
  selectedNodeKind?: GraphSelectedNodeKind;
  canActivateFocused?: boolean;
  focusedUnavailableReason?: string | null;
  predictions: LinkPrediction[];
  predictionType: string;
  onPredictionTypeChange: (value: string) => void;
  onRunPredictions: () => void;
  isRunningPredictions?: boolean;
  pathTargetId: string;
  onPathTargetChange: (value: string) => void;
  onTracePath: () => void;
  pathResult: PathResponse | null;
  onDownloadProvenance: (format: "json" | "markdown") => void;
  onFocusNode?: (nodeId: string) => void;
}

const PROVENANCE_KEYS = ["source", "source_url", "pmid", "pmids", "evidence", "provenance", "confidence"] as const;

function sourceAttribution(properties: Record<string, unknown>) {
  return PROVENANCE_KEYS
    .filter((key) => key in properties)
    .map((key) => ({ key, value: properties[key] }));
}

/* ─── Path Distance Intelligence Panel ──────────────────────────── */

const BAND_COLORS: Record<string, string> = {
  direct: "#3fb950",
  near: "#79c0ff",
  "mid-range": "#e3b341",
  distant: "#ff7b72",
};

function PathDistanceIntelPanel({ result }: { result: PathResponse }) {
  const { t } = useI18n();
  const bandColor = BAND_COLORS[result.distance_band] ?? "#8b949e";
  const hasMetrics =
    result.confidence_decay != null ||
    result.semantic_similarity != null ||
    result.path_coherence_score != null ||
    result.bottleneck_node != null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
      {/* distance band + alt paths */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span
          style={{
            padding: "3px 8px",
            borderRadius: 999,
            background: withAlpha(bandColor, 0.14),
            border: `1px solid ${withAlpha(bandColor, 0.3)}`,
            color: bandColor,
            fontSize: 11,
            fontWeight: 700,
          }}
        >
          {result.distance_band} · {t("graph.inspector.hopsLabel", { n: result.hop_count })}
        </span>
        {(result.alternative_path_count ?? 0) > 0 && (
          <span style={subtleChipStyle}>{result.alternative_path_count === 1 ? t("graph.inspector.altPath", { n: result.alternative_path_count ?? 0 }) : t("graph.inspector.altPaths", { n: result.alternative_path_count ?? 0 })}</span>
        )}
      </div>

      {/* metric grid */}
      {hasMetrics && <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {result.confidence_decay != null && (
          <div style={metricCardStyle}>
            <div style={metricLabelStyle}>{t("graph.inspector.confidenceDecay")}</div>
            <div
              style={{
                ...metricValueStyle,
                color: result.confidence_decay > 0.6 ? "#3fb950" : result.confidence_decay > 0.3 ? "#e3b341" : "#ff7b72",
              }}
            >
              {(result.confidence_decay * 100).toFixed(1)}%
            </div>
            <div style={metricBarTrackStyle}>
              <div
                style={{
                  ...metricBarFillStyle,
                  width: `${result.confidence_decay * 100}%`,
                  background:
                    result.confidence_decay > 0.6 ? "#3fb950" : result.confidence_decay > 0.3 ? "#e3b341" : "#ff7b72",
                }}
              />
            </div>
          </div>
        )}
        {result.semantic_similarity != null && (
          <div style={metricCardStyle}>
            <div style={metricLabelStyle}>{t("graph.inspector.semanticSim")}</div>
            <div style={{ ...metricValueStyle, color: "#79c0ff" }}>
              {(result.semantic_similarity * 100).toFixed(1)}%
            </div>
            <div style={metricBarTrackStyle}>
              <div style={{ ...metricBarFillStyle, width: `${result.semantic_similarity * 100}%`, background: "#79c0ff" }} />
            </div>
          </div>
        )}
        {result.path_coherence_score != null && (
          <div style={metricCardStyle}>
            <div style={metricLabelStyle}>{t("graph.inspector.pathCoherence")}</div>
            <div style={{ ...metricValueStyle, color: "#a5d6a7" }}>
              {(result.path_coherence_score * 100).toFixed(1)}%
            </div>
          </div>
        )}
        {result.bottleneck_node && (
          <div style={metricCardStyle}>
            <div style={metricLabelStyle}>{t("graph.inspector.bottleneck")}</div>
            <div
              style={{
                ...metricValueStyle,
                color: "#e3b341",
                fontSize: 11,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={result.bottleneck_node}
            >
              {getNodeLabel(result.bottleneck_node)}
            </div>
          </div>
        )}
      </div>}

      {/* interpretation */}
      {result.interpretation && (
        <div
          style={{
            padding: "8px 10px",
            background: "rgba(88,166,255,0.06)",
            borderRadius: 8,
            border: "1px solid rgba(88,166,255,0.14)",
            color: "#a0b4cc",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          {result.interpretation}
        </div>
      )}
    </div>
  );
}

/* ─── Path Flow Visualizer ──────────────────────────────────────── */

function getNodeLabel(nodeId: string): string {
  if (!graph.hasNode(nodeId)) return nodeId;
  const attrs = graph.getNodeAttributes(nodeId) as { label?: string; content?: string };
  return String(attrs.label ?? attrs.content ?? nodeId);
}

function getEdgeLabelBetween(sourceId: string, targetId: string, edgeIds?: string[]): string {
  // Try to find the specific edge from edgeIds first
  if (edgeIds) {
    for (const edgeId of edgeIds) {
      if (graph.hasEdge(edgeId)) {
        const [src, tgt] = graph.extremities(edgeId);
        if ((src === sourceId && tgt === targetId) || (src === targetId && tgt === sourceId)) {
          const attrs = graph.getEdgeAttributes(edgeId) as { edgeType?: string };
          return attrs.edgeType ?? "→";
        }
      }
    }
  }
  // Fallback: find any edge between the pair
  if (graph.hasNode(sourceId) && graph.hasNode(targetId)) {
    let label = "→";
    graph.forEachEdge(sourceId, targetId, (_edgeId, attrs) => {
      const edgeAttrs = attrs as { edgeType?: string };
      if (edgeAttrs.edgeType) label = edgeAttrs.edgeType;
    });
    return label;
  }
  return "→";
}

function PathFlowViz({
  path,
  edgeIds,
  totalWeight,
  bottleneckNodeId,
  onFocusNode,
}: {
  path: string[];
  edgeIds?: string[];
  totalWeight: number;
  bottleneckNodeId?: string | null;
  onFocusNode?: (nodeId: string) => void;
}) {
  const { t } = useI18n();
  if (path.length === 0) {
    return <div style={emptyTextStyle}>{t("graph.inspector.noPath")}</div>;
  }

  return (
    <div>
      {/* Horizontal scrollable chip flow */}
      <div style={pathFlowContainerStyle}>
        {path.map((nodeId, index) => {
          const label = getNodeLabel(nodeId);
          const edgeLabel =
            index < path.length - 1
              ? getEdgeLabelBetween(nodeId, path[index + 1], edgeIds)
              : null;

          return (
            <div key={`${nodeId}-${index}`} style={{ display: "contents" }}>
              {/* Node chip */}
              <button
                onClick={() => onFocusNode?.(nodeId)}
                title={nodeId === bottleneckNodeId ? t("graph.inspector.bottleneckTitle", { id: nodeId }) : t("graph.inspector.focusTitle", { id: nodeId })}
                style={{
                  ...pathNodeChipStyle,
                  cursor: onFocusNode ? "pointer" : "default",
                  ...(nodeId === bottleneckNodeId
                    ? { border: "1px solid rgba(227,179,65,0.5)", background: "rgba(227,179,65,0.12)" }
                    : {}),
                }}
              >
                <span style={pathNodeIndexStyle}>{index + 1}</span>
                <span style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {label}
                </span>
              </button>

              {/* Edge connector */}
              {edgeLabel !== null ? (
                <div style={pathEdgeConnectorStyle}>
                  <div style={{ width: 16, height: 1, background: "rgba(88,166,255,0.3)" }} />
                  <span style={pathEdgeLabelStyle}>{translateEdgeType(t, edgeLabel)}</span>
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <div style={{ width: 12, height: 1, background: "rgba(88,166,255,0.3)" }} />
                    <div style={{ width: 0, height: 0, borderTop: "4px solid transparent", borderBottom: "4px solid transparent", borderLeft: "5px solid rgba(88,166,255,0.4)" }} />
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* Weight badge */}
      <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "#6a7f97", fontSize: 11 }}>{t("graph.inspector.totalWeight")}</span>
        <span style={{ color: "#79c0ff", fontSize: 12, fontWeight: 700 }}>{totalWeight.toFixed(3)}</span>
        <span style={{ color: "#6a7f97", fontSize: 11 }}>·</span>
        <span style={{ color: "#6a7f97", fontSize: 11 }}>{t("graph.inspector.hopsLabel", { n: path.length })}</span>
      </div>
    </div>
  );
}

/* ─── Main Panel ─────────────────────────────────────────────────── */

export function GraphInspectorPanel({
  nodeId,
  inspectableNodeId,
  selectedNodeKind = "none",
  canActivateFocused = false,
  focusedUnavailableReason = null,
  predictions,
  predictionType,
  onPredictionTypeChange,
  onRunPredictions,
  isRunningPredictions = false,
  pathTargetId,
  onPathTargetChange,
  onTracePath,
  pathResult,
  onDownloadProvenance,
  onFocusNode,
}: GraphInspectorPanelProps) {
  const { t } = useI18n();
  if (!nodeId) {
    return (
      <div style={{ padding: 32, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 12, marginTop: 32 }}>
        <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(98, 226, 205, 0.07)", border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 14, height: 14, borderRadius: "50%", background: GRAPH_THEME.ui.timeline.playheadSoft }} />
        </div>
        <p style={{ color: GRAPH_THEME.ui.text.muted, fontSize: 14, margin: 0, lineHeight: 1.6 }}>
          {t("graph.shell.emptyHint")}
        </p>
      </div>
    );
  }

  const resolvedNodeId = inspectableNodeId && graph.hasNode(inspectableNodeId) ? inspectableNodeId : null;
  const directlyInspectable = graph.hasNode(nodeId);
  const effectiveNodeId = directlyInspectable ? nodeId : resolvedNodeId;
  const actionNodeId = directlyInspectable ? nodeId : resolvedNodeId;
  const groupedDisplaySelection = selectedNodeKind === "grouped" && !directlyInspectable;

  if (!effectiveNodeId) {
    return (
      <aside style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ borderBottom: `1px solid ${GRAPH_THEME.ui.surface.divider}`, paddingBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <span style={{ background: GRAPH_THEME.ui.timeline.playhead, boxShadow: "0 0 10px rgba(98, 226, 205, 0.34)", width: 8, height: 8, borderRadius: "50%" }} />
            <span style={{ color: GRAPH_THEME.ui.timeline.playhead, fontSize: 12, fontWeight: 700 }}>{t("graph.inspector.selection")}</span>
          </div>
          <h3 style={{ margin: 0, color: GRAPH_THEME.ui.text.strong, fontSize: 20, fontWeight: 700, wordBreak: "break-word" }}>
            {nodeId}
          </h3>
          <div style={{ color: GRAPH_THEME.ui.text.muted, fontSize: 12, marginTop: 6, fontFamily: "monospace", wordBreak: "break-all" }}>{nodeId}</div>
        </div>
        <div style={groupedSelectionNoticeStyle}>
          <div style={{ color: GRAPH_THEME.ui.text.strong, fontWeight: 600, marginBottom: 6 }}>{t("graph.inspector.notInspectable")}</div>
          <div style={{ color: GRAPH_THEME.ui.text.body, fontSize: 13, lineHeight: 1.6 }}>
            {canActivateFocused
              ? t("graph.inspector.activateFocusedHint")
              : (localizeReason(t, focusedUnavailableReason) ?? t("graph.inspector.focusedUnavailable"))}
          </div>
        </div>
      </aside>
    );
  }

  const attributes = graph.getNodeAttributes(effectiveNodeId) as {
    color?: string;
    content?: string;
    label?: string;
    nodeType?: string;
    valid_from?: string | null;
    valid_until?: string | null;
    properties?: Record<string, unknown>;
  };
  const properties = attributes?.properties ?? {};
  const attribution = sourceAttribution(properties);
  const accentColor = attributes?.color || "#58a6ff";
  const propertyEntries = Object.entries(properties).filter(
    ([key]) =>
      !["x","y","valid_from","valid_until","content","source","source_url","pmid","pmids","evidence","provenance","confidence"].includes(key),
  );

  return (
    <aside style={{ padding: 24, display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Node identity */}
      <div style={{ borderBottom: `1px solid ${GRAPH_THEME.ui.surface.divider}`, paddingBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ background: accentColor, boxShadow: `0 0 10px ${accentColor}`, width: 8, height: 8, borderRadius: "50%" }} />
          <span style={{ color: accentColor, fontSize: 12, fontWeight: 700 }}>
            {groupedDisplaySelection ? t("graph.inspector.groupedSelection") : (attributes?.nodeType || t("graph.meta.entityFallback"))}
          </span>
        </div>
        <h3 style={{ margin: 0, color: GRAPH_THEME.ui.text.strong, fontSize: 20, fontWeight: 700, wordBreak: "break-word" }}>
          {String(attributes?.label ?? effectiveNodeId)}
        </h3>
        <div style={{ color: GRAPH_THEME.ui.text.muted, fontSize: 12, marginTop: 6, fontFamily: "monospace", wordBreak: "break-all" }}>
          {groupedDisplaySelection ? nodeId : effectiveNodeId}
        </div>
        {groupedDisplaySelection ? (
          <div style={groupedSelectionNoticeStyle}>
            <div style={{ color: GRAPH_THEME.ui.text.strong, fontWeight: 600, marginBottom: 6 }}>{t("graph.inspector.displayLevelHint")}</div>
            <div style={{ color: GRAPH_THEME.ui.text.body, fontSize: 13, lineHeight: 1.6 }}>
              {canActivateFocused
                ? t("graph.inspector.canonicalAvailable", { id: effectiveNodeId })
                : (localizeReason(t, focusedUnavailableReason) ?? t("graph.inspector.focusedUnavailable"))}
            </div>
          </div>
        ) : null}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          {attributes?.valid_from || attributes?.valid_until ? (
            <span style={subtleChipStyle}>{t("graph.meta.temporal")}</span>
          ) : null}
          {attribution.length ? <span style={subtleChipStyle}>{t("graph.meta.sourceFields", { count: attribution.length })}</span> : null}
          {predictions.length ? <span style={subtleChipStyle}>{t("graph.meta.candidateLinks", { count: predictions.length })}</span> : null}
        </div>
      </div>

      {/* Temporal bounds */}
      {(attributes?.valid_from || attributes?.valid_until) ? (
        <div style={{ padding: "10px 12px", background: "rgba(233, 196, 122, 0.075)", border: "1px solid rgba(233, 196, 122, 0.22)", borderRadius: 8, fontSize: 12, color: GRAPH_THEME.palette.accent.selected, fontFamily: "monospace" }}>
          {attributes?.valid_from ? <div>{t("graph.meta.from")} {attributes.valid_from}</div> : null}
          {attributes?.valid_until ? <div>{t("graph.meta.until")} {attributes.valid_until}</div> : null}
        </div>
      ) : null}

      {/* Actions */}
      <section style={sectionStyle}>
        <div style={sectionTitleStyle}>{t("graph.actions.title")}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            style={{ ...actionButtonStyle, width: "100%", justifyContent: "center", opacity: isRunningPredictions ? 0.7 : 1 }}
            onClick={onRunPredictions}
            disabled={isRunningPredictions || !actionNodeId}
          >
            {isRunningPredictions ? (
              <Loader2 size={14} className="animate-spin" style={{ marginRight: 6 }} />
            ) : null}
            {isRunningPredictions ? t("graph.actions.running") : t("graph.actions.runLinkPrediction")}
          </button>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button style={secondaryActionButtonStyle} onClick={() => onDownloadProvenance("json")} disabled={!actionNodeId}>
              {t("graph.actions.provenanceJson")}
            </button>
            <button style={secondaryActionButtonStyle} onClick={() => onDownloadProvenance("markdown")} disabled={!actionNodeId}>
              {t("graph.actions.provenanceMd")}
            </button>
          </div>
        </div>
        <input
          value={predictionType}
          onChange={(event) => onPredictionTypeChange(event.target.value)}
          placeholder={t("graph.actions.candidateTypePlaceholder")}
          style={inputStyle}
        />
      </section>

      {/* Trace Path */}
      <section style={sectionStyle}>
        <div style={sectionTitleStyle}>{t("graph.actions.tracePath")}</div>
        <input
          value={pathTargetId}
          onChange={(event) => onPathTargetChange(event.target.value)}
          placeholder={t("graph.actions.targetPlaceholder")}
          style={inputStyle}
        />
        <button style={actionButtonStyle} onClick={onTracePath} disabled={!actionNodeId}>{t("graph.actions.traceButton")}</button>

        {pathResult?.path?.length ? (
          <>
            <PathFlowViz
              path={pathResult.path}
              edgeIds={pathResult.edge_ids}
              totalWeight={pathResult.total_weight}
              bottleneckNodeId={pathResult.bottleneck_node}
              onFocusNode={onFocusNode}
            />
            <PathDistanceIntelPanel result={pathResult} />
          </>
        ) : (
          <div style={emptyTextStyle}>
            {t("graph.actions.chooseTargetHint")}
          </div>
        )}
      </section>

      {/* Candidate Links */}
      <details className="node-panel-collapse" open={predictions.length > 0}>
        <summary className="node-panel-summary">{t("graph.candidateLinks.title")}</summary>
        <div className="node-panel-body">
          {predictions.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {predictions.map((prediction) => (
                <button
                  key={`${prediction.target}-${prediction.type}`}
                  style={predictionCardStyle}
                  onClick={() => onPathTargetChange(prediction.target)}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                    <div>
                      <div style={{ color: GRAPH_THEME.ui.text.strong, fontWeight: 600 }}>{prediction.label || prediction.target}</div>
                      <div style={{ color: GRAPH_THEME.ui.text.muted, fontSize: 12 }}>{prediction.type}</div>
                    </div>
                    <div style={{ flexShrink: 0 }}>
                      <div style={{
                        padding: "2px 7px",
                        borderRadius: 999,
                        fontSize: 10,
                        fontWeight: 700,
                        background: GRAPH_THEME.ui.timeline.playheadSoft,
                        border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
                        color: GRAPH_THEME.ui.timeline.playhead,
                      }}>
                        {(prediction.score * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : isRunningPredictions ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 8, color: "#8b949e", fontSize: 12 }}>
              <Loader2 size={13} className="animate-spin" />
              <span>{t("graph.candidateLinks.computing")}</span>
            </div>
          ) : (
            <div style={emptyTextStyle}>{t("graph.candidateLinks.empty")}</div>
          )}
        </div>
      </details>

      {/* Source Attribution */}
      <details className="node-panel-collapse">
        <summary className="node-panel-summary">{t("graph.sourceAttribution.title")}</summary>
        <div className="node-panel-body">
          {attribution.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {attribution.map(({ key, value }) => (
                <div key={key} style={propertyCardStyle}>
                  <div style={{ color: GRAPH_THEME.ui.timeline.playhead, fontSize: 11, marginBottom: 4 }}>{key}</div>
                  <div style={{ color: GRAPH_THEME.ui.text.body, fontSize: 13, wordBreak: "break-word" }}>
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={emptyTextStyle}>{t("graph.sourceAttribution.empty")}</div>
          )}
        </div>
      </details>

      {/* Properties */}
      <details className="node-panel-collapse">
        <summary className="node-panel-summary">{t("graph.properties.title")}</summary>
        <div className="node-panel-body">
          {propertyEntries.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {propertyEntries.map(([key, value]) => (
                <div key={key} style={propertyCardStyle}>
                  <div style={{ color: GRAPH_THEME.ui.timeline.playhead, fontSize: 11, marginBottom: 4 }}>{key}</div>
                  <div style={{ color: GRAPH_THEME.ui.text.body, fontSize: 13, wordBreak: "break-word" }}>
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={emptyTextStyle}>{t("graph.properties.empty")}</div>
          )}
        </div>
      </details>
    </aside>
  );
}

/* ─── styles ─────────────────────────────────────────────────────── */

const inputStyle: CSSProperties = {
  width: "100%",
  background: GRAPH_THEME.ui.control.inputBg,
  border: `1px solid ${GRAPH_THEME.ui.control.inputBorder}`,
  color: GRAPH_THEME.ui.text.strong,
  borderRadius: 12,
  padding: "11px 13px",
  fontSize: 13,
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.035)",
};

const groupedSelectionNoticeStyle: CSSProperties = {
  marginTop: 12,
  padding: "10px 12px",
  background: "rgba(98, 226, 205, 0.07)",
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  borderRadius: 12,
};

const actionButtonStyle: CSSProperties = {
  background: GRAPH_THEME.ui.control.primaryBg,
  color: GRAPH_THEME.ui.control.primaryText,
  border: `1px solid ${GRAPH_THEME.ui.control.primaryBorder}`,
  borderRadius: 12,
  padding: "9px 12px",
  cursor: "pointer",
  fontWeight: 700,
  fontSize: 12,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.07), 0 10px 24px rgba(0,0,0,0.18)",
};

const secondaryActionButtonStyle: CSSProperties = {
  ...actionButtonStyle,
  background: GRAPH_THEME.ui.control.defaultBg,
  border: `1px solid ${GRAPH_THEME.ui.control.defaultBorder}`,
  color: GRAPH_THEME.ui.control.defaultText,
  fontWeight: 600,
};

const predictionCardStyle: CSSProperties = {
  textAlign: "left",
  padding: "10px 12px",
  background: "rgba(255, 255, 255, 0.035)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 10,
  cursor: "pointer",
  width: "100%",
};

const propertyCardStyle: CSSProperties = {
  background: "rgba(255, 255, 255, 0.028)",
  padding: "10px 12px",
  borderRadius: 10,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const emptyTextStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  lineHeight: 1.5,
};

const subtleChipStyle: CSSProperties = {
  background: "rgba(255, 255, 255, 0.04)",
  color: GRAPH_THEME.ui.text.body,
  padding: "4px 8px",
  borderRadius: 999,
  fontSize: 11,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const sectionStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 10,
  padding: 14,
  background: GRAPH_THEME.ui.surface.cardSubtle,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 14,
};

const sectionTitleStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
};

const pathFlowContainerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 0,
  flexWrap: "wrap",
  rowGap: 8,
};

const pathNodeChipStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "5px 10px",
  borderRadius: 999,
  background: "rgba(98, 226, 205, 0.08)",
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  color: GRAPH_THEME.ui.text.strong,
  fontSize: 12,
  fontWeight: 600,
  maxWidth: 160,
};

const pathNodeIndexStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 16,
  height: 16,
  borderRadius: "50%",
  background: GRAPH_THEME.ui.timeline.playheadSoft,
  color: GRAPH_THEME.ui.timeline.playhead,
  fontSize: 9,
  fontWeight: 800,
  flexShrink: 0,
};

const pathEdgeConnectorStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 2,
  flexShrink: 0,
};

const pathEdgeLabelStyle: CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  color: GRAPH_THEME.ui.text.subtle,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  maxWidth: 70,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const metricCardStyle: CSSProperties = {
  background: "rgba(0,0,0,0.18)",
  borderRadius: 8,
  padding: "8px 10px",
  border: "1px solid rgba(255,255,255,0.05)",
  display: "flex",
  flexDirection: "column",
  gap: 3,
};

const metricLabelStyle: CSSProperties = {
  color: "rgba(88,166,255,0.65)",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const metricValueStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: "#e6edf3",
};

const metricBarTrackStyle: CSSProperties = {
  height: 3,
  borderRadius: 999,
  background: "rgba(255,255,255,0.07)",
  overflow: "hidden",
  marginTop: 4,
};

const metricBarFillStyle: CSSProperties = {
  height: "100%",
  borderRadius: 999,
  transition: "width 300ms ease",
};
