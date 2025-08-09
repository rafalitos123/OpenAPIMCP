from fastmcp import FastMCP
from fastmcp.experimental.server.openapi import OpenAPITool
from fastmcp.experimental.utilities.openapi.models import HTTPRoute
from jsonschema_path import SchemaPath
import httpx
import json
import socket
import secrets
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.logging import configure_logging, get_logger
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

logger = get_logger(__name__)

configure_logging(level="DEBUG")
app = FastAPI(title="OpenAPI MCP Builder API")

# Allow cross-origin requests from local static server and preview
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep references to running servers/apps to avoid garbage-collection
RUNNING_SERVERS: dict[str, dict] = {}

 


def _derive_base_url(openapi_spec: dict, openapi_url: str) -> str:
    """Derive API base URL from OpenAPI servers or fallback to the origin of the spec URL."""
    try:
        servers = openapi_spec.get("servers") or []
        if servers and isinstance(servers, list):
            url = servers[0].get("url") if isinstance(servers[0], dict) else None
            if isinstance(url, str) and url:
                return url
    except Exception:
        pass
    parsed = urlparse(openapi_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_mcp_from_openapi(openapi_spec: dict, openapi_url: str) -> FastMCP:
    """Build a FastMCP server from an OpenAPI spec with component customization."""
    spec = SchemaPath.from_dict(openapi_spec)

    def get_security_schemes_for_route(route: HTTPRoute) -> set[str]:
        """Return set of security scheme names applied to this route."""
        schemes: set[str] = set()

        # 1) Operation-level security
        try:
            with (spec / "paths" / route.path / route.method.lower() / "security").open() as sec:  # type: ignore[attr-defined]
                if isinstance(sec, list):
                    for req in sec:
                        if isinstance(req, dict):
                            for name in req.keys():
                                schemes.add(str(name))
                return schemes
        except KeyError:
            pass

        # 2) Top-level security
        try:
            with (spec / "security").open() as sec:  # type: ignore[attr-defined]
                if isinstance(sec, list):
                    for req in sec:
                        if isinstance(req, dict):
                            for name in req.keys():
                                schemes.add(str(name))
        except KeyError:
            pass

        return schemes

    def customize_components(route: HTTPRoute, component) -> None:  # type: ignore[no-untyped-def]
        # Tag all components
        component.tags.add("openapi")

        secured_schemes = get_security_schemes_for_route(route)
        if not secured_schemes:
            return

        # Only Tools support arbitrary header parameters at call time
        if isinstance(component, OpenAPITool):
            params = component.parameters or {"type": "object", "properties": {}}
            props = params.setdefault("properties", {})

            if "Authorization" not in props:
                props["Authorization"] = {
                    "type": "string",
                    "description": "Authorization header (e.g., 'Bearer <token>').",
                }
            component.parameters = params

            if "Authorization" not in route.parameter_map:
                route.parameter_map["Authorization"] = {
                    "location": "header",
                    "openapi_name": "Authorization",
                }

            flat_props = route.flat_param_schema.setdefault("properties", {})
            if "Authorization" not in flat_props:
                flat_props["Authorization"] = {
                    "type": "string",
                    "description": "Authorization header (e.g., 'Bearer <token>').",
                }

    base_url = _derive_base_url(openapi_spec, openapi_url)
    client = httpx.AsyncClient(base_url=base_url)

    name = openapi_spec.get("info", {}).get("title") or f"MCP from {base_url}"
    mcp = FastMCP.from_openapi(
        openapi_spec,
        client,
        name=str(name),
        mcp_component_fn=customize_components,
    )
    return mcp


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@app.get("/generate")
async def generate(request: Request, openapi_url: str = Query(..., description="Public URL to OpenAPI JSON or YAML")) -> dict:
    """Create and run an MCP server for the given OpenAPI spec and return its URL."""
    # Fetch OpenAPI spec
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.get(openapi_url)
            resp.raise_for_status()
            try:
                openapi_spec = resp.json()
            except Exception:
                # Try YAML, then JSON from text
                if yaml is not None:
                    try:
                        openapi_spec = yaml.safe_load(resp.text)  # type: ignore
                    except Exception:
                        openapi_spec = json.loads(resp.text)
                else:
                    openapi_spec = json.loads(resp.text)
    except Exception as e:
        logger.exception("Failed to download OpenAPI spec")
        raise HTTPException(status_code=400, detail=f"Failed to fetch OpenAPI: {e}")

    # Build MCP server
    try:
        mcp = _build_mcp_from_openapi(openapi_spec, openapi_url)
    except Exception as e:
        logger.exception("Failed to build MCP from OpenAPI")
        raise HTTPException(status_code=400, detail=f"Failed to build MCP: {e}")

    # Mount MCP ASGI app under this FastAPI app (works on single host/platforms like Render)
    server_id = f"srv-{secrets.token_hex(4)}"
    mount_path = f"/mcp/{server_id}"
    mcp_app = mcp.http_app(path="/")
    app.mount(mount_path, mcp_app)
    RUNNING_SERVERS[server_id] = {"mount_path": mount_path, "mcp": mcp}

    base = str(request.base_url).rstrip("/")
    mcp_url = f"{base}{mount_path}/"
    logger.info(f"Mounted MCP server {server_id} at {mcp_url}")
    return {"server_id": server_id, "mcp_url": mcp_url}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

# Mount static UI last, so API routes (like /generate) take precedence
try:
    project_root = Path(__file__).resolve().parents[2]
    static_dir = project_root / "web"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
except Exception:
    # Non-fatal if static mount fails
    pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "5050"))
    uvicorn.run(app, host="0.0.0.0", port=port)

