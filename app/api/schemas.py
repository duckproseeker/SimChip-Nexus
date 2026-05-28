"""API schemas — only pipeline-related types are active."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True)
    data: T | None = Field(default=None)
    error: dict | None = Field(default=None)


class PipelineNodeDefPayload(BaseModel):
    node_id: str
    type: str
    position: dict[str, float] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class PipelineEdgeDefPayload(BaseModel):
    edge_id: str
    source: str
    source_handle: str = ""
    target: str
    target_handle: str = ""


class PipelinePayload(BaseModel):
    pipeline_id: str
    name: str
    description: str
    nodes: list[PipelineNodeDefPayload]
    edges: list[PipelineEdgeDefPayload]
    created_at_utc: str = ""
    updated_at_utc: str = ""


class CreatePipelineRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="")


class UpdatePipelineRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    nodes: list[PipelineNodeDefPayload] | None = None
    edges: list[PipelineEdgeDefPayload] | None = None


class PipelineResponse(ApiResponse[PipelinePayload]):
    pass


class PipelineListResponse(ApiResponse[list[PipelinePayload]]):
    pass


class PipelineNodeStatePayload(BaseModel):
    status: str
    run_id: str | None = None
    error: str | None = None


class PipelineExecutionPayload(BaseModel):
    execution_id: str
    pipeline_id: str
    status: str
    node_states: dict[str, PipelineNodeStatePayload]
    created_at_utc: str = ""


class PipelineExecutionResponse(ApiResponse[PipelineExecutionPayload]):
    pass


class PipelineExecutionListResponse(ApiResponse[list[PipelineExecutionPayload]]):
    pass


class PipelineValidationError(BaseModel):
    code: str
    message: str


class PipelineValidationResult(BaseModel):
    valid: bool
    errors: list[PipelineValidationError]


class PipelineValidationResponse(ApiResponse[PipelineValidationResult]):
    pass
