import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Check,
  Code2,
  Copy,
  Eye,
  ExternalLink,
  Image as ImageIcon,
  Loader2,
  Pencil,
  RefreshCw,
  X,
} from "lucide-react";
import { GRAPH_THEME } from "./graphTheme";
import type { MarkdownApplyResult } from "./markdownResourceClient";
import type { MarkdownResourceRef } from "./markdownEditorState";
import { isSafeUrl } from "./markdownUrlSafety";
import { useMarkdownEditor } from "./useMarkdownEditor";

export interface MarkdownContentViewerProps {
  content?: string | null;
  resource?: MarkdownResourceRef;
  onApplied?: (result: MarkdownApplyResult) => void;
  onDirtyChange?: (dirty: boolean) => void;
  className?: string;
  defaultMode?: "preview" | "source";
}

export function MarkdownContentViewer({
  content,
  resource,
  onApplied,
  onDirtyChange,
  className,
  defaultMode = "preview",
}: MarkdownContentViewerProps) {
  const [activeMode, setActiveMode] = useState<"preview" | "source">(defaultMode);
  const [copied, setCopied] = useState(false);
  const modeBeforeEditRef = useRef<"preview" | "source">(defaultMode);
  const resourceKey = resource ? `${resource.kind}:${resource.id}` : "";
  const [activeResourceKey, setActiveResourceKey] = useState(resourceKey);
  const editor = useMarkdownEditor({ resource, onApplied, onDirtyChange });
  const {
    session,
    error,
    dirty,
    editing,
    saving,
    loading,
  } = editor;

  if (activeResourceKey !== resourceKey) {
    setActiveResourceKey(resourceKey);
    setCopied(false);
    setActiveMode(defaultMode);
  }

  // Track the content value for which the copied indicator is valid.
  const [copiedForContent, setCopiedForContent] = useState<string | null | undefined>(content);
  if (copiedForContent !== content) {
    setCopiedForContent(content);
    if (copied) setCopied(false);
  }

  const copyTimeoutRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const rawContent = editor.editing
    ? editor.session?.draft ?? ""
    : (typeof content === "string" ? content : "");
  const previewContent = useMemo(() => {
    if (!editor.editing) return rawContent;
    const lines = rawContent.split(/\r?\n/);
    if (lines[0] !== "---") return rawContent;
    const closingIndex = lines.findIndex((line, index) => index > 0 && line === "---");
    return closingIndex < 0 ? rawContent : lines.slice(closingIndex + 1).join("\n").replace(/^\n/, "");
  }, [editor.editing, rawContent]);
  const hasContent = rawContent.trim().length > 0;
  const renderedMarkdown = useMemo(
    () => (
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>
        {previewContent}
      </ReactMarkdown>
    ),
    [previewContent],
  );
  const handleCopy = async () => {
    if (!hasContent) return;
    try {
      await navigator.clipboard.writeText(rawContent);
      clearTimeout(copyTimeoutRef.current);
      setCopied(true);
      copyTimeoutRef.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard write unavailable.
    }
  };

  const handleEdit = async () => {
    modeBeforeEditRef.current = activeMode;
    setActiveMode("source");
    if (!await editor.beginEdit()) {
      setActiveMode(modeBeforeEditRef.current);
    }
  };

  const handleCancel = () => {
    editor.discard();
    setActiveMode(modeBeforeEditRef.current);
  };

  const handleApply = async () => {
    if (await editor.save()) {
      setActiveMode("preview");
    }
  };

  return (
    <div className={className} style={viewerContainerStyle}>
      <div style={viewerHeaderStyle}>
        <div style={{ display: "flex", gap: 4 }} role="tablist" aria-label="Markdown view">
          <button
            type="button"
            role="tab"
            aria-selected={activeMode === "preview"}
            aria-controls="markdown-viewer-panel"
            onClick={() => setActiveMode("preview")}
            style={{ ...tabBtnStyle, ...(activeMode === "preview" ? activeTabBtnStyle : {}) }}
          >
            <Eye size={12} style={{ marginRight: 5 }} aria-hidden="true" />
            Preview
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeMode === "source"}
            aria-controls="markdown-viewer-panel"
            onClick={() => setActiveMode("source")}
            style={{ ...tabBtnStyle, ...(activeMode === "source" ? activeTabBtnStyle : {}) }}
          >
            <Code2 size={12} style={{ marginRight: 5 }} aria-hidden="true" />
            Source
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {hasContent && (
            <button type="button" onClick={() => void handleCopy()} style={copyBtnStyle} title="Copy raw content">
              {copied ? (
                <>
                  <Check size={12} color="#3fb950" style={{ marginRight: 4 }} aria-hidden="true" />
                  <span style={{ color: "#3fb950", fontSize: 11 }}>Copied</span>
                </>
              ) : (
                <>
                  <Copy size={12} style={{ marginRight: 4 }} aria-hidden="true" />
                  <span style={{ fontSize: 11 }}>Copy</span>
                </>
              )}
            </button>
          )}
          {resource && !editing && !loading ? (
            <button type="button" onClick={() => void handleEdit()} style={copyBtnStyle}>
              <Pencil size={12} style={{ marginRight: 4 }} aria-hidden="true" />
              Edit
            </button>
          ) : null}
          {loading ? (
            <button type="button" disabled style={{ ...copyBtnStyle, opacity: 0.65 }}>
              <Loader2 size={12} className="animate-spin" style={{ marginRight: 4 }} aria-hidden="true" />
              Loading…
            </button>
          ) : null}
          {editing ? (
            <>
              <button type="button" onClick={handleCancel} disabled={saving} style={copyBtnStyle}>
                <X size={12} style={{ marginRight: 4 }} aria-hidden="true" />
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleApply()}
                disabled={saving || !dirty}
                title={!dirty ? "Make a change before applying" : undefined}
                style={{ ...saveBtnStyle, opacity: saving || !dirty ? 0.55 : 1 }}
              >
                {saving ? (
                  <Loader2 size={12} className="animate-spin" style={{ marginRight: 4 }} aria-hidden="true" />
                ) : (
                  <Check size={12} style={{ marginRight: 4 }} aria-hidden="true" />
                )}
                {saving ? "Applying…" : "Apply"}
              </button>
            </>
          ) : null}
        </div>
      </div>

      {error ? (
        <div id="markdown-editor-error" role="alert" style={errorStyle}>
          <span>{error.message}</span>
          {error.kind === "conflict" ? (
            <button type="button" onClick={() => void editor.reloadLatest()} style={errorActionStyle}>
              <RefreshCw size={12} style={{ marginRight: 4 }} aria-hidden="true" />
              Reload latest
            </button>
          ) : null}
        </div>
      ) : null}

      <div
        id="markdown-viewer-panel"
        role="tabpanel"
        aria-busy={saving || loading}
        style={viewerBodyStyle}
      >
        {activeMode === "source" && editing ? (
          <textarea
            aria-label="Markdown source"
            aria-describedby={error ? "markdown-editor-error" : undefined}
            aria-invalid={error?.kind === "validation" || undefined}
            value={session?.draft ?? ""}
            onChange={(event) => editor.changeDraft(event.target.value)}
            disabled={saving}
            spellCheck={false}
            style={editorStyle}
          />
        ) : !hasContent ? (
          <div style={emptyTextStyle}>No content available for this node.</div>
        ) : activeMode === "source" ? (
          <pre style={sourcePreStyle}>
            <code style={sourceCodeStyle}>{rawContent}</code>
          </pre>
        ) : (
          <div style={previewStyle}>{renderedMarkdown}</div>
        )}
      </div>
    </div>
  );
}

