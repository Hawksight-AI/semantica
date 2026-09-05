"""Minimal AgentMemory selection surface for Explorer."""

from fastapi import APIRouter, Depends, Query

from ...context.agent_memory import AgentMemory
from ..dependencies import get_agent_memory
from ..schemas import MemoryListResponse, MemorySummaryResponse

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("", response_model=MemoryListResponse)
def list_memories(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    memory: AgentMemory = Depends(get_agent_memory),
) -> MemoryListResponse:
    records, total = memory.list_snapshot(offset=skip, limit=limit)
    items = []
    for record in records:
        metadata = record.get("metadata") or {}
        content = record.get("content") or ""
        excerpt = " ".join(str(content).split())[:160]
        items.append(
            MemorySummaryResponse(
                id=record["memory_id"],
                type=str(metadata.get("type") or "general"),
                excerpt=excerpt,
                updated_at=(
                    str(metadata["updated_at"])
                    if metadata.get("updated_at") is not None
                    else None
                ),
            )
        )
    return MemoryListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )
