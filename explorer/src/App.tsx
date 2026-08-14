import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  ArrowRight,
  BrainCircuit,
  Database,
  FileSearch,
  GitBranchPlus,
  GitMerge,
  Network,
  Radar,
  Route,
  Scale,
  Search,
  Settings2,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { ErrorBoundary } from './ErrorBoundary';

const DecisionWorkspace = lazy(() => import('./workspaces/DecisionWorkspace/DecisionWorkspace').then((module) => ({ default: module.DecisionWorkspace })));
const DiffMergeWorkspace = lazy(() => import('./workspaces/DiffMergeWorkspace/DiffMergeWorkspace').then((module) => ({ default: module.DiffMergeWorkspace })));
const GraphWorkspace = lazy(() => import('./workspaces/GraphWorkspace/GraphWorkspace').then((module) => ({ default: module.GraphWorkspace })));
const ImportExportWorkspace = lazy(() => import('./workspaces/ImportExportWorkspace/ImportExportWorkspace').then((module) => ({ default: module.ImportExportWorkspace })));
const LineageDiagram = lazy(() => import('./workspaces/LineageWorkspace/LineageDiagram').then((module) => ({ default: module.LineageDiagram })));
const ReasoningWorkspace = lazy(() => import('./workspaces/ReasoningWorkspace').then((module) => ({ default: module.ReasoningWorkspace })));
const SparqlWorkspace = lazy(() => import('./workspaces/SparqlWorkspace/SparqlWorkspace').then((module) => ({ default: module.SparqlWorkspace })));
const VocabularyWorkspace = lazy(() => import('./workspaces/VocabularyWorkspace/VocabularyWorkspace').then((module) => ({ default: module.VocabularyWorkspace })));
const RegistryTab = lazy(() => import('./workspaces/EnrichWorkspace/RegistryTab').then((module) => ({ default: module.RegistryTab })));
const EntityResolutionTab = lazy(() => import('./workspaces/EnrichWorkspace/EntityResolutionTab').then((module) => ({ default: module.EntityResolutionTab })));
const KGOverviewTab = lazy(() => import('./workspaces/ManageWorkspace/KGOverviewTab').then((module) => ({ default: module.KGOverviewTab })));
const OntologySummaryTab = lazy(() => import('./workspaces/ManageWorkspace/OntologySummaryTab').then((module) => ({ default: module.OntologySummaryTab })));
const OntologyWorkspace = lazy(() => import('./workspaces/OntologyWorkspace').then((module) => ({ default: module.OntologyWorkspace })));

type WorkspaceId = 'welcome' | 'explore' | 'analyze' | 'decisions' | 'enrich' | 'manage' | 'ontology-hub';
type ExploreView = 'graph' | 'vocabulary';
type AnalyzeView = 'sparql' | 'reasoning';
type EnrichView = 'import' | 'merge' | 'registry' | 'resolve';
type ManageView = 'lineage' | 'kg-overview' | 'ontology';

type NavItem = {
  id: WorkspaceId;
  label: string;
  hint: string;
  icon: LucideIcon;
};

type LandingMetric = {
  label: string;
  value: string;
  tone?: 'cyan' | 'mint' | 'amber' | 'rose';
};

type LandingAction = {
  label: string;
  description: string;
  icon: LucideIcon;
  onClick: () => void;
};

type GraphStatsPayload = {
  node_count?: number;
  edge_count?: number;
  nodeCount?: number;
  edgeCount?: number;
  nodes?: number;
  edges?: number;
};

type ConnectionStatus = 'checking' | 'online' | 'offline';

const CONNECTION_STATUS_LABEL: Record<ConnectionStatus, string> = {
  checking: 'Connecting…',
  online: 'System Online',
  offline: 'Backend Unreachable',
};

const queryClient = new QueryClient();

const PREVIEW_DOTS = Array.from({ length: 42 }, (_, i) => ({
  cx: 170 + ((i * 73) % 330),
  cy: 170 + ((i * 47) % 210),
  r: 2 + (i % 3),
  fill: (['#56d364', '#58a6ff', '#f2b66d', '#ff9daf'] as const)[i % 4],
}));

const navItems: NavItem[] = [
  { id: 'explore', label: 'Knowledge Explorer', hint: 'Graph and vocabulary browsing', icon: Database },
  { id: 'analyze', label: 'Analyze', hint: 'Query and inspect the dataset', icon: FileSearch },
  { id: 'decisions', label: 'Decisions', hint: 'Decision chains and precedent review', icon: Scale },
  { id: 'enrich', label: 'Enrich', hint: 'Import, export, and merge workflows', icon: GitBranchPlus },
  { id: 'manage', label: 'Manage', hint: 'Lineage and governance tooling', icon: Settings2 },
  { id: 'ontology-hub', label: 'Ontology Hub', hint: 'Schema governance, registry, and vocabulary management', icon: GitMerge },
];

