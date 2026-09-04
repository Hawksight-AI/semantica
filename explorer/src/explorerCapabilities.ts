type Fetcher = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

type ExplorerInfo = {
  capabilities?: {
    agent_memory?: boolean;
  };
};

export async function fetchAgentMemoryAvailability(
  fetcher: Fetcher = fetch,
): Promise<boolean> {
  try {
    const response = await fetcher('/api/info');
    if (!response.ok) return false;

    const info = await response.json() as ExplorerInfo;
    return info.capabilities?.agent_memory === true;
  } catch {
    return false;
  }
}
