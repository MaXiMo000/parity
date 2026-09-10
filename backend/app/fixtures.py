"""Phase 0 walking-skeleton data: one hand-written, realistic-shaped
REST API (a small task manager) — no real OpenAPI parsing yet (Phase 1),
no real request proxying yet (Phase 2). Field names match SPEC.md §7.5's
real `node` columns exactly, so nothing here needs to change shape once
Phase 1 makes it real.
"""
from __future__ import annotations

from typing import Any

FIXTURE_WORKSPACE_ID = "phase0-fixture-workspace"

_TASK_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "done": {"type": "boolean"},
    },
    "required": ["id", "title", "done"],
}

_NODES: list[dict[str, Any]] = [
    dict(
        id="list_tasks", kind="rest_operation", method="GET", path_template="/tasks",
        operation_id="list_tasks", declared_request_schema=None,
        declared_response_schema={"type": "array", "items": _TASK_ITEM_SCHEMA},
        call_count=0,
    ),
    dict(
        id="create_task", kind="rest_operation", method="POST", path_template="/tasks",
        operation_id="create_task",
        declared_request_schema={
            "type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"],
        },
        declared_response_schema=_TASK_ITEM_SCHEMA,
        call_count=0,
    ),
    dict(
        id="get_task", kind="rest_operation", method="GET", path_template="/tasks/{id}",
        operation_id="get_task", declared_request_schema=None,
        declared_response_schema=_TASK_ITEM_SCHEMA,
        call_count=0,
    ),
    dict(
        id="update_task", kind="rest_operation", method="PATCH", path_template="/tasks/{id}",
        operation_id="update_task",
        declared_request_schema={
            "type": "object", "properties": {"title": {"type": "string"}, "done": {"type": "boolean"}},
        },
        declared_response_schema=_TASK_ITEM_SCHEMA,
        call_count=0,
    ),
    dict(
        id="delete_task", kind="rest_operation", method="DELETE", path_template="/tasks/{id}",
        operation_id="delete_task", declared_request_schema=None,
        declared_response_schema=None,
        call_count=0,
    ),
]

# Pairs of node ids that share a path template — the frontend renders an
# edge per pair so the 3D layout clusters an endpoint's methods together.
# Real Phase-1 grouping (by tag/path hierarchy) replaces this; Phase 0
# just needs *a* real, non-arbitrary grouping rule.
_EDGES: list[tuple[str, str]] = [
    ("list_tasks", "create_task"),
    ("get_task", "update_task"),
    ("update_task", "delete_task"),
]


def fixture_workspace() -> dict[str, Any]:
    return {
        "id": FIXTURE_WORKSPACE_ID,
        "name": "Task Manager (fixture)",
        "schema_kind": "openapi",
        "nodes": [dict(n) for n in _NODES],
    }


def fixture_edges() -> list[tuple[str, str]]:
    return list(_EDGES)