/* ─── Markdown rendering config ───────────────────────────────────── */

// Both props are hoisted to module scope so they keep a stable identity across
// renders. As inline literals they allocated a fresh plugin array and ~20 fresh
// arrow components on every render, which made React treat every mapped tag as a
// new element type and remount the entire rendered subtree instead of updating
// it (issue #1118). The arrow bodies only read the style constants below at call
// time, so declaring the map before them is safe.
const REMARK_PLUGINS = [remarkGfm];

const MARKDOWN_COMPONENTS: Components = {
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
};

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
  gap: 8,
  flexWrap: "wrap",
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

const saveBtnStyle: CSSProperties = {
  ...copyBtnStyle,
  background: GRAPH_THEME.ui.control.primaryBg,
  border: `1px solid ${GRAPH_THEME.ui.control.primaryBorder}`,
  color: GRAPH_THEME.ui.control.primaryText,
  fontWeight: 700,
};

const errorStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
  padding: "8px 12px",
  color: "#ffb4ad",
  background: "rgba(248, 81, 73, 0.1)",
  borderBottom: "1px solid rgba(248, 81, 73, 0.25)",
  fontSize: 12,
  lineHeight: 1.5,
};

const errorActionStyle: CSSProperties = {
  ...copyBtnStyle,
  flexShrink: 0,
  color: "#ffb4ad",
  border: "1px solid rgba(248, 81, 73, 0.32)",
};

const viewerBodyStyle: CSSProperties = {
  padding: 12,
  maxHeight: 380,
  overflowY: "auto",
};

const editorStyle: CSSProperties = {
  display: "block",
  boxSizing: "border-box",
  width: "100%",
  minHeight: 280,
  resize: "vertical",
  padding: 10,
  borderRadius: 8,
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  background: "rgba(0, 0, 0, 0.3)",
  color: GRAPH_THEME.ui.text.strong,
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  fontSize: 12,
  lineHeight: 1.6,
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
