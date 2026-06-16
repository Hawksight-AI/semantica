"""
Semantica Knowledge Explorer : CLI Entry Point

Provides the ``semantica-explorer`` command that loads a graph from a
JSON file, starts a FastAPI server, and optionally opens the browser.

Usage::

    semantica-explorer --graph my_graph.json --port 8000
    python -m semantica.explorer --graph my_graph.json
"""

import argparse
import sys
import webbrowser

from rich.console import Console
from rich.panel import Panel

_out = Console()
_err = Console(stderr=True)


def main(argv=None):
    """CLI entry point for the Knowledge Explorer server."""
    parser = argparse.ArgumentParser(
        prog="semantica-explorer",
        description="Semantica Knowledge Explorer — interactive dashboard for KG exploration",
    )
    parser.add_argument(
        "--graph", "-g",
        required=True,
        help="Path to a ContextGraph JSON file to load.",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically.",
    )
    args = parser.parse_args(argv)


    import os
    if not os.path.isfile(args.graph):
        _err.print(f"[bold red]Error:[/bold red] graph file not found: {args.graph}")
        sys.exit(1)

    try:
        import uvicorn
    except ImportError:
        _err.print(
            "[bold red]Error:[/bold red] uvicorn is required.  Install with:\n"
            "  [dim]pip install semantica[explorer][/dim]"
        )
        sys.exit(1)

    from .session import GraphSession
    from .app import create_app

    with _out.status("[dim]Loading graph…[/dim]", spinner="dots"):
        session = GraphSession.from_file(args.graph)
    stats = session.get_stats()
    _out.print(
        f"[bold green]✓[/bold green] Graph loaded — "
        f"[cyan]{stats.get('node_count', 0)}[/cyan] nodes, "
        f"[cyan]{stats.get('edge_count', 0)}[/cyan] edges"
    )

    app = create_app(session=session)

    url = f"http://{args.host}:{args.port}"

    _LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
    if args.host not in _LOOPBACK_HOSTS:
        _err.print(
            f"[bold yellow]Warning:[/bold yellow] Binding to "
            f"[cyan]{args.host}[/cyan] exposes the Explorer to the network. "
            "The API has no authentication — all graph data will be readable "
            "and writable by any host that can reach this port."
        )

    if not args.no_browser:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    _out.print(
        Panel(
            f"[cyan]API docs[/cyan]  {url}/docs\n[cyan]Health[/cyan]    {url}/api/health",
            title=f"[bold]Semantica Explorer[/bold] · [dim]{url}[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
