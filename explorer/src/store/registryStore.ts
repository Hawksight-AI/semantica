/**
 * src/store/registryStore.ts
 *
 * Lightweight client-side audit log for all KG / Ontology mutations.
 * No backend required — events are dispatched by each workspace after
 * a successful API call or WebSocket mutation.
 *
 * Any component can call logEvent() from anywhere (including non-React code).
 * React components subscribe via the useRegistry() hook.
 */
import { useState, useEffect } from "react";

export type RegistryEntryOp =
  | "import"
  | "export"
  | "merge"
  | "add-node"
  | "update-node"
  | "add-edge"
  | "delete"
  | "infer"
  | "vocab-import";

export interface RegistryEntry {
  id: string;
  op: RegistryEntryOp;
  timestamp: Date;
  summary: string;
  detail?: Record<string, unknown>;
}

type Listener = (entries: readonly RegistryEntry[]) => void;

let _entries: RegistryEntry[] = [];
const _listeners = new Set<Listener>();
const MAX_ENTRIES = 500;

function _notify(): void {
  _listeners.forEach((fn) => fn(_entries));
}

export function logEvent(
  op: RegistryEntryOp,
  summary: string,
  detail?: Record<string, unknown>,
): void {
  const entry: RegistryEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    op,
    timestamp: new Date(),
    summary,
    detail,
  };
  _entries = [entry, ..._entries].slice(0, MAX_ENTRIES);
  _notify();
}

export function clearRegistry(): void {
  _entries = [];
  _notify();
}

export function getRegistryEntries(): readonly RegistryEntry[] {
  return _entries;
}

export function useRegistry(): readonly RegistryEntry[] {
  const [snapshot, setSnapshot] = useState<readonly RegistryEntry[]>(_entries);
  useEffect(() => {
    // Sync any events that arrived between render and subscribe
    setSnapshot(_entries);
    _listeners.add(setSnapshot);
    return () => {
      _listeners.delete(setSnapshot);
    };
  }, []);
  return snapshot;
}
