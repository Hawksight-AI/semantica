import { useCallback, useEffect, useState } from "react";
import {
  BookMarked,
  GitMerge,
  HeartPulse,
  Layers,
  Shield,
  Sliders,
} from "lucide-react";
import { AlignmentsTab } from "./AlignmentsTab";
import { HealthTab } from "./HealthTab";
import { OntologyManager } from "./OntologyManager";
import { OntologyEditor } from "./OntologyEditor";
import { ShaclStudio } from "./ShaclStudio";
import { VersionsTab } from "./VersionsTab";
import { readOntologyUrlState, writeEntitySelection, writeTab } from "./ontologyUrlState";

export type OntologyHubTab =
  | "registry"
  | "editor"
  | "versions"
  | "alignments"
  | "health"
  | "shacl";

const TABS: { id: OntologyHubTab; label: string; icon: typeof GitMerge }[] = [
  { id: "registry", label: "Registry", icon: BookMarked },
  { id: "editor", label: "Editor", icon: Sliders },
  { id: "versions", label: "Versions", icon: Layers },
  { id: "alignments", label: "Alignments", icon: GitMerge },
  { id: "health", label: "Health", icon: HeartPulse },
  { id: "shacl", label: "SHACL", icon: Shield },
];

function readInitialTab(): OntologyHubTab {
  const { tab, entityUri } = readOntologyUrlState();
  const requested = TABS.find((candidate) => candidate.id === tab);
  if (requested) return requested.id;
  if (entityUri) return "editor";
  return "registry";
}

interface OntologyWorkspaceProps {
  onJumpToGraphNode?: (nodeId: string) => void;
}

export function OntologyWorkspace({ onJumpToGraphNode }: OntologyWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<OntologyHubTab>(readInitialTab);

  useEffect(() => {
    writeTab(activeTab);
  }, [activeTab]);

  const handleTabChange = useCallback((tab: OntologyHubTab) => {
    setActiveTab(tab);
  }, []);

  const handleFixInEditor = useCallback((entityUri: string) => {
    writeEntitySelection(entityUri);
    setActiveTab("editor");
  }, []);

  const renderTab = () => {
    switch (activeTab) {
      case "registry":
        return <OntologyManager />;
      case "editor":
        return <OntologyEditor />;
      case "versions":
        return <VersionsTab />;
      case "alignments":
        return <AlignmentsTab />;
      case "health":
        return <HealthTab onFixInEditor={handleFixInEditor} />;
      case "shacl":
        return <ShaclStudio onJumpToNode={onJumpToGraphNode} />;
    }
  };

  return (
    <div className="ws-page">
      {/* Internal sub-tab bar */}
      <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid var(--ws-border)", background: "rgba(0,0,0,0.18)", flexShrink: 0, flexWrap: "wrap" }}>
        {TABS.map(({ id, label, icon: Icon }) => {
          const active = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => handleTabChange(id)}
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 13px", borderRadius: 999, border: `1px solid ${active ? "var(--ws-border-strong)" : "transparent"}`, background: active ? "var(--ws-accent-soft)" : "transparent", color: active ? "var(--ws-text)" : "var(--ws-text-muted)", fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "160ms ease" }}
            >
              <Icon size={13} />
              {label}
            </button>
          );
        })}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>{renderTab()}</div>
    </div>
  );
}
