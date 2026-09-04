export type ExploreView = 'graph' | 'memories' | 'vocabulary';

type ExploreWorkspaceTabsProps = {
  activeView: ExploreView;
  agentMemoryAvailable: boolean;
  onSelect: (view: ExploreView) => void;
};

export function ExploreWorkspaceTabs({
  activeView,
  agentMemoryAvailable,
  onSelect,
}: ExploreWorkspaceTabsProps) {
  return (
    <>
      <button className="workspace-tab" data-active={activeView === 'graph'} onClick={() => onSelect('graph')}>
        Semantica Explorer
      </button>
      {agentMemoryAvailable ? (
        <button className="workspace-tab" data-active={activeView === 'memories'} onClick={() => onSelect('memories')}>
          Memories
        </button>
      ) : null}
      <button className="workspace-tab" data-active={activeView === 'vocabulary'} onClick={() => onSelect('vocabulary')}>
        Vocabulary Browser
      </button>
    </>
  );
}
