#!/usr/bin/env python3
"""Metabase API Explorer - Visualize API endpoint responses.

Usage:
    python metabase_api.py --api card          # List all cards/questions
    python metabase_api.py --api card --id 1   # Get specific card
    python metabase_api.py --api event         # List timeline events
    python metabase_api.py --api dashboard     # List all dashboards
    python metabase_api.py --api dashboard --id 1  # Get specific dashboard
    python metabase_api.py --api collection    # List all collections
    python metabase_api.py --api alert         # List all alerts
    python metabase_api.py --api pulse         # List all pulses
    python metabase_api.py --api database      # List all databases
    python metabase_api.py --api user          # Current user info
    python metabase_api.py --api raw --endpoint "table/1"  # Raw endpoint
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree


load_dotenv()

console = Console()

API_ENDPOINTS = {
    "card": "api/card",
    "question": "api/card",
    "event": "api/timeline?include=events",
    "timeline-event": "api/timeline?include=events",
    "timeline": "api/timeline",
    "dashboard": "api/dashboard",
    "collection": "api/collection",
    "alert": "api/alert",
    "pulse": "api/pulse",
    "database": "api/database",
    "table": "api/table",
    "user": "api/user/current",
    "session": "api/session/properties",
    "activity": "api/activity",
    "setting": "api/setting",
    "field": "api/field",
    "segment": "api/segment",
    "metric": "api/metric",
}


def get_session_token() -> str | None:
    """Get session token from auth state file or environment."""
    auth_file = Path(".auth/metabase_admin_state.json")
    if auth_file.exists():
        try:
            data = json.loads(auth_file.read_text())
            for cookie in data.get("cookies", []):
                if cookie.get("name") == "metabase.SESSION":
                    return cookie.get("value")
        except Exception:
            pass
    return os.getenv("METABASE_SESSION_TOKEN")


def authenticate(base_url: str, username: str, password: str) -> str | None:
    """Authenticate with Metabase and return session token."""
    try:
        response = httpx.post(
            f"{base_url}/api/session",
            json={"username": username, "password": password},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("id")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        return None


def make_request(
    base_url: str,
    endpoint: str,
    session_token: str,
    item_id: int | None = None,
) -> dict | list | None:
    """Make an authenticated request to the Metabase API."""
    headers = {
        "Content-Type": "application/json",
        "X-Metabase-Session": session_token,
    }
    
    # Handle query params in endpoint
    if "?" in endpoint:
        base_endpoint, query_params = endpoint.split("?", 1)
        if item_id is not None:
            url = f"{base_url}/{base_endpoint}/{item_id}?{query_params}"
        else:
            url = f"{base_url}/{endpoint}"
    else:
        url = f"{base_url}/{endpoint}"
        if item_id is not None:
            url = f"{url}/{item_id}"
    
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP Error {e.response.status_code}: {e.response.text}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Request failed: {e}[/red]")
        return None


def get_type_str(value: Any) -> str:
    """Get a string representation of a value's type."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        if len(value) > 50:
            return f"string ({len(value)} chars)"
        return "string"
    if isinstance(value, list):
        if not value:
            return "array (empty)"
        return f"array [{len(value)} items]"
    if isinstance(value, dict):
        return f"object ({len(value)} keys)"
    return type(value).__name__


def build_schema_tree(data: Any, tree: Tree, max_depth: int = 4, depth: int = 0) -> None:
    """Build a tree visualization of the data schema."""
    if depth >= max_depth:
        tree.add("[dim]...[/dim]")
        return
    
    if isinstance(data, dict):
        for key, value in list(data.items())[:20]:
            type_str = get_type_str(value)
            
            if isinstance(value, dict):
                branch = tree.add(f"[cyan]{key}[/cyan]: [yellow]{type_str}[/yellow]")
                build_schema_tree(value, branch, max_depth, depth + 1)
            elif isinstance(value, list) and value:
                branch = tree.add(f"[cyan]{key}[/cyan]: [yellow]{type_str}[/yellow]")
                if isinstance(value[0], (dict, list)):
                    build_schema_tree(value[0], branch, max_depth, depth + 1)
                else:
                    branch.add(f"[dim]items: {get_type_str(value[0])}[/dim]")
            else:
                preview = ""
                if isinstance(value, str) and value:
                    preview = f' = [green]"{value[:30]}{"..." if len(value) > 30 else ""}"[/green]'
                elif isinstance(value, (int, float, bool)) or value is None:
                    preview = f" = [magenta]{value}[/magenta]"
                tree.add(f"[cyan]{key}[/cyan]: [yellow]{type_str}[/yellow]{preview}")
        
        if len(data) > 20:
            tree.add(f"[dim]... and {len(data) - 20} more keys[/dim]")
    
    elif isinstance(data, list) and data:
        if isinstance(data[0], dict):
            build_schema_tree(data[0], tree, max_depth, depth + 1)


