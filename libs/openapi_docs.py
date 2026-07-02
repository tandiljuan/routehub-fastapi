"""Enrich FastAPI-generated OpenAPI with metadata from openapi_bc.json baseline."""

from __future__ import annotations

import copy
import os
from typing import Any

_DEFAULT_DESCRIPTION = (
    "RouteHub is a route planning and optimization API designed for logistics, "
    "delivery services, and mobility applications."
)
_DEFAULT_LICENSE = {
    "name": "GNU Affero General Public License",
    "url": "https://www.gnu.org/licenses/agpl-3.0.html",
}
_DEFAULT_VERSION = "0.21.0"
_DEFAULT_PROD_SERVER = "https://api.vepathos.com"
_DEFAULT_LCL_SERVER = "http://127.0.0.1:8001"

_BEARER_SCHEME = {
    "description": (
        "Static bearer API key sent in the `Authorization` header "
        "(`Authorization: Bearer <token>`). The workspace is derived from the "
        "validated key and bound server-side."
    ),
    "type": "http",
    "scheme": "bearer",
}

_GENERIC_SCHEMA = {
    "title": "GenericResponse",
    "type": "object",
    "properties": {
        "code": {"type": "integer"},
        "message": {"type": "string"},
    },
    "required": ["code"],
}

_UNAUTHORIZED_RESPONSE = {
    "description": "Invalid or missing access token.",
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/GenericResponse"},
            "example": {"code": 401, "message": "Invalid API key"},
        }
    },
}


def _openapi_servers(*, is_lcl: bool) -> list[dict[str, str]]:
    explicit = os.environ.get("OPENAPI_SERVER_URL")
    if explicit:
        return [{"url": explicit.rstrip("/")}]
    if is_lcl:
        return [{"url": _DEFAULT_LCL_SERVER}]
    return [{"url": _DEFAULT_PROD_SERVER}]


def enrich_openapi(schema: dict[str, Any], *, is_lcl: bool = False) -> dict[str, Any]:
    """Apply servers, global security, license, and 401 responses (openapi_bc parity)."""
    out = copy.deepcopy(schema)
    info = dict(out.get("info") or {})
    info.setdefault("title", "RouteHub")
    info["description"] = os.environ.get("OPENAPI_DESCRIPTION", _DEFAULT_DESCRIPTION)
    info["version"] = os.environ.get("OPENAPI_VERSION", _DEFAULT_VERSION)
    info["license"] = _DEFAULT_LICENSE
    out["info"] = info

    out["servers"] = _openapi_servers(is_lcl=is_lcl)

    components = dict(out.get("components") or {})
    # One credential for the whole API: a bearer API key (auth + workspace scope).
    components["securitySchemes"] = {"bearerAuth": _BEARER_SCHEME}

    schemas = dict(components.get("schemas") or {})
    schemas.setdefault("GenericResponse", _GENERIC_SCHEMA)
    components["schemas"] = schemas

    responses = dict(components.get("responses") or {})
    responses.setdefault("unauthorized", _UNAUTHORIZED_RESPONSE)
    components["responses"] = responses
    out["components"] = components

    out["security"] = [{"bearerAuth": []}]

    for path_item in out.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for op in path_item.values():
            if not isinstance(op, dict):
                continue
            op.pop("security", None)
            op_responses = dict(op.get("responses") or {})
            op_responses.setdefault("401", {"$ref": "#/components/responses/unauthorized"})
            op["responses"] = op_responses

    return out