const shellStyles = `
  :root {
    --app-bg: #07111f;
    --panel-bg: rgba(7, 17, 31, 0.82);
    --panel-border: rgba(140, 192, 255, 0.14);
    --text-main: #ebf3ff;
    --text-muted: #8fa8c6;
    --accent: #4aa3ff;
    --accent-strong: #7fd0ff;
    --warm: #f2b66d;
    --success: #4cc38a;

    /* ── Shared workspace design tokens ── */
    --ws-bg: #060d1a;
    --ws-surface: rgba(255,255,255,0.028);
    --ws-surface-hover: rgba(74,163,255,0.07);
    --ws-border: rgba(74,163,255,0.13);
    --ws-border-strong: rgba(74,163,255,0.26);
    --ws-text: #ddeeff;
    --ws-text-muted: #5a7a9a;
    --ws-text-dim: #3a5570;
    --ws-accent: #4aa3ff;
    --ws-accent-soft: rgba(74,163,255,0.12);
    --ws-green: #4cc38a;
    --ws-green-soft: rgba(76,195,138,0.12);
    --ws-amber: #f2b66d;
    --ws-amber-soft: rgba(242,182,109,0.12);
    --ws-red: #ff7b72;
    --ws-red-soft: rgba(255,123,114,0.12);
    --ws-purple: #c084fc;
    --ws-purple-soft: rgba(192,132,252,0.1);
    --ws-radius: 14px;
    --ws-radius-sm: 8px;
    --ws-radius-lg: 20px;
  }

  /* ── Shared workspace primitives (available to all workspace components) ── */
  .ws-page {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: var(--ws-bg);
    overflow: hidden;
  }

  .ws-scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: thin;
    scrollbar-color: var(--ws-border) transparent;
  }

  .ws-padded {
    padding: 24px 28px;
  }

  .ws-split {
    display: grid;
    height: 100%;
    overflow: hidden;
  }

  .ws-split--2col { grid-template-columns: 300px 1fr; }
  .ws-split--half { grid-template-columns: 1fr 1fr; }
  .ws-split--rows { grid-template-rows: 1fr auto; }

  .ws-panel {
    background: var(--ws-surface);
    border: 1px solid var(--ws-border);
    border-radius: var(--ws-radius);
    overflow: hidden;
  }

  .ws-panel--inset {
    background: rgba(0,0,0,0.22);
    border: 1px solid rgba(74,163,255,0.09);
    border-radius: var(--ws-radius);
  }

  .ws-card {
    background: var(--ws-surface);
    border: 1px solid var(--ws-border);
    border-radius: var(--ws-radius);
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: border-color 180ms ease, background 180ms ease;
  }

  .ws-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(74,163,255,0.18), transparent);
  }

  .ws-card:hover {
    border-color: var(--ws-border-strong);
    background: var(--ws-surface-hover);
  }

  .ws-eyebrow {
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ws-text-muted);
  }

  .ws-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ws-text-muted);
    margin-bottom: 8px;
    display: block;
  }

  .ws-title {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.035em;
    color: var(--ws-text);
    margin: 0;
  }

  .ws-body {
    font-size: 13px;
    line-height: 1.65;
    color: var(--ws-text-muted);
  }

  .ws-btn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 9px 16px;
    border-radius: var(--ws-radius-sm);
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: 160ms ease;
    border: 1px solid transparent;
  }

  .ws-btn--primary {
    background: linear-gradient(135deg, rgba(74,163,255,0.28), rgba(56,210,160,0.16));
    border-color: rgba(74,163,255,0.4);
    color: #e8f6ff;
    box-shadow: 0 0 0 1px rgba(74,163,255,0.08) inset;
  }

  .ws-btn--primary:hover:not(:disabled) {
    background: linear-gradient(135deg, rgba(74,163,255,0.4), rgba(56,210,160,0.24));
    border-color: rgba(74,163,255,0.6);
    box-shadow: 0 6px 20px rgba(74,163,255,0.18);
    transform: translateY(-1px);
  }

  .ws-btn--ghost {
    background: rgba(255,255,255,0.04);
    border-color: var(--ws-border);
    color: var(--ws-text-muted);
  }

  .ws-btn--ghost:hover:not(:disabled) {
    background: var(--ws-surface-hover);
    border-color: var(--ws-border-strong);
    color: var(--ws-text);
  }

  .ws-btn--danger {
    background: var(--ws-red-soft);
    border-color: rgba(255,123,114,0.3);
    color: #ff9e97;
  }

  .ws-btn--success {
    background: var(--ws-green-soft);
    border-color: rgba(76,195,138,0.3);
    color: #6ee7b7;
  }

  .ws-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    transform: none !important;
  }

  .ws-input {
    width: 100%;
    padding: 9px 12px;
    background: rgba(0,0,0,0.28);
    border: 1px solid var(--ws-border);
    border-radius: var(--ws-radius-sm);
    color: var(--ws-text);
    font-size: 13px;
    outline: none;
    transition: border-color 160ms ease;
    box-sizing: border-box;
  }

  .ws-input:focus {
    border-color: var(--ws-accent);
    box-shadow: 0 0 0 3px rgba(74,163,255,0.1);
  }

  .ws-textarea {
    width: 100%;
    padding: 12px;
    background: rgba(0,0,0,0.28);
    border: 1px solid var(--ws-border);
    border-radius: var(--ws-radius-sm);
    color: var(--ws-text);
    font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 12.5px;
    line-height: 1.7;
    resize: vertical;
    outline: none;
    transition: border-color 160ms ease;
    box-sizing: border-box;
  }

  .ws-textarea:focus {
    border-color: var(--ws-accent);
    box-shadow: 0 0 0 3px rgba(74,163,255,0.1);
  }

  .ws-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }

  .ws-pill--accent { color: #7fd0ff; background: var(--ws-accent-soft); border: 1px solid rgba(74,163,255,0.22); }
  .ws-pill--green  { color: #6ee7b7; background: var(--ws-green-soft);  border: 1px solid rgba(76,195,138,0.28); }
  .ws-pill--amber  { color: #fbbf24; background: var(--ws-amber-soft);  border: 1px solid rgba(242,182,109,0.28); }
  .ws-pill--red    { color: #fca5a5; background: var(--ws-red-soft);    border: 1px solid rgba(255,123,114,0.28); }
  .ws-pill--purple { color: #d8b4fe; background: var(--ws-purple-soft); border: 1px solid rgba(192,132,252,0.22); }
  .ws-pill--mono   { color: var(--ws-text-muted); background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); }

  .ws-divider {
    height: 1px;
    background: var(--ws-border);
    margin: 0;
  }

  .ws-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 48px 24px;
    gap: 10px;
    color: var(--ws-text-muted);
  }

  .ws-empty-icon { opacity: 0.35; margin-bottom: 4px; }
  .ws-empty-title { font-size: 14px; font-weight: 700; color: var(--ws-text); }
  .ws-empty-body { font-size: 12px; line-height: 1.5; max-width: 36ch; }

  .ws-sidebar {
    border-right: 1px solid var(--ws-border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: rgba(0,0,0,0.12);
  }

  .ws-sidebar-header {
    padding: 18px 16px 14px;
    border-bottom: 1px solid var(--ws-border);
    flex-shrink: 0;
  }

  .ws-sidebar-body {
    flex: 1;
    overflow-y: auto;
    padding: 10px 10px;
    scrollbar-width: thin;
    scrollbar-color: var(--ws-border) transparent;
  }

  .ws-list-item {
    width: 100%;
    text-align: left;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--ws-text-muted);
    cursor: pointer;
    transition: 140ms ease;
    display: block;
  }

  .ws-list-item:hover {
    background: var(--ws-surface);
    border-color: var(--ws-border);
    color: var(--ws-text);
  }

  .ws-list-item--active {
    background: var(--ws-accent-soft);
    border-color: var(--ws-border-strong);
    color: #e8f6ff;
  }

  .ws-stat-grid {
    display: grid;
    gap: 12px;
  }

  .ws-stat-grid--3 { grid-template-columns: repeat(3, 1fr); }
  .ws-stat-grid--4 { grid-template-columns: repeat(4, 1fr); }
  .ws-stat-grid--2 { grid-template-columns: repeat(2, 1fr); }

  .ws-stat-card {
    padding: 18px 20px;
    border-radius: var(--ws-radius);
    border: 1px solid var(--ws-border);
    background: var(--ws-surface);
    position: relative;
    overflow: hidden;
  }

  .ws-stat-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(74,163,255,0.2), transparent);
  }

  .ws-stat-value {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: var(--ws-text);
    line-height: 1;
  }

  .ws-stat-label {
    margin-top: 6px;
    font-size: 11px;
    font-weight: 600;
    color: var(--ws-text-dim);
    letter-spacing: 0.04em;
  }

  @keyframes ws-spin { to { transform: rotate(360deg); } }
  .ws-spin { animation: ws-spin 0.8s linear infinite; }

  @keyframes ws-skeleton {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.7; }
  }

  .ws-skeleton {
    background: rgba(255,255,255,0.06);
    border-radius: 8px;
    animation: ws-skeleton 1.4s ease-in-out infinite;
  }

  @keyframes ws-slide-up {
    from { opacity: 0; transform: translateY(14px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .ws-animate-in { animation: ws-slide-up 0.22s ease both; }

  .app-shell {
    display: flex;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    color: var(--text-main);
    background:
      radial-gradient(circle at top left, rgba(74, 163, 255, 0.12), transparent 32%),
      radial-gradient(circle at bottom right, rgba(242, 182, 109, 0.08), transparent 26%),
      linear-gradient(180deg, #091322 0%, #050b15 100%);
    font-family: "Segoe UI", "SF Pro Display", sans-serif;
  }

  .app-rail {
    width: 88px;
    padding: 20px 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-right: 1px solid var(--panel-border);
    background: rgba(3, 9, 18, 0.92);
    backdrop-filter: blur(18px);
  }

  .brand-pill {
    width: 100%;
    min-height: 56px;
    border-radius: 18px;
    display: grid;
    place-items: center;
    color: var(--text-main);
    background: linear-gradient(135deg, rgba(74, 163, 255, 0.22), rgba(127, 208, 255, 0.08));
    border: 1px solid rgba(127, 208, 255, 0.18);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
  }

  .nav-button {
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-muted);
    border-radius: 18px;
    min-height: 72px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    cursor: pointer;
    transition: 160ms ease;
  }

  .nav-button:hover {
    color: var(--text-main);
    background: rgba(74, 163, 255, 0.08);
    border-color: rgba(74, 163, 255, 0.12);
  }

  .nav-button[data-active='true'] {
    color: var(--text-main);
    background: linear-gradient(180deg, rgba(74, 163, 255, 0.18), rgba(74, 163, 255, 0.08));
    border-color: rgba(127, 208, 255, 0.22);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
  }

  .nav-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  .workspace-shell {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .workspace-header {
    padding: 14px 22px;
    border-bottom: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(7, 17, 31, 0.94), rgba(7, 17, 31, 0.82));
    backdrop-filter: blur(18px);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    min-height: 68px;
  }

  .workspace-header--compact {
    min-height: 60px;
    padding: 10px 18px;
    background: linear-gradient(180deg, rgba(7, 17, 31, 0.92), rgba(7, 17, 31, 0.72));
  }

  .workspace-header--compact .workspace-title {
    font-size: 16px;
  }

  .workspace-header--compact .workspace-subtitle {
    font-size: 11px;
  }

  .workspace-header-main {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .workspace-kicker {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 999px;
    background: rgba(74, 163, 255, 0.08);
    border: 1px solid rgba(127, 208, 255, 0.14);
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .workspace-kicker::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: linear-gradient(135deg, var(--accent-strong), var(--warm));
    box-shadow: 0 0 14px rgba(127, 208, 255, 0.45);
  }

  .workspace-title-block {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .workspace-title {
    margin: 0;
    font-size: 20px;
    line-height: 1;
    letter-spacing: -0.03em;
  }

  .workspace-subtitle {
    color: var(--text-muted);
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .workspace-tabs {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .workspace-tab {
    border: 1px solid rgba(127, 208, 255, 0.18);
    background: rgba(9, 19, 34, 0.56);
    color: var(--text-muted);
    border-radius: 999px;
    padding: 8px 12px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    transition: 160ms ease;
    white-space: nowrap;
  }

  .workspace-tab[data-active='true'] {
    color: var(--text-main);
    background: rgba(74, 163, 255, 0.16);
    border-color: rgba(127, 208, 255, 0.3);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
  }

  .workspace-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  /* ── Welcome page ─────────────────────────────────────── */
  .landing-page {
    position: relative;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    background:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(74, 163, 255, 0.18) 0%, transparent 60%),
      radial-gradient(ellipse 60% 40% at 80% 90%, rgba(242, 182, 109, 0.1) 0%, transparent 50%),
      linear-gradient(180deg, #060d1a 0%, #03070f 100%);
    scrollbar-width: thin;
    scrollbar-color: rgba(74,163,255,0.18) transparent;
  }

  .landing-page::before {
    content: "";
    position: fixed;
    inset: 0 0 0 88px;
    pointer-events: none;
    background:
      repeating-linear-gradient(0deg, transparent, transparent 79px, rgba(74,163,255,0.035) 80px),
      repeating-linear-gradient(90deg, transparent, transparent 79px, rgba(74,163,255,0.025) 80px);
    mask-image: radial-gradient(ellipse 90% 80% at 50% 20%, black 30%, transparent 100%);
  }

  .landing-shell {
    position: relative;
    z-index: 1;
    width: min(1360px, 100%);
    margin: 0 auto;
    padding: clamp(28px, 4vw, 56px) clamp(20px, 3vw, 48px);
    display: flex;
    flex-direction: column;
    gap: 56px;
  }

  /* ── Hero ──────────────────────────────────────────────── */
  .landing-hero {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(380px, 520px);
    gap: clamp(24px, 3vw, 48px);
    align-items: center;
    min-height: min(580px, calc(100vh - 140px));
  }

  .landing-copy {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .landing-status-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 24px;
    --status-color: #4cc38a;
    --status-shadow-a: 0 0 0 3px rgba(76, 195, 138, 0.22), 0 0 12px rgba(76, 195, 138, 0.5);
    --status-shadow-b: 0 0 0 5px rgba(76, 195, 138, 0.1), 0 0 20px rgba(76, 195, 138, 0.35);
  }

  .landing-status-bar[data-status='checking'] {
    --status-color: #f2b66d;
    --status-shadow-a: 0 0 0 3px rgba(242, 182, 109, 0.22), 0 0 12px rgba(242, 182, 109, 0.5);
    --status-shadow-b: 0 0 0 5px rgba(242, 182, 109, 0.1), 0 0 20px rgba(242, 182, 109, 0.35);
  }

  .landing-status-bar[data-status='offline'] {
    --status-color: #ff7b72;
    --status-shadow-a: 0 0 0 3px rgba(255, 123, 114, 0.22), 0 0 12px rgba(255, 123, 114, 0.5);
    --status-shadow-b: 0 0 0 5px rgba(255, 123, 114, 0.1), 0 0 20px rgba(255, 123, 114, 0.35);
  }

  .landing-status-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--status-color);
    box-shadow: var(--status-shadow-a);
    animation: landing-pulse 2.4s ease-in-out infinite;
  }

  .landing-status-text {
    color: var(--status-color);
    font: 700 11px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .landing-status-divider {
    width: 1px;
    height: 14px;
    background: rgba(158, 217, 255, 0.2);
  }

  .landing-status-version {
    color: #5a7a9a;
    font: 600 11px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.06em;
  }

  .landing-kicker {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 5px 12px 5px 8px;
    border-radius: 999px;
    border: 1px solid rgba(74, 163, 255, 0.3);
    background: rgba(74, 163, 255, 0.08);
    color: #7fd0ff;
    font: 700 11px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    width: fit-content;
    margin-bottom: 20px;
  }

  .landing-kicker-mark {
    width: 16px;
    height: 16px;
    border-radius: 6px;
    background: linear-gradient(135deg, #4aa3ff, #56d3a0);
    display: grid;
    place-items: center;
    flex: 0 0 auto;
  }

  .landing-kicker-node { display: none; }

  .landing-kicker-mark::after {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: rgba(3, 10, 20, 0.8);
  }

  .landing-title {
    margin: 0 0 20px;
    color: #f0f7ff;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: clamp(38px, 4.8vw, 72px);
    line-height: 1.08;
    letter-spacing: -0.04em;
    font-weight: 800;
  }

  .landing-title span {
    color: transparent;
    background: linear-gradient(100deg, #7fd0ff 0%, #4cc38a 50%, #f2b66d 100%);
    -webkit-background-clip: text;
    background-clip: text;
  }

  .landing-subtitle {
    margin: 0 0 32px;
    color: #7a99b8;
    font-size: clamp(14px, 1.2vw, 17px);
    line-height: 1.7;
    max-width: 54ch;
  }

  .landing-cta-row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .landing-cta-primary {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 22px;
    border-radius: 12px;
    border: 1px solid rgba(74, 163, 255, 0.5);
    background: linear-gradient(135deg, rgba(74, 163, 255, 0.28), rgba(56, 210, 160, 0.18));
    color: #e8f6ff;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    transition: 180ms ease;
    box-shadow: 0 0 0 1px rgba(74, 163, 255, 0.1) inset, 0 8px 24px rgba(74, 163, 255, 0.15);
  }

  .landing-cta-primary:hover {
    transform: translateY(-2px);
    background: linear-gradient(135deg, rgba(74, 163, 255, 0.38), rgba(56, 210, 160, 0.26));
    box-shadow: 0 0 0 1px rgba(74, 163, 255, 0.18) inset, 0 14px 32px rgba(74, 163, 255, 0.22);
  }

  .landing-cta-secondary {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 18px;
    border-radius: 12px;
    border: 1px solid rgba(158, 217, 255, 0.14);
    background: rgba(255, 255, 255, 0.04);
    color: #8fafc8;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: 180ms ease;
  }

  .landing-cta-secondary:hover {
    border-color: rgba(158, 217, 255, 0.26);
    color: #c5dcef;
    background: rgba(255, 255, 255, 0.07);
  }

  /* ── Preview panel ─────────────────────────────────────── */
  .landing-preview {
    position: relative;
    overflow: hidden;
    border-radius: 24px;
    border: 1px solid rgba(74, 163, 255, 0.18);
    background:
      radial-gradient(circle at 40% 30%, rgba(74, 163, 255, 0.14), transparent 46%),
      radial-gradient(circle at 70% 70%, rgba(242, 182, 109, 0.1), transparent 38%),
      linear-gradient(145deg, rgba(8, 17, 28, 0.96), rgba(3, 8, 14, 0.88));
    box-shadow: 0 24px 72px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255,255,255,0.04) inset;
    aspect-ratio: 4/3.2;
    min-height: 340px;
  }

  .landing-preview-topbar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 38px;
    background: rgba(4, 10, 18, 0.82);
    border-bottom: 1px solid rgba(74, 163, 255, 0.1);
    backdrop-filter: blur(12px);
    display: flex;
    align-items: center;
    padding: 0 14px;
    gap: 8px;
  }

  .landing-preview-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
  }

  .landing-preview-dot:nth-child(1) { background: rgba(255, 95, 86, 0.7); }
  .landing-preview-dot:nth-child(2) { background: rgba(255, 189, 46, 0.7); }
  .landing-preview-dot:nth-child(3) { background: rgba(39, 201, 63, 0.7); }

  .landing-preview-tab {
    margin-left: 12px;
    padding: 3px 10px;
    border-radius: 6px;
    background: rgba(74, 163, 255, 0.12);
    border: 1px solid rgba(74, 163, 255, 0.2);
    color: #7fd0ff;
    font: 600 10px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.06em;
  }

  .landing-preview-orbit {
    position: absolute;
    inset: 38px 0 0;
    opacity: 0.95;
  }

  .landing-preview-orbit svg {
    width: 100%;
    height: 100%;
    overflow: visible;
  }

  .landing-preview-line {
    stroke: rgba(74, 163, 255, 0.3);
    stroke-width: 1.2;
    fill: none;
    stroke-dasharray: 4 3;
  }

  .landing-preview-line--warm {
    stroke: rgba(242, 182, 109, 0.3);
  }

  .landing-preview-line--mint {
    stroke: rgba(76, 195, 138, 0.28);
  }

  .landing-node {
    transform-origin: center;
    animation: landing-float 7s ease-in-out infinite;
  }

  .landing-node:nth-child(2n) { animation-delay: -2.2s; }
  .landing-node:nth-child(3n) { animation-delay: -4.1s; }

  .landing-command-card,
  .landing-dossier-card,
  .landing-timeline-card {
    position: absolute;
    border: 1px solid rgba(74, 163, 255, 0.16);
    background: rgba(3, 9, 18, 0.84);
    backdrop-filter: blur(20px);
    box-shadow: 0 12px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04) inset;
  }

  .landing-command-card {
    top: 50px;
    left: 16px;
    right: 16px;
    border-radius: 14px;
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .landing-command-icon {
    width: 32px;
    height: 32px;
    border-radius: 10px;
    display: grid;
    place-items: center;
    color: #56d3a0;
    background: rgba(76, 195, 138, 0.1);
    border: 1px solid rgba(76, 195, 138, 0.2);
    flex: 0 0 auto;
  }

  .landing-command-label {
    color: #c8dff0;
    font-size: 12px;
    font-weight: 700;
  }

  .landing-command-meta {
    margin-top: 2px;
    color: #4a6a85;
    font: 500 10px/1 "JetBrains Mono", monospace;
  }

  .landing-dossier-card {
    right: 14px;
    bottom: 80px;
    width: min(210px, calc(100% - 28px));
    border-radius: 16px;
    padding: 14px;
  }

  .landing-dossier-kicker {
    color: #56d3a0;
    font: 700 9px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .landing-dossier-title {
    margin-top: 6px;
    color: #e8f4ff;
    font: 800 20px/1 "Inter", sans-serif;
    letter-spacing: -0.04em;
  }

  .landing-dossier-row {
    margin-top: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    color: #5e7d98;
    font-size: 10px;
    font-weight: 600;
  }

  .landing-dossier-row strong { color: #f2b66d; font-weight: 700; }

  .landing-timeline-card {
    left: 14px;
    right: 14px;
    bottom: 14px;
    border-radius: 12px;
    padding: 10px 12px;
  }

  .landing-timeline-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .landing-timeline-title {
    color: #5e7d98;
    font: 700 9px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .landing-timeline-badge {
    color: #7fd0ff;
    font: 700 9px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.06em;
  }

  .landing-timeline-track {
    position: relative;
    height: 4px;
    border-radius: 999px;
    background: rgba(74, 163, 255, 0.1);
    overflow: hidden;
  }

  .landing-timeline-track::after {
    content: "";
    position: absolute;
    inset: 0 28% 0 0;
    border-radius: inherit;
    background: linear-gradient(90deg, #4cc38a, #4aa3ff, #f2b66d);
  }

  .landing-timeline-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 6px;
    color: #3a5570;
    font: 600 9px/1 "JetBrains Mono", monospace;
  }

  /* ── Metrics strip ─────────────────────────────────────── */
  .landing-metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }

  .landing-metric {
    padding: 18px 20px;
    border-radius: 16px;
    border: 1px solid rgba(158, 217, 255, 0.09);
    background: rgba(255, 255, 255, 0.025);
    position: relative;
    overflow: hidden;
    transition: border-color 200ms ease;
  }

  .landing-metric::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(158, 217, 255, 0.2), transparent);
  }

  .landing-metric:hover {
    border-color: rgba(158, 217, 255, 0.18);
  }

  .landing-metric-value {
    color: #ddeeff;
    font: 800 28px/1 "Inter", sans-serif;
    letter-spacing: -0.04em;
  }

  .landing-metric[data-tone='mint'] .landing-metric-value { color: #56d3a0; }
  .landing-metric[data-tone='amber'] .landing-metric-value { color: #f2b66d; }
  .landing-metric[data-tone='rose'] .landing-metric-value { color: #ff9daf; }
  .landing-metric[data-tone='cyan'] .landing-metric-value { color: #7fd0ff; }

  .landing-metric-label {
    margin-top: 6px;
    color: #4a6a85;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  /* ── Workspace grid ────────────────────────────────────── */
  .landing-section-header {
    display: flex;
    align-items: baseline;
    gap: 14px;
    margin-bottom: 16px;
  }

  .landing-section-title {
    color: #c8dff0;
    font: 700 13px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin: 0;
  }

  .landing-section-line {
    flex: 1;
    height: 1px;
    background: rgba(74, 163, 255, 0.1);
  }

  .landing-workspace-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .landing-workspace-card {
    position: relative;
    overflow: hidden;
    padding: 22px;
    border-radius: 18px;
    border: 1px solid rgba(158, 217, 255, 0.09);
    background: rgba(255, 255, 255, 0.025);
    cursor: pointer;
    text-align: left;
    color: inherit;
    transition: border-color 200ms ease, background 200ms ease, transform 200ms ease, box-shadow 200ms ease;
  }

  .landing-workspace-card::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(158, 217, 255, 0.16), transparent);
    opacity: 0;
    transition: opacity 200ms ease;
  }

  .landing-workspace-card:hover {
    border-color: rgba(74, 163, 255, 0.24);
    background: rgba(74, 163, 255, 0.06);
    transform: translateY(-3px);
    box-shadow: 0 12px 32px rgba(0,0,0,0.28);
  }

  .landing-workspace-card:hover::before { opacity: 1; }

  .landing-workspace-card--primary {
    grid-column: span 3;
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 24px;
    border-color: rgba(76, 195, 138, 0.22);
    background: linear-gradient(135deg, rgba(76, 195, 138, 0.08), rgba(74, 163, 255, 0.05));
  }

  .landing-workspace-card--primary:hover {
    border-color: rgba(76, 195, 138, 0.38);
    background: linear-gradient(135deg, rgba(76, 195, 138, 0.12), rgba(74, 163, 255, 0.08));
    box-shadow: 0 12px 40px rgba(76, 195, 138, 0.12);
  }

  .landing-workspace-card-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    color: #7fd0ff;
    background: rgba(74, 163, 255, 0.1);
    border: 1px solid rgba(74, 163, 255, 0.2);
    margin-bottom: 14px;
  }

  .landing-workspace-card--primary .landing-workspace-card-icon {
    color: #56d3a0;
    background: rgba(76, 195, 138, 0.1);
    border-color: rgba(76, 195, 138, 0.22);
    width: 48px;
    height: 48px;
    border-radius: 14px;
    margin-bottom: 0;
  }

  .landing-workspace-card-eyebrow {
    color: #56d3a0;
    font: 700 10px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 6px;
  }

  .landing-workspace-card-title {
    color: #e2effb;
    font: 700 16px/1.2 "Inter", sans-serif;
    letter-spacing: -0.025em;
    margin-bottom: 6px;
  }

  .landing-workspace-card--primary .landing-workspace-card-title {
    font-size: 20px;
  }

  .landing-workspace-card-desc {
    color: #4a6a85;
    font-size: 12px;
    line-height: 1.5;
    max-width: 36ch;
  }

  .landing-workspace-card-arrow {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    display: grid;
    place-items: center;
    color: #56d3a0;
    background: rgba(76, 195, 138, 0.1);
    border: 1px solid rgba(76, 195, 138, 0.2);
    flex: 0 0 auto;
    transition: 180ms ease;
  }

  .landing-workspace-card--primary:hover .landing-workspace-card-arrow {
    background: rgba(76, 195, 138, 0.18);
    transform: translateX(3px);
  }

  /* ── Capability band ───────────────────────────────────── */
  .landing-capability-band {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 14px 18px;
    border: 1px solid rgba(74, 163, 255, 0.1);
    border-radius: 16px;
    background: rgba(3, 9, 18, 0.6);
    backdrop-filter: blur(12px);
  }

  .landing-capability-label {
    color: #3a5570;
    font: 700 10px/1 "JetBrains Mono", monospace;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-right: 4px;
    white-space: nowrap;
  }

  .landing-capability {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 10px;
    border-radius: 999px;
    color: #5a7a9a;
    background: rgba(74, 163, 255, 0.05);
    border: 1px solid rgba(74, 163, 255, 0.12);
    font-size: 11px;
    font-weight: 600;
    transition: 160ms ease;
    cursor: default;
  }

  .landing-capability:hover {
    color: #9be8ff;
    border-color: rgba(74, 163, 255, 0.28);
    background: rgba(74, 163, 255, 0.1);
  }

  /* ── Animations ────────────────────────────────────────── */
  @keyframes landing-float {
    0%, 100% { transform: translateY(0) scale(1); }
    50% { transform: translateY(-8px) scale(1.05); }
  }

  @keyframes landing-pulse {
    0%, 100% { box-shadow: var(--status-shadow-a); }
    50% { box-shadow: var(--status-shadow-b); }
  }

  .workspace-loading {
    height: 100%;
    display: grid;
    place-items: center;
    color: var(--text-muted);
    background: linear-gradient(180deg, rgba(7, 17, 31, 0.8), rgba(5, 11, 21, 0.92));
    font-size: 14px;
  }

  @media (max-width: 980px) {
    .workspace-header {
      flex-direction: column;
      align-items: stretch;
      min-height: auto;
      padding: 12px 18px;
    }

    .workspace-header-main {
      justify-content: space-between;
    }

    .workspace-subtitle {
      white-space: normal;
    }

    .workspace-tabs {
      justify-content: flex-start;
    }

    .landing-hero {
      grid-template-columns: 1fr;
      min-height: auto;
    }

    .landing-workspace-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .landing-workspace-card--primary {
      grid-column: span 2;
    }

    .landing-metrics {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .landing-preview {
      aspect-ratio: 16/10;
      min-height: 320px;
    }
  }

  @media (max-width: 680px) {
    .app-rail {
      width: 72px;
      padding: 14px 9px;
    }

    .landing-shell {
      padding: 20px 16px;
      gap: 36px;
    }

    .landing-workspace-grid {
      grid-template-columns: 1fr;
    }

    .landing-workspace-card--primary {
      grid-column: span 1;
      grid-template-columns: 1fr;
    }

    .landing-workspace-card-arrow {
      display: none;
    }

    .landing-metrics {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .landing-preview {
      min-height: 280px;
    }

    .landing-dossier-card {
      left: 10px;
      right: 10px;
      width: auto;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .landing-node,
    .landing-workspace-card,
    .landing-cta-primary,
    .landing-cta-secondary {
      animation: none;
      transition: none;
    }
  }
`;

