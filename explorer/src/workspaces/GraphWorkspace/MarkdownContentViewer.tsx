import { useState, useRef, useEffect, useId, type CSSProperties, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Code2, Eye, ExternalLink, Image as ImageIcon } from "lucide-react";
import { GRAPH_THEME } from "./graphTheme";

export interface MarkdownContentViewerProps {
  content?: string | null;
  className?: string;
  defaultMode?: "preview" | "source";
}

export function isSafeUrl(url?: string): boolean {
  if (!url) return false;
  const trimmed = url.trim();
  // Reject whitespace-only strings — new URL("", base) would resolve to the base
  // protocol and produce a false positive. This guards direct callers of the exported
  // function; markdown parsers normalise whitespace-only destinations to "" which
  // already fails the !url check above.
  if (!trimmed) return false;
  if (trimmed.startsWith("//")) return false;
  if (trimmed.startsWith("#")) return true;
  if (trimmed.startsWith("/")) return true;
  try {
    const parsed = new URL(trimmed, "http://localhost");
    return ["http:", "https:", "mailto:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}

export function MarkdownContentViewer({
  content,
  className,
  defaultMode = "preview",
}: MarkdownContentViewerProps) {
  const [activeMode, setActiveMode] = useState<"preview" | "source">(defaultMode);
  const [copied, setCopied] = useState(false);
  // Track the content value for which the copied indicator is valid.
  // When content changes (i.e. the user selects a different node), reset the
  // copied indicator inline during render rather than in a useEffect — this
  // avoids a cascading-render lint error and is the React-recommended pattern
  // for resetting derived visual state on prop changes.
  const [copiedForContent, setCopiedForContent] = useState<string | null | undefined>(content);
  if (copiedForContent !== content) {
    setCopiedForContent(content);
    if (copied) {
      // Clear the stale indicator synchronously so the new node's copy button
      // never shows "Copied" from the previous selection.
      setCopied(false);
    }
  }

  // useId (not hardcoded strings) so the ids stay unique if more than one viewer
  // is ever mounted at once — the same pattern GraphWorkspace uses for its search
  // combobox. Hardcoded ids would collide silently in that case.
  const baseId = useId();
  const previewTabId = `${baseId}-tab-preview`;
  const sourceTabId = `${baseId}-tab-source`;
  const panelId = `${baseId}-panel`;

  // Roving tabindex: the tablist is one Tab stop and arrows move focus within it.
  // Focus is tracked separately from selection because activation is manual (see
  // handleTabKeyDown), so a tab can hold focus without being the selected one.
  const [focusedMode, setFocusedMode] = useState<"preview" | "source">(defaultMode);
  const previewTabRef = useRef<HTMLButtonElement>(null);
  const sourceTabRef = useRef<HTMLButtonElement>(null);

  const focusTab = (mode: "preview" | "source") => {
    setFocusedMode(mode);
    (mode === "preview" ? previewTabRef : sourceTabRef).current?.focus();
  };

  const selectMode = (mode: "preview" | "source") => {
    setActiveMode(mode);
    setFocusedMode(mode);
  };

  // Manual activation (APG permits it, and here it is required): arrows move
  // focus only, Enter/Space activates via the native button click. Automatic
  // activation would re-run the full markdown parse on every arrow keypress —
  // measured at 385ms for a 1000-row GFM table and 1.4s at 2000 rows (#1118).
  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const order = ["preview", "source"] as const;
    const current = order.indexOf(focusedMode);
    let next: "preview" | "source";
    switch (event.key) {
      case "ArrowRight": next = order[(current + 1) % order.length]; break;
      case "ArrowLeft": next = order[(current - 1 + order.length) % order.length]; break;
      case "Home": next = order[0]; break;
      case "End": next = order[order.length - 1]; break;
      default: return;
    }
    event.preventDefault();
    focusTab(next);
  };

  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up any outstanding timeout on unmount.
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const rawContent = typeof content === "string" ? content : "";
  const hasContent = rawContent.trim().length > 0;

  const handleCopy = async () => {
    if (!hasContent) return;
    try {
      await navigator.clipboard.writeText(rawContent);
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
      setCopied(true);
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard write unavailable
    }
  };

  return (
    <div className={className} style={viewerContainerStyle}>
      <div style={viewerHeaderStyle}>
        <div style={{ display: "flex", gap: 4 }} role="tablist" aria-label="Content view mode">
          <button
            type="button"
            role="tab"
            id={previewTabId}
            ref={previewTabRef}
            aria-selected={activeMode === "preview"}
            aria-controls={panelId}
            tabIndex={focusedMode === "preview" ? 0 : -1}
            onClick={() => selectMode("preview")}
            onKeyDown={handleTabKeyDown}
            style={{ ...tabBtnStyle, ...(activeMode === "preview" ? activeTabBtnStyle : {}) }}
          >
            <Eye size={12} style={{ marginRight: 5 }} />
            Preview
          </button>
          <button
            type="button"
            role="tab"
            id={sourceTabId}
            ref={sourceTabRef}
            aria-selected={activeMode === "source"}
            aria-controls={panelId}
            tabIndex={focusedMode === "source" ? 0 : -1}
            onClick={() => selectMode("source")}
            onKeyDown={handleTabKeyDown}
            style={{ ...tabBtnStyle, ...(activeMode === "source" ? activeTabBtnStyle : {}) }}
          >
            <Code2 size={12} style={{ marginRight: 5 }} />
            Source
          </button>
        </div>

        {hasContent && (
          <button type="button" onClick={() => void handleCopy()} style={copyBtnStyle} title="Copy raw content">
            {copied ? (
              <>
                <Check size={12} color="#3fb950" style={{ marginRight: 4 }} />
                <span style={{ color: "#3fb950", fontSize: 11 }}>Copied</span>
              </>
            ) : (
              <>
                <Copy size={12} style={{ marginRight: 4 }} />
                <span style={{ fontSize: 11 }}>Copy</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* Both tabs point aria-controls at this one panel: only the active view is
          ever rendered, so per-tab panel ids would leave the inactive tab
          referencing an element that is not in the DOM. Wrapping all three
          branches — including the empty state — keeps the reference resolvable.
          tabIndex 0 because the panel is a scroll container (viewerBodyStyle caps
          its height), so keyboard users need to be able to focus and scroll it. */}
      <div
        style={viewerBodyStyle}
        role="tabpanel"
        id={panelId}
        aria-labelledby={activeMode === "preview" ? previewTabId : sourceTabId}
        tabIndex={0}
      >
        {!hasContent ? (
          <div style={emptyTextStyle}>No content available for this node.</div>
        ) : activeMode === "source" ? (
          <pre style={sourcePreStyle}>
            <code style={sourceCodeStyle}>{rawContent}</code>
          </pre>
        ) : (
          <div style={previewStyle}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // C-1: react-markdown passes a HAST `node` prop (the raw AST
                // Element) to every custom component override via passNode:true.
                // In React 19 any unknown prop spreads onto a native element are
                // serialised as HTML attributes, producing node="[object Object]"
                // on every rendered link. Fix: destructure `node` by name so it
                // is explicitly discarded, then spread `...rest` to preserve all
                // other legitimate HAST/remark-gfm attributes — e.g. the `id`,
                // `aria-describedby`, `aria-label`, `data-footnote-ref`,
                // `data-footnote-backref`, and `class` attrs that GFM footnotes
                // require for correct in-page navigation and accessibility.
                //
                // C-2: fragment links (#anchor, GFM footnote backlinks) must
                // navigate within the current document. External links continue
                // to use target="_blank" with noopener noreferrer.
                //
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                a: ({ href, children, title, node: _node, ...rest }) => {
                  if (!isSafeUrl(href)) {
                    return <span style={{ color: GRAPH_THEME.ui.text.muted, textDecoration: "line-through" }}>{children}</span>;
                  }
                  // isSafeUrl returning true guarantees href is a non-empty string.
                  const safeHref = href ?? "";
                  // Fragment links (#section, footnote backlinks like
                  // #user-content-fnref-1) are in-document anchors. Opening them
                  // in a new tab would break GFM footnote back-navigation.
                  const isFragment = safeHref.startsWith("#");
                  if (isFragment) {
                    return (
                      <a href={safeHref} title={title} style={linkStyle} {...rest}>
                        {children}
                      </a>
                    );
                  }
                  return (
                    <a href={safeHref} title={title} target="_blank" rel="noopener noreferrer" style={linkStyle} {...rest}>
                      {children}
                      <ExternalLink size={10} style={{ marginLeft: 3, verticalAlign: "middle", display: "inline" }} />
                    </a>
                  );
                },
                img: ({ src, alt }) => (
                  <span style={imageBadgeStyle} title={src || "Image"}>
                    <ImageIcon size={12} style={{ marginRight: 5 }} />
                    <span>Image: {alt || src || "unlabeled"}</span>
                  </span>
                ),
                h1: ({ children }) => <h1 style={h1Style}>{children}</h1>,
                h2: ({ children }) => <h2 style={h2Style}>{children}</h2>,
                h3: ({ children }) => <h3 style={h3Style}>{children}</h3>,
                h4: ({ children }) => <h4 style={h4Style}>{children}</h4>,
                p: ({ children }) => <p style={{ margin: "0 0 8px 0" }}>{children}</p>,
                ul: ({ children }) => <ul style={{ margin: "0 0 8px 0", paddingLeft: 18 }}>{children}</ul>,
                ol: ({ children }) => <ol style={{ margin: "0 0 8px 0", paddingLeft: 18 }}>{children}</ol>,
                li: ({ children }) => <li style={{ marginBottom: 3 }}>{children}</li>,
                blockquote: ({ children }) => <blockquote style={blockquoteStyle}>{children}</blockquote>,
                hr: () => <hr style={{ border: "none", borderTop: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`, margin: "10px 0" }} />,
                table: ({ children }) => (
                  <div style={{ width: "100%", overflowX: "auto", margin: "8px 0", borderRadius: 6, border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>{children}</table>
                  </div>
                ),
                thead: ({ children }) => <thead style={{ background: "rgba(255, 255, 255, 0.04)" }}>{children}</thead>,
                tbody: ({ children }) => <tbody>{children}</tbody>,
                tr: ({ children }) => <tr style={{ borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>{children}</tr>,
                th: ({ children }) => <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700, color: GRAPH_THEME.ui.text.strong, borderRight: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>{children}</th>,
                td: ({ children }) => <td style={{ padding: "6px 8px", color: GRAPH_THEME.ui.text.body, borderRight: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>{children}</td>,
                pre: ({ children }) => <pre style={preBlockStyle}>{children}</pre>,
                // C-1: discard `node` here too — code elements are custom components
                // and would otherwise receive node="[object Object]" in the DOM.
                code: ({ className: codeClass, children }) => {
                  const isInline = !codeClass && typeof children === "string" && !children.includes("\n");
                  return (
                    <code style={isInline ? inlineCodeStyle : blockCodeStyle}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {rawContent}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Styles ──────────────────────────────────────────────────────── */

const viewerContainerStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  background: "rgba(255, 255, 255, 0.025)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 12,
  overflow: "hidden",
};

const viewerHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "6px 10px",
  background: "rgba(0, 0, 0, 0.2)",
  borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const tabBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "4px 9px",
  borderRadius: 6,
  border: "1px solid transparent",
  background: "transparent",
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 150ms ease",
};

const activeTabBtnStyle: CSSProperties = {
  background: GRAPH_THEME.ui.timeline.playheadSoft,
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  color: GRAPH_THEME.ui.timeline.playhead,
};

const copyBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "3px 8px",
  borderRadius: 6,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  background: "rgba(255, 255, 255, 0.04)",
  color: GRAPH_THEME.ui.text.subtle,
  fontSize: 11,
  cursor: "pointer",
};

const viewerBodyStyle: CSSProperties = {
  padding: 12,
  maxHeight: 380,
  overflowY: "auto",
};

const emptyTextStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  lineHeight: 1.5,
  fontStyle: "italic",
};

const sourcePreStyle: CSSProperties = {
  margin: 0,
  padding: 10,
  borderRadius: 8,
  background: "rgba(0, 0, 0, 0.3)",
  border: "1px solid rgba(255, 255, 255, 0.05)",
  overflowX: "auto",
};

const sourceCodeStyle: CSSProperties = {
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  fontSize: 12,
  lineHeight: 1.6,
  color: GRAPH_THEME.ui.text.strong,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  userSelect: "text",
};

const previewStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.body,
  fontSize: 13,
  lineHeight: 1.6,
  wordBreak: "break-word",
};

const h1Style: CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 8,
  marginBottom: 6,
  paddingBottom: 3,
  borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const h2Style: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 8,
  marginBottom: 4,
};

const h3Style: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 6,
  marginBottom: 4,
};

const h4Style: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 4,
  marginBottom: 2,
};

const blockquoteStyle: CSSProperties = {
  margin: "8px 0",
  padding: "6px 12px",
  borderLeft: `3px solid ${GRAPH_THEME.ui.timeline.playhead}`,
  background: "rgba(98, 226, 205, 0.05)",
  borderRadius: "0 6px 6px 0",
  color: GRAPH_THEME.ui.text.body,
  fontStyle: "italic",
};

const linkStyle: CSSProperties = {
  color: "#79c0ff",
  textDecoration: "underline",
  textUnderlineOffset: "3px",
  wordBreak: "break-all",
};

const imageBadgeStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "3px 7px",
  background: "rgba(255, 255, 255, 0.04)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 6,
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
  margin: "3px 0",
};

const inlineCodeStyle: CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
  padding: "2px 5px",
  borderRadius: 4,
  background: "rgba(255, 255, 255, 0.07)",
  color: "#e6edf3",
  border: "1px solid rgba(255, 255, 255, 0.08)",
};

const preBlockStyle: CSSProperties = {
  margin: "8px 0",
  padding: 10,
  borderRadius: 8,
  background: "rgba(0, 0, 0, 0.35)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  overflowX: "auto",
};

const blockCodeStyle: CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
  lineHeight: 1.5,
  color: "#e6edf3",
};
