import { useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  FileUp,
  Globe,
  Loader2,
  Plus,
  X,
} from "lucide-react";
import { useI18n } from "../../i18n";

type LoaderMode = "url" | "file" | "create";
type CreateMode = "scratch" | "data" | "text";

interface OntologyPreview {
  uri: string;
  name: string;
  description?: string;
  namespace?: string;
  version?: string;
  license?: string;
  format: string;
  estimated_triples: number;
  source_url?: string;
}

interface LoaderProps {
  onLoaded: () => void;
  onClose: () => void;
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.07em",
        textTransform: "uppercase" as const,
        background: `${color}18`,
        border: `1px solid ${color}33`,
        color,
      }}
    >
      {label}
    </span>
  );
}

function FieldGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={fieldLabelStyle}>{label}</label>
      {children}
    </div>
  );
}

function Input({
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={inputStyle}
    />
  );
}

function Textarea({
  value,
  onChange,
  placeholder,
  rows = 5,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      style={{ ...inputStyle, resize: "vertical", fontFamily: "monospace" }}
    />
  );
}

function PreviewCard({ preview }: { preview: OntologyPreview }) {
  const { t } = useI18n();
  return (
    <div style={previewCardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <CheckCircle2 size={16} color="#4cc38a" />
        <span style={{ color: "#4cc38a", fontSize: 12, fontWeight: 700 }}>
          {t('onto.previewReady')}
        </span>
        <Badge label={preview.format} color="#58a6ff" />
      </div>

      <div style={previewTitleStyle}>{preview.name}</div>
      {preview.description && (
        <div style={{ color: "#8fa8c6", fontSize: 12, marginTop: 6, lineHeight: 1.5 }}>
          {preview.description}
        </div>
      )}

      <div style={previewGridStyle}>
        <PreviewRow label={t('onto.ns')} value={preview.namespace || preview.uri} mono />
        {preview.version && <PreviewRow label={t('onto.version')} value={preview.version} />}
        {preview.license && <PreviewRow label={t('onto.license')} value={preview.license} />}
        <PreviewRow
          label={t('onto.estTriples')}
          value={preview.estimated_triples.toLocaleString()}
        />
      </div>
    </div>
  );
}

function PreviewRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ color: "#6a7f97", fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: "0.07em" }}>
        {label}
      </span>
      <span
        style={{
          color: "#c6d4e3",
          fontSize: 11,
          fontFamily: mono ? "monospace" : undefined,
          wordBreak: "break-all",
        }}
      >
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// URL Import panel
// ---------------------------------------------------------------------------

