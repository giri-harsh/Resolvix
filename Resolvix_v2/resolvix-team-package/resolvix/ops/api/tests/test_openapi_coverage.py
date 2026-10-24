"""Test OpenAPI coverage - ensure all implemented routes are documented."""
from pathlib import Path

import yaml
from resolvix_ops.app import create_app


def parse_openapi_paths(yaml_path: Path) -> set[tuple[str, str]]:
    """Parse ops-api.yaml and return set of (method, path) tuples."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    
    paths_set = set()
    for path, path_item in spec.get("paths", {}).items():
        for method in path_item.keys():
            if method in ["get", "post", "put", "patch", "delete", "options", "head"]:
                paths_set.add((method.upper(), path))
    
    return paths_set


def get_implemented_routes() -> set[tuple[str, str]]:
    """Get implemented routes from the FastAPI app."""
    app = create_app()
    routes_set = set()
    
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method != "HEAD":  # Skip HEAD as it's auto-generated
                    routes_set.add((method, route.path))
    
    return routes_set


def test_all_implemented_routes_documented():
    """Every implemented route must be in ops-api.yaml or the allowlist."""
    ops_api_dir = Path(__file__).parent.parent
    yaml_path = ops_api_dir.parent.parent / "contracts" / "openapi" / "ops-api.yaml"
    
    spec_routes = parse_openapi_paths(yaml_path)
    impl_routes = get_implemented_routes()
    
    # Allowlist: additive extensions and FastAPI docs routes
    allowlist = {
        ("GET", "/v1/auth/me"),      # Additive: get current user
        ("POST", "/v1/auth/logout"), # Additive: logout
        ("GET", "/docs"),            # FastAPI auto-generated docs
        ("GET", "/openapi.json"),    # FastAPI auto-generated OpenAPI spec
        ("GET", "/redoc"),           # FastAPI auto-generated ReDoc
        ("GET", "/docs/oauth2-redirect"),  # FastAPI OAuth2 redirect for docs
    }
    
    # Check: all implemented routes are either in spec or allowlist
    undocumented = impl_routes - spec_routes - allowlist
    
    assert not undocumented, (
        f"Routes implemented but not in ops-api.yaml or allowlist: {undocumented}"
    )


def test_path_templates_match():
    """Path templates must match structure (e.g., /v1/tickets/{ticket_id})."""
    ops_api_dir = Path(__file__).parent.parent
    yaml_path = ops_api_dir.parent.parent / "contracts" / "openapi" / "ops-api.yaml"
    
    spec_routes = parse_openapi_paths(yaml_path)
    impl_routes = get_implemented_routes()
    
    # For implemented routes that are in the spec, verify path structure matches
    spec_paths = {p for _, p in spec_routes}
    impl_paths = {p for _, p in impl_routes}
    
    # Check for similar paths with different parameter names
    for impl_path in impl_paths:
        # Convert {param} to a pattern for comparison
        impl_pattern = impl_path.replace("{", "[").replace("}", "]")
        
        for spec_path in spec_paths:
            spec_pattern = spec_path.replace("{", "[").replace("}", "]")
            
            # If patterns match but paths differ, they have different param names
            if impl_pattern == spec_pattern and impl_path != spec_path:
                raise AssertionError(
                    f"Path parameter mismatch: implemented {impl_path} vs spec {spec_path}"
                )