def display_response(data: Any, endpoint: str, show_raw: bool = False, show_schema: bool = True) -> None:
    """Display the API response in a formatted way."""
    console.print()
    
    if isinstance(data, list):
        console.print(Panel(
            f"[bold green]Endpoint:[/bold green] {endpoint}\n"
            f"[bold blue]Response Type:[/bold blue] Array with {len(data)} items",
            title="API Response",
            border_style="blue",
        ))
        
        if data and isinstance(data[0], dict):
            console.print("\n[bold]Sample Item Keys:[/bold]")
            keys = list(data[0].keys())
            console.print(f"  {', '.join(keys[:10])}")
            if len(keys) > 10:
                console.print(f"  [dim]... and {len(keys) - 10} more[/dim]")
            
            console.print("\n[bold]First 5 Items Summary:[/bold]")
            for i, item in enumerate(data[:5]):
                name = item.get("name") or item.get("title") or item.get("id", "N/A")
                item_id = item.get("id", "N/A")
                console.print(f"  [{i+1}] ID: {item_id}, Name/Title: {name}")
    
    elif isinstance(data, dict):
        console.print(Panel(
            f"[bold green]Endpoint:[/bold green] {endpoint}\n"
            f"[bold blue]Response Type:[/bold blue] Object with {len(data)} keys",
            title="API Response",
            border_style="blue",
        ))
    
    if show_schema:
        console.print("\n[bold]Response Schema:[/bold]")
        tree = Tree("[bold]root[/bold]")
        build_schema_tree(data, tree)
        console.print(tree)
    
    if show_raw:
        console.print("\n[bold]Raw JSON:[/bold]")
        json_str = json.dumps(data, indent=2, default=str)
        if len(json_str) > 5000:
            json_str = json_str[:5000] + "\n... (truncated)"
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
        console.print(syntax)


def main():
    parser = argparse.ArgumentParser(
        description="Explore Metabase API endpoints and visualize their responses.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available API aliases:
  card, question     -> api/card (questions/saved questions)
  event, timeline-event -> api/timeline?include=events (timeline with events)
  timeline           -> api/timeline (timelines only)
  dashboard          -> api/dashboard
  collection         -> api/collection
  alert              -> api/alert
  pulse              -> api/pulse
  database           -> api/database
  table              -> api/table
  field              -> api/field
  segment            -> api/segment
  metric             -> api/metric
  user               -> api/user/current
  session            -> api/session/properties
  activity           -> api/activity
  setting            -> api/setting

Examples:
  python metabase_api.py --api card
  python metabase_api.py --api card --id 1
  python metabase_api.py --api event --raw
  python metabase_api.py --api dashboard --id 1 --raw
  python metabase_api.py --api raw --endpoint "table/1/query_metadata"
        """,
    )
    parser.add_argument(
        "--api",
        help="API endpoint alias (card, event, dashboard, etc.) or 'raw' for custom endpoint",
    )
    parser.add_argument(
        "--endpoint",
        help="Custom endpoint path (use with --api raw)",
    )
    parser.add_argument(
        "--id",
        type=int,
        help="Specific item ID to fetch",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw JSON output",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Hide schema tree",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("METABASE_URL", "http://localhost:3000"),
        help="Metabase base URL",
    )
    parser.add_argument(
        "--list-apis",
        action="store_true",
        help="List all available API aliases",
    )
    
    args = parser.parse_args()
    
    if args.list_apis:
        console.print("[bold]Available API Endpoints:[/bold]")
        for alias, endpoint in sorted(API_ENDPOINTS.items()):
            console.print(f"  [cyan]{alias:20}[/cyan] -> {endpoint}")
        return
    
    if not args.api:
        parser.error("--api is required (or use --list-apis to see available endpoints)")
    
    base_url = args.url.rstrip("/")
    
    session_token = get_session_token()
    if not session_token:
        console.print("[yellow]No session token found, attempting authentication...[/yellow]")
        username = os.getenv("METABASE_USERNAME", "agent@agent.com")
        password = os.getenv("METABASE_PASSWORD", "apassword123")
        session_token = authenticate(base_url, username, password)
        
        if not session_token:
            console.print("[red]Failed to get session token. Please check your credentials.[/red]")
            sys.exit(1)
    
    if args.api == "raw":
        if not args.endpoint:
            console.print("[red]--endpoint is required when using --api raw[/red]")
            sys.exit(1)
        endpoint = f"api/{args.endpoint.lstrip('api/').lstrip('/')}"
    else:
        api_key = args.api.lower()
        if api_key not in API_ENDPOINTS:
            console.print(f"[red]Unknown API: {args.api}[/red]")
            console.print(f"Available: {', '.join(API_ENDPOINTS.keys())}")
            sys.exit(1)
        endpoint = API_ENDPOINTS[api_key]
    
    console.print(f"[dim]Fetching: {base_url}/{endpoint}{'/' + str(args.id) if args.id else ''}[/dim]")
    
    data = make_request(base_url, endpoint, session_token, args.id)
    
    if data is not None:
        display_response(
            data,
            endpoint,
            show_raw=args.raw,
            show_schema=not args.no_schema,
        )
    else:
        console.print("[red]No data returned from API[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