function URLImportPanel({ onLoaded }: { onLoaded: () => void }) {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [format, setFormat] = useState("");
  const [customName, setCustomName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [preview, setPreview] = useState<OntologyPreview | null>(null);
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "error">("idle");
  const [loadState, setLoadState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handlePreview = async () => {
    if (!url.trim()) return;
    setPreviewState("loading");
    setPreview(null);
    setErrorMsg("");
    try {
      const res = await fetch("/api/ontology/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), format: format || undefined }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail || "Preview failed");
      }
      setPreview(await res.json());
      setPreviewState("idle");
    } catch (e) {
      setPreviewState("error");
      setErrorMsg(e instanceof Error ? e.message : "Could not fetch preview");
    }
  };

  const handleLoad = async () => {
    if (!url.trim()) return;
    setLoadState("loading");
    try {
      const res = await fetch("/api/ontology/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          format: format || undefined,
          name: customName || undefined,
          description: description || undefined,
          tags: tags ? tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Load failed" }));
        throw new Error(err.detail || "Load failed");
      }
      setLoadState("success");
      setTimeout(() => {
        setLoadState("idle");
        onLoaded();
      }, 1200);
    } catch (e) {
      setLoadState("error");
      setErrorMsg(e instanceof Error ? e.message : "Load failed");
    }
  };

  return (
    <div style={panelBodyStyle}>
      <FieldGroup label={t('onto.urlLabel')}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setPreview(null);
              setPreviewState("idle");
            }}
            placeholder={t('onto.loadPlaceholder')}
            style={{ ...inputStyle, flex: 1 }}
          />
          <button
            onClick={handlePreview}
            disabled={!url.trim() || previewState === "loading"}
            style={previewBtnStyle}
          >
            {previewState === "loading" ? (
              <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
            ) : (
              t('onto.fetchPreview')
            )}
          </button>
        </div>
        <div style={{ color: "#5a7a9a", fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
          {t('onto.loadHint')}
        </div>
      </FieldGroup>

      {previewState === "error" && (
        <div style={errorBoxStyle}>
          <AlertCircle size={13} />
          <span>{errorMsg}</span>
        </div>
      )}

      {preview && <PreviewCard preview={preview} />}

      <button
        onClick={() => setShowAdvanced((v) => !v)}
        style={advancedToggleStyle}
      >
        <ChevronDown
          size={13}
          style={{ transform: showAdvanced ? "rotate(180deg)" : undefined, transition: "200ms" }}
        />
        {t('onto.advanced')}
      </button>

      {showAdvanced && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <FieldGroup label={t('onto.formatOverride')}>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              style={selectStyle}
            >
              <option value="">{t('onto.fmtAuto')}</option>
              <option value="turtle">{t('onto.fmtTurtle')}</option>
              <option value="xml">{t('onto.fmtXml')}</option>
              <option value="nt">{t('onto.fmtNt')}</option>
              <option value="json-ld">{t('onto.fmtJsonld')}</option>
            </select>
          </FieldGroup>
          <FieldGroup label={t('onto.customName')}>
            <Input value={customName} onChange={setCustomName} placeholder={t('onto.customNamePh')} />
          </FieldGroup>
          <FieldGroup label={t('onto.description')}>
            <Input value={description} onChange={setDescription} placeholder={t('onto.descriptionPh')} />
          </FieldGroup>
          <FieldGroup label={t('onto.tags')}>
            <Input value={tags} onChange={setTags} placeholder={t('onto.tagsPh')} />
          </FieldGroup>
        </div>
      )}

      {loadState === "success" && (
        <div style={successBoxStyle}>
          <CheckCircle2 size={13} />
          <span>{t('onto.loadedSuccess')}</span>
        </div>
      )}

      {loadState === "error" && (
        <div style={errorBoxStyle}>
          <AlertCircle size={13} />
          <span>{errorMsg}</span>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
        <button
          onClick={handleLoad}
          disabled={!url.trim() || loadState === "loading"}
          style={primaryBtnStyle}
        >
          {loadState === "loading" ? (
            <>
              <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
              {t('onto.loading')}
            </>
          ) : (
            <>
              <Globe size={13} />
              {t('onto.loadOntology')}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// File Upload panel
// ---------------------------------------------------------------------------

function FileUploadPanel({ onLoaded }: { onLoaded: () => void }) {
  const { t } = useI18n();
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [format, setFormat] = useState("");
  const [loadState, setLoadState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [dragging, setDragging] = useState(false);

  const handleFile = (file: File) => {
    setFileName(file.name);
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    const fmtMap: Record<string, string> = {
      ttl: "turtle", rdf: "xml", owl: "xml", xml: "xml",
      nt: "nt", jsonld: "json-ld", json: "json-ld",
    };
    // Leave format empty for unknown extensions so the backend auto-detects
    setFormat(fmtMap[ext] ?? "");
    const reader = new FileReader();
    reader.onload = (e) => setContent(e.target?.result as string || "");
    reader.readAsText(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleLoad = async () => {
    if (!content) return;
    setLoadState("loading");
    try {
      const res = await fetch("/api/ontology/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Omit format when empty so the backend _detect_format() runs
        body: JSON.stringify({ content, ...(format ? { format } : {}) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Load failed" }));
        throw new Error(err.detail || "Load failed");
      }
      setLoadState("success");
      setTimeout(() => {
        setLoadState("idle");
        onLoaded();
      }, 1200);
    } catch (e) {
      setLoadState("error");
      setErrorMsg(e instanceof Error ? e.message : "Load failed");
    }
  };

  return (
    <div style={panelBodyStyle}>
      <div
        style={{
          ...dropzoneStyle,
          borderColor: dragging
            ? "rgba(74,163,255,0.5)"
            : "rgba(127,208,255,0.18)",
          background: dragging ? "rgba(74,163,255,0.06)" : undefined,
        }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
      >
        <FileUp size={24} color="#4aa3ff" />
        {fileName ? (
          <div style={{ color: "#ebf3ff", fontSize: 13, fontWeight: 600 }}>{fileName}</div>
        ) : (
          <>
            <div style={{ color: "#8fa8c6", fontSize: 13 }}>
              {t('onto.dropFile', { browse: t('onto.browse') })}
            </div>
            <div style={{ color: "#5a7a9a", fontSize: 11 }}>
              .ttl · .rdf · .owl · .xml · .nt · .jsonld · .json · .n3
            </div>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept=".ttl,.rdf,.owl,.nt,.jsonld,.json,.xml,.n3"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
      </div>

      {content && (
        <FieldGroup label={t('onto.format')}>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            style={selectStyle}
          >
            <option value="turtle">{t('onto.fmtTurtle')}</option>
            <option value="xml">{t('onto.fmtXml')}</option>
            <option value="nt">{t('onto.fmtNt')}</option>
            <option value="json-ld">{t('onto.fmtJsonld')}</option>
          </select>
        </FieldGroup>
      )}

      {loadState === "success" && (
        <div style={successBoxStyle}>
          <CheckCircle2 size={13} />
          <span>{t('onto.loadedFileSuccess', { file: fileName })}</span>
        </div>
      )}

      {loadState === "error" && (
        <div style={errorBoxStyle}>
          <AlertCircle size={13} />
          <span>{errorMsg}</span>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button
          onClick={handleLoad}
          disabled={!content || loadState === "loading"}
          style={primaryBtnStyle}
        >
          {loadState === "loading" ? (
            <>
              <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
              {t('onto.loading')}
            </>
          ) : (
            <>
              <FileUp size={13} />
              {t('onto.loadFile')}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create New panel
// ---------------------------------------------------------------------------

function CreateNewPanel({ onLoaded }: { onLoaded: () => void }) {
  const { t } = useI18n();
  const [createMode, setCreateMode] = useState<CreateMode>("scratch");
  const [namespace, setNamespace] = useState("https://example.org/ontology/");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [sampleData, setSampleData] = useState("");
  const [schemaText, setSchemaText] = useState("");
  const [createState, setCreateState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const handleCreate = async () => {
    if (!name.trim() || !namespace.trim()) return;
    setCreateState("loading");
    try {
      const res = await fetch("/api/ontology/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: createMode,
          namespace: namespace.trim(),
          name: name.trim(),
          description: description || undefined,
          tags: tags ? tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
          sample_data: createMode === "data" ? sampleData : undefined,
          schema_text: createMode === "text" ? schemaText : undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Create failed" }));
        throw new Error(err.detail || "Create failed");
      }
      setCreateState("success");
      setTimeout(() => {
        setCreateState("idle");
        onLoaded();
      }, 1200);
    } catch (e) {
      setCreateState("error");
      setErrorMsg(e instanceof Error ? e.message : "Create failed");
    }
  };

  return (
    <div style={panelBodyStyle}>
      <div style={{ display: "flex", gap: 6 }}>
        {(["scratch", "data", "text"] as CreateMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setCreateMode(m)}
            style={{
              ...modeTabBase,
              ...(createMode === m ? modeTabActive : modeTabIdle),
            }}
          >
            {m === "scratch" ? t('onto.fromScratch') : m === "data" ? t('onto.fromData') : t('onto.fromText')}
          </button>
        ))}
      </div>

      <FieldGroup label={t('onto.displayName')}>
        <Input value={name} onChange={setName} placeholder={t('onto.createNamePh')} />
      </FieldGroup>

      <FieldGroup label={t('onto.namespaceUri')}>
        <Input value={namespace} onChange={setNamespace} placeholder="https://example.org/onto/" />
      </FieldGroup>

      <FieldGroup label={t('onto.description')}>
        <Input value={description} onChange={setDescription} placeholder={t('onto.descriptionPh')} />
      </FieldGroup>

      <FieldGroup label={t('onto.tags')}>
        <Input value={tags} onChange={setTags} placeholder={t('onto.tagsPh')} />
      </FieldGroup>

      {createMode === "data" && (
        <FieldGroup label={t('onto.sampleData')}>
          <Textarea
            value={sampleData}
            onChange={setSampleData}
            placeholder={'[{"name": "Alice", "age": 30, "city": "Berlin"}]'}
            rows={6}
          />
        </FieldGroup>
      )}

      {createMode === "text" && (
        <FieldGroup label={t('onto.schemaReq')}>
          <Textarea
            value={schemaText}
            onChange={setSchemaText}
            placeholder={t('onto.schemaReqPh')}
            rows={6}
          />
        </FieldGroup>
      )}

      {createState === "success" && (
        <div style={successBoxStyle}>
          <CheckCircle2 size={13} />
          <span>{t('onto.createdSuccess')}</span>
        </div>
      )}

      {createState === "error" && (
        <div style={errorBoxStyle}>
          <AlertCircle size={13} />
          <span>{errorMsg}</span>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button
          onClick={handleCreate}
          disabled={!name.trim() || !namespace.trim() || createState === "loading"}
          style={primaryBtnStyle}
        >
          {createState === "loading" ? (
            <>
              <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
              {t('onto.creating')}
            </>
          ) : (
            <>
              <Plus size={13} />
              {t('onto.createOntology')}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main OntologyLoader modal
// ---------------------------------------------------------------------------

export function OntologyLoader({ onLoaded, onClose }: LoaderProps) {
  const { t } = useI18n();
  const [mode, setMode] = useState<LoaderMode>("url");

  return (
    <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={modalStyle}>
        <div style={modalHeaderStyle}>
          <div>
            <div style={{ color: "#ebf3ff", fontSize: 16, fontWeight: 800 }}>{t('onto.loaderTitle')}</div>
            <div style={{ color: "#8fa8c6", fontSize: 12, marginTop: 2 }}>
              {t('onto.loaderSubtitle')}
            </div>
          </div>
          <button onClick={onClose} style={closeIconBtnStyle}>
            <X size={16} />
          </button>
        </div>

        <div style={{ display: "flex", gap: 2, padding: "0 20px", borderBottom: "1px solid rgba(127,208,255,0.1)" }}>
          {(["url", "file", "create"] as LoaderMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                ...modalTabBase,
                ...(mode === m ? modalTabActive : modalTabIdle),
              }}
            >
              {m === "url" ? (
                <><Globe size={12} /> {t('onto.loaderTabUrl')}</>
              ) : m === "file" ? (
                <><FileUp size={12} /> {t('onto.loaderTabFile')}</>
              ) : (
                <><Plus size={12} /> {t('onto.loaderTabCreate')}</>
              )}
            </button>
          ))}
        </div>

        <div style={modalBodyStyle}>
          {mode === "url" && <URLImportPanel onLoaded={onLoaded} />}
          {mode === "file" && <FileUploadPanel onLoaded={onLoaded} />}
          {mode === "create" && <CreateNewPanel onLoaded={onLoaded} />}
        </div>
      </div>
    </div>
  );
}

/* ─── styles ─────────────────────────────────────────────────────────── */

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(3,9,18,0.78)",
  backdropFilter: "blur(6px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  width: "min(620px, 96vw)",
  maxHeight: "88vh",
  display: "flex",
  flexDirection: "column",
  borderRadius: 20,
  border: "1px solid rgba(127,208,255,0.16)",
  background: "linear-gradient(180deg, rgba(11,21,34,0.98), rgba(6,13,22,0.96))",
  boxShadow: "0 32px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)",
  overflow: "hidden",
};

const modalHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  padding: "20px 20px 16px",
};

const modalBodyStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
};

const panelBodyStyle: React.CSSProperties = {
  padding: "16px 20px 20px",
  display: "flex",
  flexDirection: "column",
  gap: 14,
};

const modalTabBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "8px 14px",
  border: "none",
  borderBottom: "2px solid transparent",
  background: "transparent",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 600,
  transition: "160ms ease",
};

const modalTabIdle: React.CSSProperties = {
  color: "#8fa8c6",
};

const modalTabActive: React.CSSProperties = {
  color: "#4aa3ff",
  borderBottomColor: "#4aa3ff",
};

const closeIconBtnStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "#8fa8c6",
  cursor: "pointer",
  padding: 4,
  borderRadius: 8,
  display: "grid",
  placeItems: "center",
};

const fieldLabelStyle: React.CSSProperties = {
  color: "#8fa8c6",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.05em",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid rgba(127,208,255,0.16)",
  background: "rgba(0,0,0,0.24)",
  color: "#ebf3ff",
  fontSize: 13,
  outline: "none",
  boxSizing: "border-box",
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  appearance: "none" as const,
  cursor: "pointer",
};

const previewBtnStyle: React.CSSProperties = {
  padding: "8px 14px",
  borderRadius: 8,
  border: "1px solid rgba(127,208,255,0.2)",
  background: "rgba(74,163,255,0.08)",
  color: "#7fd0ff",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
};

const primaryBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 7,
  padding: "9px 18px",
  borderRadius: 10,
  border: "1px solid rgba(74,163,255,0.3)",
  background: "linear-gradient(135deg, rgba(74,163,255,0.2), rgba(74,163,255,0.1))",
  color: "#7fd0ff",
  fontSize: 13,
  fontWeight: 700,
  cursor: "pointer",
};

const advancedToggleStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  background: "transparent",
  border: "none",
  color: "#6a7f97",
  fontSize: 12,
  cursor: "pointer",
  padding: 0,
};

const previewCardStyle: React.CSSProperties = {
  padding: 14,
  borderRadius: 10,
  border: "1px solid rgba(76,195,138,0.18)",
  background: "rgba(76,195,138,0.04)",
};

const previewTitleStyle: React.CSSProperties = {
  color: "#ebf3ff",
  fontSize: 15,
  fontWeight: 800,
  letterSpacing: "-0.03em",
};

const previewGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 10,
  marginTop: 12,
};

const dropzoneStyle: React.CSSProperties = {
  border: "2px dashed",
  borderRadius: 12,
  padding: "32px 20px",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 10,
  cursor: "pointer",
  transition: "160ms ease",
};

const successBoxStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid rgba(76,195,138,0.22)",
  background: "rgba(76,195,138,0.06)",
  color: "#4cc38a",
  fontSize: 12,
};

const errorBoxStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid rgba(255,157,175,0.22)",
  background: "rgba(255,157,175,0.06)",
  color: "#ff9daf",
  fontSize: 12,
};

const modeTabBase: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: 8,
  border: "1px solid transparent",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 600,
};

const modeTabIdle: React.CSSProperties = {
  background: "transparent",
  color: "#8fa8c6",
  borderColor: "rgba(127,208,255,0.1)",
};

const modeTabActive: React.CSSProperties = {
  background: "rgba(74,163,255,0.14)",
  color: "#ebf3ff",
  borderColor: "rgba(127,208,255,0.24)",
};