function WorkspaceShell({
  title,
  subtitle,
  tabs,
  compact = false,
  kicker = 'Workspace',
  children,
}: {
  title: string;
  subtitle?: string;
  tabs?: ReactNode;
  compact?: boolean;
  kicker?: string;
  children: ReactNode;
}) {
  return (
    <section className="workspace-shell">
      <header className={`workspace-header${compact ? " workspace-header--compact" : ""}`}>
        <div className="workspace-header-main">
          <div className="workspace-kicker">{kicker}</div>
          <div className="workspace-title-block">
            <h1 className="workspace-title">{title}</h1>
            {subtitle ? <div className="workspace-subtitle">{subtitle}</div> : null}
          </div>
        </div>
        {tabs ? <div className="workspace-tabs">{tabs}</div> : null}
      </header>
      <div className="workspace-body">{children}</div>
    </section>
  );
}

function WorkspaceFallback() {
  return <div className="workspace-loading">Loading workspace…</div>;
}

function getNumberStat(payload: GraphStatsPayload, keys: Array<keyof GraphStatsPayload>) {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function formatMetric(value: number | null, fallback: string) {
  return value === null ? fallback : value.toLocaleString();
}

function WelcomeScreen({
  onOpenNetwork,
  onOpenVocabulary,
  onOpenReasoning,
  onOpenImport,
  onOpenDecisions,
  onOpenManage,
}: {
  onOpenNetwork: () => void;
  onOpenVocabulary: () => void;
  onOpenReasoning: () => void;
  onOpenImport: () => void;
  onOpenDecisions: () => void;
  onOpenManage: () => void;
}) {
  const [stats, setStats] = useState<{ nodes: number | null; edges: number | null; status: ConnectionStatus }>({
    nodes: null,
    edges: null,
    status: 'checking',
  });

  useEffect(() => {
    const controller = new AbortController();

    fetch('/api/graph/stats', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() as Promise<GraphStatsPayload> : null))
      .then((payload) => {
        if (!payload) {
          setStats((current) => ({ ...current, status: 'offline' }));
          return;
        }

        setStats({
          nodes: getNumberStat(payload, ['node_count', 'nodeCount', 'nodes']),
          edges: getNumberStat(payload, ['edge_count', 'edgeCount', 'edges']),
          status: 'online',
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        setStats((current) => ({ ...current, status: 'offline' }));
      });

    return () => controller.abort();
  }, []);

  const isOnline = stats.status === 'online';
  const metrics: LandingMetric[] = [
    { label: 'Knowledge nodes', value: formatMetric(stats.nodes, 'Live'), tone: 'cyan' },
    { label: 'Relationships mapped', value: formatMetric(stats.edges, 'Ready'), tone: 'mint' },
    { label: 'Graph modes', value: '3', tone: 'amber' },
    { label: isOnline ? 'Dataset online' : 'Ready to explore', value: isOnline ? 'Active' : 'Standby', tone: 'rose' },
  ];

  const secondaryLaunchers: LandingAction[] = [
    {
      label: 'Vocabulary',
      description: 'Schemes and terms',
      icon: Database,
      onClick: onOpenVocabulary,
    },
    {
      label: 'Analyze',
      description: 'Inference and queries',
      icon: BrainCircuit,
      onClick: onOpenReasoning,
    },
    {
      label: 'Decisions',
      description: 'Chains and precedents',
      icon: Scale,
      onClick: onOpenDecisions,
    },
    {
      label: 'Enrich',
      description: 'Import and resolve',
      icon: GitBranchPlus,
      onClick: onOpenImport,
    },
    {
      label: 'Manage',
      description: 'Lineage and ontology',
      icon: ShieldCheck,
      onClick: onOpenManage,
    },
  ];

  return (
    <main className="landing-page">
      <div className="landing-shell">

        {/* ── Hero ── */}
        <section className="landing-hero">
          <div className="landing-copy">
            <div className="landing-status-bar" data-status={stats.status}>
              <div className="landing-status-dot" />
              <span className="landing-status-text">{CONNECTION_STATUS_LABEL[stats.status]}</span>
              <div className="landing-status-divider" />
              <span className="landing-status-version">Semantica v2 · Semantic Intelligence</span>
            </div>

            <div className="landing-kicker" aria-label="Product category">
              <span className="landing-kicker-mark" aria-hidden="true" />
              Knowledge Explorer
            </div>

            <h1 className="landing-title">
              Navigate knowledge<br />
              like a <span>living system.</span>
            </h1>
            <p className="landing-subtitle">
              Semantica turns dense knowledge graphs into a navigable command center —
              discovery, reasoning, provenance, distance intelligence, and decision context,
              all in one interface.
            </p>

            <div className="landing-cta-row">
              <button className="landing-cta-primary" type="button" onClick={onOpenNetwork}>
                <Network size={16} />
                Open Semantica Explorer
                <ArrowRight size={15} />
              </button>
              <button className="landing-cta-secondary" type="button" onClick={onOpenReasoning}>
                <BrainCircuit size={15} />
                Run Reasoning
              </button>
            </div>
          </div>

          {/* ── Preview panel ── */}
          <div className="landing-preview" aria-label="Knowledge graph preview">
            <div className="landing-preview-topbar" aria-hidden="true">
              <div className="landing-preview-dot" />
              <div className="landing-preview-dot" />
              <div className="landing-preview-dot" />
              <div className="landing-preview-tab">Semantica Explorer</div>
            </div>
            <div className="landing-command-card">
              <div className="landing-command-icon">
                <Search size={15} />
              </div>
              <div>
                <div className="landing-command-label">Search command, node, or concept</div>
                <div className="landing-command-meta">distance heatmap · focused view · causal path</div>
              </div>
            </div>
            <div className="landing-preview-orbit">
              <svg viewBox="0 0 640 440" role="img" aria-hidden="true">
                <path className="landing-preview-line" d="M110 310 C200 110 390 90 510 240" />
                <path className="landing-preview-line landing-preview-line--warm" d="M120 190 C240 270 374 182 508 340" />
                <path className="landing-preview-line landing-preview-line--mint" d="M168 378 C274 200 392 218 488 144" />
                <path className="landing-preview-line landing-preview-line--warm" d="M204 118 C318 340 408 368 526 284" />
                <path className="landing-preview-line" d="M110 310 C180 350 260 360 340 320 C420 280 480 260 510 240" />
                <g className="landing-node">
                  <circle cx="110" cy="310" r="10" fill="#4cc38a" fillOpacity="0.9" />
                  <circle cx="110" cy="310" r="20" fill="none" stroke="rgba(76,195,138,0.24)" strokeWidth="1.5" />
                  <circle cx="110" cy="310" r="34" fill="none" stroke="rgba(76,195,138,0.1)" strokeWidth="1" />
                </g>
                <g className="landing-node">
                  <circle cx="204" cy="118" r="7" fill="#4aa3ff" fillOpacity="0.9" />
                  <circle cx="204" cy="118" r="16" fill="none" stroke="rgba(74,163,255,0.24)" strokeWidth="1.5" />
                </g>
                <g className="landing-node">
                  <circle cx="510" cy="240" r="13" fill="#f2b66d" fillOpacity="0.9" />
                  <circle cx="510" cy="240" r="26" fill="none" stroke="rgba(242,182,109,0.26)" strokeWidth="1.5" />
                  <circle cx="510" cy="240" r="40" fill="none" stroke="rgba(242,182,109,0.1)" strokeWidth="1" />
                </g>
                <g className="landing-node">
                  <circle cx="488" cy="144" r="6" fill="#ff9daf" fillOpacity="0.9" />
                  <circle cx="488" cy="144" r="14" fill="none" stroke="rgba(255,157,175,0.22)" strokeWidth="1.5" />
                </g>
                <g className="landing-node">
                  <circle cx="340" cy="320" r="9" fill="#7fd0ff" fillOpacity="0.9" />
                  <circle cx="340" cy="320" r="20" fill="none" stroke="rgba(127,208,255,0.22)" strokeWidth="1.5" />
                </g>
                <g opacity="0.45">
                  {PREVIEW_DOTS.map((dot, index) => (
                    <circle key={index} cx={dot.cx} cy={dot.cy * 0.82} r={dot.r * 0.8} fill={dot.fill} />
                  ))}
                </g>
              </svg>
            </div>
            <div className="landing-dossier-card">
              <div className="landing-dossier-kicker">Entity Dossier</div>
              <div className="landing-dossier-title">NSRP1</div>
              <div className="landing-dossier-row"><span>Distance band</span><strong>Near</strong></div>
              <div className="landing-dossier-row"><span>Path coherence</span><strong>0.84</strong></div>
              <div className="landing-dossier-row"><span>Provenance</span><strong>Audited</strong></div>
            </div>
            <div className="landing-timeline-card">
              <div className="landing-timeline-header">
                <span className="landing-timeline-title">Temporal Evidence</span>
                <span className="landing-timeline-badge">66% coverage</span>
              </div>
              <div className="landing-timeline-track" />
              <div className="landing-timeline-labels">
                <span>1970</span>
                <span>2030</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── Live metrics ── */}
        <div className="landing-metrics" aria-label="System status">
          {metrics.map((metric) => (
            <div key={metric.label} className="landing-metric" data-tone={metric.tone}>
              <div className="landing-metric-value">{metric.value}</div>
              <div className="landing-metric-label">{metric.label}</div>
            </div>
          ))}
        </div>

        {/* ── Workspace grid ── */}
        <section aria-label="Workspaces">
          <div className="landing-section-header">
            <h2 className="landing-section-title">Workspaces</h2>
            <div className="landing-section-line" />
          </div>
          <div className="landing-workspace-grid">
            <button className="landing-workspace-card landing-workspace-card--primary" type="button" onClick={onOpenNetwork}>
              <div>
                <div className="landing-workspace-card-eyebrow">Primary Workspace</div>
                <div className="landing-workspace-card-title">Semantica Explorer</div>
                <div className="landing-workspace-card-desc">
                  Full graph, grouped communities, focused neighborhoods, and distance intelligence — all in one canvas.
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="landing-workspace-card-icon" style={{ marginBottom: 0 }}>
                  <Network size={22} />
                </div>
                <div className="landing-workspace-card-arrow">
                  <ArrowRight size={18} />
                </div>
              </div>
            </button>

            {secondaryLaunchers.map((launcher) => {
              const Icon = launcher.icon;
              return (
                <button key={launcher.label} className="landing-workspace-card" type="button" onClick={launcher.onClick}>
                  <div className="landing-workspace-card-icon">
                    <Icon size={18} />
                  </div>
                  <div className="landing-workspace-card-title">{launcher.label}</div>
                  <div className="landing-workspace-card-desc">{launcher.description}</div>
                </button>
              );
            })}
          </div>
        </section>

        {/* ── Capability band ── */}
        <section className="landing-capability-band" aria-label="Intelligence capabilities">
          <div className="landing-capability-label">Intelligence Layer</div>
          <div className="landing-capability"><Radar size={12} />Distance Heatmap</div>
          <div className="landing-capability"><Network size={12} />Focused Neighborhood</div>
          <div className="landing-capability"><GitMerge size={12} />Grouped Communities</div>
          <div className="landing-capability"><Route size={12} />Trace Causal Path</div>
          <div className="landing-capability"><ShieldCheck size={12} />Provenance Dossier</div>
        </section>

      </div>
    </main>
  );
}

export default function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceId>('welcome');
  const [exploreView, setExploreView] = useState<ExploreView>('graph');
  const [analyzeView, setAnalyzeView] = useState<AnalyzeView>('reasoning');
  const [enrichView, setEnrichView] = useState<EnrichView>('import');
  const [manageView, setManageView] = useState<ManageView>('lineage');
  const [graphFocusRequest, setGraphFocusRequest] = useState<{ nodeId: string; token: number } | null>(null);


  const renderWorkspace = () => {
    if (activeWorkspace === 'welcome') {
      return (
        <WelcomeScreen
          onOpenNetwork={() => {
            setActiveWorkspace('explore');
            setExploreView('graph');
          }}
          onOpenVocabulary={() => {
            setActiveWorkspace('explore');
            setExploreView('vocabulary');
          }}
          onOpenReasoning={() => {
            setActiveWorkspace('analyze');
            setAnalyzeView('reasoning');
          }}
          onOpenImport={() => {
            setActiveWorkspace('enrich');
            setEnrichView('import');
          }}
          onOpenDecisions={() => setActiveWorkspace('decisions')}
          onOpenManage={() => setActiveWorkspace('manage')}
        />
      );
    }

    if (activeWorkspace === 'explore') {
      return (
        <WorkspaceShell
          title="Explore"
          subtitle={exploreView === 'graph' ? undefined : "Browse the graph and switch views without leaving the workspace."}
          kicker={exploreView === 'graph' ? 'Graph Studio' : 'Vocabulary Browser'}
          compact
          tabs={
            <>
              <button className="workspace-tab" data-active={exploreView === 'graph'} onClick={() => setExploreView('graph')}>
                Semantica Explorer
              </button>
              <button className="workspace-tab" data-active={exploreView === 'vocabulary'} onClick={() => setExploreView('vocabulary')}>
                Vocabulary Browser
              </button>
            </>
          }
        >
          <ErrorBoundary key={`explore-${exploreView}`}>
            <Suspense fallback={<WorkspaceFallback />}>
              {exploreView === 'graph' ? (
                <GraphWorkspace
                  externalFocusNodeId={graphFocusRequest?.nodeId}
                  externalFocusToken={graphFocusRequest?.token}
                />
              ) : <VocabularyWorkspace />}
            </Suspense>
          </ErrorBoundary>
        </WorkspaceShell>
      );
    }

    if (activeWorkspace === 'analyze') {
      return (
        <WorkspaceShell
          title="Analyze"
          subtitle="Query the active graph and test inference rules."
          kicker={analyzeView === 'reasoning' ? 'Reasoning Engine' : 'SPARQL Query'}
          tabs={
            <>
              <button className="workspace-tab" data-active={analyzeView === 'reasoning'} onClick={() => setAnalyzeView('reasoning')}>
                Reasoning Playground
              </button>
              <button className="workspace-tab" data-active={analyzeView === 'sparql'} onClick={() => setAnalyzeView('sparql')}>
                SPARQL Querying
              </button>
            </>
          }
        >
          <ErrorBoundary key={`analyze-${analyzeView}`}>
            <Suspense fallback={<WorkspaceFallback />}>
              {analyzeView === 'reasoning' ? <ReasoningWorkspace /> : <SparqlWorkspace />}
            </Suspense>
          </ErrorBoundary>
        </WorkspaceShell>
      );
    }

    if (activeWorkspace === 'decisions') {
      return (
        <WorkspaceShell
          title="Decisions"
          subtitle="Inspect decision chains, causal context, and precedent matches."
          kicker="Decision Intelligence"
        >
          <ErrorBoundary key="decisions">
            <Suspense fallback={<WorkspaceFallback />}>
              <DecisionWorkspace />
            </Suspense>
          </ErrorBoundary>
        </WorkspaceShell>
      );
    }

    if (activeWorkspace === 'enrich') {
      return (
        <WorkspaceShell
          title="Enrich"
          subtitle="Import, export, reconcile, and audit graph entities."
          kicker="Knowledge Audit"
          tabs={
            <>
              <button className="workspace-tab" data-active={enrichView === 'import'} onClick={() => setEnrichView('import')}>
                Import and Export
              </button>
              <button className="workspace-tab" data-active={enrichView === 'merge'} onClick={() => setEnrichView('merge')}>
                Diff and Merge
              </button>
              <button className="workspace-tab" data-active={enrichView === 'resolve'} onClick={() => setEnrichView('resolve')}>
                Entity Resolution
              </button>
              <button className="workspace-tab" data-active={enrichView === 'registry'} onClick={() => setEnrichView('registry')}>
                Registry
              </button>
            </>
          }
        >
          <ErrorBoundary key={`enrich-${enrichView}`}>
            <Suspense fallback={<WorkspaceFallback />}>
              {enrichView === 'import' ? <ImportExportWorkspace /> :
               enrichView === 'merge' ? <DiffMergeWorkspace /> :
               enrichView === 'resolve' ? <EntityResolutionTab /> :
               <RegistryTab />}
            </Suspense>
          </ErrorBoundary>
        </WorkspaceShell>
      );
    }

    if (activeWorkspace === 'ontology-hub') {
      return (
        <WorkspaceShell
          title="Ontology Hub"
          subtitle="Load, browse, edit, and govern ontologies and vocabularies."
          kicker="Schema Governance"
          compact
        >
          <ErrorBoundary key="ontology-hub">
            <Suspense fallback={<WorkspaceFallback />}>
              <OntologyWorkspace
                onJumpToGraphNode={(nodeId: string) => {
                  setGraphFocusRequest({ nodeId, token: Date.now() });
                  setActiveWorkspace('explore');
                  setExploreView('graph');
                }}
              />
            </Suspense>
          </ErrorBoundary>
        </WorkspaceShell>
      );
    }

    return (
      <WorkspaceShell
        title="Manage"
        subtitle="Review provenance, lineage, ontology, and governance context."
        kicker="Graph Governance"
        tabs={
          <>
            <button className="workspace-tab" data-active={manageView === 'lineage'} onClick={() => setManageView('lineage')}>
              PROV-O Lineage
            </button>
            <button className="workspace-tab" data-active={manageView === 'kg-overview'} onClick={() => setManageView('kg-overview')}>
              KG Overview
            </button>
            <button className="workspace-tab" data-active={manageView === 'ontology'} onClick={() => setManageView('ontology')}>
              Ontology Summary
            </button>
          </>
        }
      >
        <ErrorBoundary key={`manage-${manageView}`}>
          <Suspense fallback={<WorkspaceFallback />}>
            {manageView === 'lineage' ? <LineageDiagram /> :
             manageView === 'kg-overview' ? <KGOverviewTab /> :
             <OntologySummaryTab onOpenVocabularyBrowser={() => {
               setActiveWorkspace('explore');
               setExploreView('vocabulary');
             }} />}
          </Suspense>
        </ErrorBoundary>
      </WorkspaceShell>
    );
  };

  return (
    <QueryClientProvider client={queryClient}>
      <style>{shellStyles}</style>
      <div className="app-shell">
        <aside className="app-rail">
          <button className="brand-pill" title="Semantica Knowledge Explorer" onClick={() => setActiveWorkspace('welcome')} style={{ cursor: 'pointer', border: '1px solid rgba(127,208,255,0.18)' }}>SKE</button>
          {navItems.map(({ id, label, hint, icon: Icon }) => (
            <button
              key={id}
              className="nav-button"
              data-active={activeWorkspace === id}
              onClick={() => setActiveWorkspace(id)}
              title={hint}
            >
              <Icon size={20} />
              <span className="nav-label">{label}</span>
            </button>
          ))}
        </aside>
        {renderWorkspace()}
      </div>
    </QueryClientProvider>
  );
}
