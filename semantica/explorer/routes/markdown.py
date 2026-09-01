"""Explorer routes for canonical Markdown resources."""

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_markdown_resources
from ..markdown_resources import (
    InvalidMarkdownFrontmatter,
    MarkdownApplyResult,
    MarkdownDocument,
    MarkdownResourceError,
    MarkdownResourceKind,
    MarkdownResourceNotFound,
    MarkdownResourceRef,
    MarkdownResourceRegistry,
    MarkdownRevisionConflict,
    ResourceIdentityMismatch,
)
from ..schemas import (
    MarkdownApplyRequest,
    MarkdownApplyResponse,
    MarkdownDocumentResponse,
)

router = APIRouter(prefix="/api/markdown", tags=["markdown"])


def _resource_ref(kind: str, resource_id: str) -> MarkdownResourceRef:
    try:
        resource_kind = MarkdownResourceKind(kind)
    except ValueError:
        _raise_http_error(
            MarkdownResourceNotFound(
                f"Markdown resource kind {kind!r} is not available."
            )
        )
    return MarkdownResourceRef(kind=resource_kind, id=resource_id)


def _error_detail(error: MarkdownResourceError) -> dict:
    detail = {"code": error.code, "message": error.message}
    if error.field is not None:
        detail["field"] = error.field
    if error.current_revision is not None:
        detail["current_revision"] = error.current_revision
    return detail


def _raise_http_error(error: MarkdownResourceError) -> NoReturn:
    if isinstance(error, MarkdownResourceNotFound):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, MarkdownRevisionConflict):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, (InvalidMarkdownFrontmatter, ResourceIdentityMismatch)):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=status_code, detail=_error_detail(error)) from error


def _document_response(
    document: MarkdownDocument,
) -> MarkdownDocumentResponse:
    return MarkdownDocumentResponse(
        resource={
            "kind": document.resource.kind.value,
            "id": document.resource.id,
        },
        source=document.source,
        body=document.body,
        revision=document.revision,
        editable=True,
    )


def _apply_response(result: MarkdownApplyResult) -> MarkdownApplyResponse:
    document = _document_response(result)
    return MarkdownApplyResponse(**document.model_dump(), changed=result.changed)


@router.get(
    "/{kind}/{resource_id:path}",
    response_model=MarkdownDocumentResponse,
)
def read_markdown_resource(
    kind: str,
    resource_id: str,
    resources: MarkdownResourceRegistry = Depends(get_markdown_resources),
) -> MarkdownDocumentResponse:
    try:
        return _document_response(resources.read(_resource_ref(kind, resource_id)))
    except MarkdownResourceError as error:
        _raise_http_error(error)


@router.put(
    "/{kind}/{resource_id:path}",
    response_model=MarkdownApplyResponse,
)
def apply_markdown_resource(
    kind: str,
    resource_id: str,
    request: MarkdownApplyRequest,
    resources: MarkdownResourceRegistry = Depends(get_markdown_resources),
) -> MarkdownApplyResponse:
    try:
        result = resources.apply(
            _resource_ref(kind, resource_id),
            request.markdown,
            request.expected_revision,
        )
        return _apply_response(result)
    except MarkdownResourceError as error:
        _raise_http_error(error)
