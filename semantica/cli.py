"""
Semantica CLI Entry Point

This module provides the command-line interface for the Semantica framework,
enabling users to interact with the framework via terminal commands.
"""

import json
import os
import sys
import time

# Reconfigure stdout/stderr to UTF-8 on Windows before any other import
# captures sys.stdout (Rich, Click). This prevents UnicodeEncodeError from
# box-drawing characters and emoji on the default cp1252 code page.
if sys.platform == "win32":
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple

import yaml

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from . import __version__
from .core.config_manager import Config, ConfigManager
from .utils.exceptions import SemanticaError
from .utils.logging import setup_logging

if TYPE_CHECKING:
    from .core.orchestrator import Semantica

console = Console()

# ─── Visual style constants ───────────────────────────────────────────────────
_BRAND    = "bold blue"
_KEY      = "cyan"
_VAL      = "green"
_DIM      = "dim"
_SUCCESS  = "bold green"
_WARN_STY = "bold yellow"
_TABLE_BOX = box.SIMPLE_HEAD   # single underline under headers; ASCII-safe


@dataclass
class CLIContext:
    """Shared runtime context for all CLI commands."""

    config_path: Optional[str]
    config: Config
    log_level: str
    log_level_override: Optional[str] = None
    framework: Optional["Semantica"] = None
    json_output: bool = False
    quiet: bool = False
    no_color: bool = False
    dry_run_global: bool = False
    store_backend: Optional[str] = None
    vector_store_backend: Optional[str] = None
    _start: float = field(default_factory=time.perf_counter)


def _require_ctx(cli_ctx: Optional[CLIContext]) -> CLIContext:
    """Guard against uninitialized CLI context.

    Under normal Click operation (standalone_mode=True) ctx.obj is always set
    before a subcommand runs. This guard protects embedded/library usage where
    standalone_mode=False might leave ctx.obj as None.
    """
    if cli_ctx is None:
        raise click.ClickException(
            "CLI context is uninitialized — this is a bug, please report it."
        )
    return cli_ctx


_ERROR_HINTS: Dict[type, str] = {
    ConnectionRefusedError: "run 'semantica doctor' to check backend connectivity",
    FileNotFoundError:      "check that the path exists and is readable",
    PermissionError:        "check file and directory permissions",
    ImportError:            "install the missing extras: pip install semantica[…]",
    TimeoutError:           "the backend may be overloaded — retry or increase timeout in config",
}


def _show_error_card(title: str, detail: str, hint: Optional[str] = None) -> None:
    body = f"[bold]{title}[/bold]\n[{_DIM}]{detail}[/{_DIM}]"
    if hint:
        body += f"\n\n[{_KEY}]→[/{_KEY}] [{_DIM}]{hint}[/{_DIM}]"
    console.print(
        Panel(body, title="[bold red] Error [/bold red]", border_style="red", padding=(0, 2))
    )


def _run_with_error_handling(action: Callable[[], None]) -> None:
    """Run a CLI action with Rich error cards on failure."""
    try:
        action()
    except click.ClickException as exc:
        _show_error_card(type(exc).__name__, exc.format_message())
        raise SystemExit(exc.exit_code)
    except SemanticaError as exc:
        cause = exc.__cause__
        hint = _ERROR_HINTS.get(type(cause)) if cause else None
        _show_error_card("Semantica error", str(exc), hint=hint)
        raise SystemExit(1)
    except Exception as exc:
        hint = _ERROR_HINTS.get(type(exc), "run with --log-level DEBUG for a full traceback")
        _show_error_card(type(exc).__name__, str(exc), hint=hint)
        raise SystemExit(1)


def _load_config_data(file_path: Path) -> Dict[str, Any]:
    """Load and validate raw YAML/JSON config data."""
    suffix = file_path.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            with file_path.open("r", encoding="utf-8") as handle:
                config_data = yaml.safe_load(handle)
        elif suffix == ".json":
            with file_path.open("r", encoding="utf-8") as handle:
                config_data = json.load(handle)
        else:
            raise click.ClickException(
                "Unsupported configuration file format: "
                f"{suffix}. Supported formats: .yaml, .yml, .json"
            )
    except (json.JSONDecodeError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise click.ClickException(
            f"Failed to parse configuration file '{file_path}': {exc}"
        ) from exc

    if config_data is None:
        config_data = {}

    if not isinstance(config_data, dict):
        raise click.ClickException(
            "Configuration file must contain a mapping/object at the root."
        )

    return config_data


def _build_runtime_config(
    config_path: Optional[str],
    log_level: Optional[str],
) -> Config:
    """Resolve CLI config from file plus global flag overrides."""
    config_manager = ConfigManager()

    if config_path:
        config_data = _load_config_data(Path(config_path))
    else:
        config_data = {}

    logging_config = config_data.get("logging")
    if logging_config is not None and not isinstance(logging_config, dict):
        raise click.ClickException(
            "Logging configuration section must contain a mapping/object."
        )

    if log_level:
        if logging_config is None:
            logging_config = {}
            config_data["logging"] = logging_config

        logging_config["level"] = log_level.upper()

    # Keep validation disabled at CLI bootstrap to avoid blocking unrelated commands.
    return config_manager.load_from_dict(config_data, validate=False)


def _setup_cli_logging(
    logging_config: Dict[str, Any],
    *,
    quiet: bool = False,
    json_output: bool = False,
    allow_file_fallback: bool = True,
) -> None:
    """Initialize logging without making the default log file a startup blocker.

    The library logging default writes to ``semantica.log`` in the current
    working directory. CLI commands should still be usable from read-only or
    restricted directories, so default file-handler failures fall back to
    console-only logging. If the user explicitly configured a log file, keep the
    failure actionable instead of silently ignoring their configuration.
    """
    try:
        setup_logging(config=logging_config)
    except OSError as exc:
        if not allow_file_fallback:
            raise

        fallback_config = {**logging_config, "file": None}
        setup_logging(config=fallback_config)
        # Do not emit a warning: completion scripts and machine-readable
        # commands must keep stdout/stderr stable when the default log file is
        # unavailable. Explicitly configured log-file failures still raise.
        del quiet, json_output, exc  # suppress unused-variable lint


def _get_framework(cli_ctx: CLIContext) -> "Semantica":
    """Lazily initialize framework only when a command needs it."""
    if cli_ctx.framework is None:
        from .core.orchestrator import Semantica

        cli_ctx.framework = Semantica(config=cli_ctx.config.to_dict())
    return cli_ctx.framework


def _check_log_directory(cli_ctx: CLIContext) -> str:
    """Verify the configured log directory is writable.

    The CLI may already hold an open file handle for ``semantica.log``. Probe
    with a unique temporary file so Windows can check writability without
    deleting the active log file.
    """
    log_file = cli_ctx.config.get("logging.file", "semantica.log")
    if not log_file:
        return "console-only logging"

    log_path = Path(log_file).expanduser()
    log_dir = log_path.parent
    if not log_dir or str(log_dir) == ".":
        log_dir = Path.cwd()
    elif not log_dir.is_absolute():
        log_dir = Path.cwd() / log_dir

    probe_path: Optional[Path] = None
    try:
        probe_path = (
            log_dir
            / f".semantica-doctor-{os.getpid()}-{time.time_ns()}.tmp"
        )
        probe_path.write_text("ok", encoding="utf-8")
        return f"{log_dir} writable"
    finally:
        if probe_path is not None:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                # Some locked-down Windows environments allow writes but deny
                # unlinking. Logging can still proceed, so cleanup is best-effort.
                pass


def _run_build(cli_ctx: CLIContext, sources: Sequence[str]) -> None:
    """Thin wrapper around existing build orchestration flow.

    build_knowledge_base is expected to return a dict of the form::

        {
            "statistics": {
                "sources_processed": <int>,
                ...
            },
            ...
        }

    Both the top-level dict and the "statistics" key are optional; the
    function degrades gracefully when either is absent or None.
    """
    if not sources:
        raise click.UsageError(
            "At least one source is required. Use --source/-s one or more times."
        )

    if cli_ctx.dry_run_global:
        _dry(cli_ctx, "build knowledge base", sources=list(sources))
        return

    framework = _get_framework(cli_ctx)
    if cli_ctx.quiet or cli_ctx.json_output:
        result = framework.build_knowledge_base(sources=list(sources))
    elif len(sources) == 1:
        with console.status(
            f"[{_DIM}]Building knowledge base from {Path(sources[0]).name}…[/{_DIM}]",
            spinner="dots",
        ):
            result = framework.build_knowledge_base(sources=list(sources))
    elif not cli_ctx.json_output:
        result: Dict[str, Any] = {}
        with Progress(
            SpinnerColumn(),
            TextColumn("[{task.description}]", style=_DIM),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("waiting", total=len(sources))
            for src in sources:
                progress.update(task, description=Path(src).name)
                result = framework.build_knowledge_base(sources=[src])
                progress.advance(task)

    stats = result.get("statistics", {}) if isinstance(result, dict) else {}
    processed = stats.get("sources_processed")
    if processed is not None:
        _ok(cli_ctx, f"Knowledge base built — {processed} source(s) processed.")
    else:
        _ok(cli_ctx, "Knowledge base build completed.")


def _run_build_command(
    cli_ctx: CLIContext,
    source: Sequence[str],
    command_config_path: Optional[str],
) -> None:
    """Execute build command path with optional command-level config override.

    When a per-command config file is supplied, the logging configuration from
    that file is re-applied (setup_logging clears existing handlers before
    adding new ones, so there is no handler accumulation risk).
    """
    if command_config_path:
        cmd_config = _build_runtime_config(
            command_config_path, cli_ctx.log_level_override
        )
        # Re-apply logging so the command-level logging section takes effect.
        _setup_cli_logging(
            cmd_config.get("logging", {}),
            quiet=cli_ctx.quiet,
            json_output=cli_ctx.json_output,
            allow_file_fallback=False,
        )
        command_ctx = CLIContext(
            config_path=command_config_path,
            config=cmd_config,
            log_level=cli_ctx.log_level,
            log_level_override=cli_ctx.log_level_override,
            # Propagate all global flag state so command-level config overrides
            # don't silently drop --json, --quiet, --dry-run, or backend flags.
            json_output=cli_ctx.json_output,
            quiet=cli_ctx.quiet,
            no_color=cli_ctx.no_color,
            dry_run_global=cli_ctx.dry_run_global,
            store_backend=cli_ctx.store_backend,
            vector_store_backend=cli_ctx.vector_store_backend,
        )
        _run_build(command_ctx, source)
    else:
        _run_build(cli_ctx, source)


# ─── Banner, startup dashboard, Rich help ─────────────────────────────────────

_BANNER = (
    " ███████╗███████╗███╗   ███╗ █████╗ ███╗   ██╗████████╗██╗ ██████╗  █████╗ \n"
    " ██╔════╝██╔════╝████╗ ████║██╔══██╗████╗  ██║╚══██╔══╝██║██╔════╝ ██╔══██╗\n"
    " ███████╗█████╗  ██╔████╔██║███████║██╔██╗ ██║   ██║   ██║██║      ███████║\n"
    " ╚════██║██╔══╝  ██║╚██╔╝██║██╔══██║██║╚██╗██║   ██║   ██║██║      ██╔══██║\n"
    " ███████║███████╗██║ ╚═╝ ██║██║  ██║██║ ╚████║   ██║   ██║╚██████╗ ██║  ██║\n"
    " ╚══════╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═╝"
)

_HELP_SECTIONS: List[Tuple[str, List[str]]] = [
    ("📥 Data Ingestion",   ["ingest", "watch", "parse", "split", "normalize"]),
    ("🧠 Intelligence",     ["extract", "deduplicate", "reason", "decision", "temporal"]),
    ("🕸️  Knowledge Graph", ["kg"]),
    ("📊 Analytics",        ["embed", "validate", "ontology", "provenance"]),
    ("📤 Export & Viz",     ["export", "visualize"]),
    ("⚙️  Infrastructure",  ["store", "backup", "pipeline", "config"]),
    ("🖥️  Services",        ["server", "explorer", "mcp"]),
    ("🛠️  Tools",           ["init", "doctor", "changelog", "info", "shell", "completion"]),
]


class RichGroup(click.Group):
    """click.Group that renders --help with Rich-formatted grouped sections."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        import io
        is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        width = min(getattr(formatter, "width", 100) or 100, 100)
        h = Console(file=io.StringIO(), no_color=not is_tty, width=width, highlight=False)
        buf = h.file  # type: ignore[attr-defined]

        h.print()
        h.print(
            Panel(
                Text.from_markup(
                    f"[{_BRAND}]semantica[/{_BRAND}]  [{_DIM}]v{__version__}[/{_DIM}]\n"
                    "Knowledge Intelligence Platform"
                ),
                box=box.ROUNDED, padding=(0, 2), expand=False,
            )
        )
        h.print(f"[{_DIM}]Usage:[/{_DIM}]  semantica [OPTIONS] COMMAND [ARGS]...\n")

        for section_title, cmd_names in _HELP_SECTIONS:
            rows: List[Tuple[str, str]] = []
            for name in cmd_names:
                cmd = self.get_command(ctx, name)
                if cmd is None or cmd.hidden:
                    continue
                rows.append((name, cmd.get_short_help_str(limit=55)))
            if not rows:
                continue
            h.print(f"  [{_KEY}]{section_title}[/{_KEY}]")
            tbl = Table(box=None, show_header=False, show_edge=False, padding=(0, 2, 0, 4))
            tbl.add_column("cmd", style=_KEY, no_wrap=True, min_width=14)
            tbl.add_column("desc", style=_DIM)
            for name, desc in rows:
                tbl.add_row(name, desc)
            h.print(tbl)

        h.print(f"\n  [{_KEY}]Options[/{_KEY}]")
        opt_tbl = Table(box=None, show_header=False, show_edge=False, padding=(0, 2, 0, 4))
        opt_tbl.add_column("flag", style=_KEY, no_wrap=True, min_width=28)
        opt_tbl.add_column("desc", style=_DIM)
        for param in ctx.command.params:
            if isinstance(param, click.Option) and not param.hidden:
                opt_tbl.add_row("  ".join(param.opts), param.help or "")
        h.print(opt_tbl)

        h.print(f"\n  [{_KEY}]Quick Start[/{_KEY}]")
        for cmd_str, desc in [
            ("semantica ingest data/",    "load documents into the knowledge base"),
            ("semantica extract doc.pdf", "extract entities and relations"),
            ("semantica kg build",         "build the knowledge graph"),
            ("semantica reason run",       "run the reasoning engine"),
            ("semantica shell",            "interactive REPL"),
        ]:
            h.print(f"    [{_VAL}]{cmd_str:<38}[/{_VAL}][{_DIM}]{desc}[/{_DIM}]")
        h.print()
        formatter.write(buf.getvalue())


def _show_startup(cli_ctx: CLIContext) -> None:
    """Dashboard printed when semantica is run with no subcommand."""
    if cli_ctx.quiet or cli_ctx.json_output:
        return
    cfg = cli_ctx.config.to_dict()
    graph_store = (
        cli_ctx.store_backend or cfg.get("graph_db", {}).get("backend", "memory")
    )
    vector_store = (
        cli_ctx.vector_store_backend
        or cfg.get("vector_store", {}).get("backend", "faiss")
    )
    profile = cfg.get("profile", "default")

    console.print()
    console.print(Text(_BANNER, style=_BRAND), justify="center")
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[{_DIM}]Knowledge Intelligence Platform  •  v{__version__}[/{_DIM}]\n\n"
                f"[{_KEY}]🕸️  Context Graphs[/{_KEY}]      "
                f"[{_KEY}]⚡ Decision Intelligence[/{_KEY}]      "
                f"[{_KEY}]🔍 Provenance[/{_KEY}]\n"
                f"[{_KEY}]🧩 Knowledge Fusion[/{_KEY}]    "
                f"[{_KEY}]🧠 Reasoning Engine[/{_KEY}]          "
                f"[{_KEY}]📊 Explainability[/{_KEY}]"
            ),
            box=box.ROUNDED,
            padding=(1, 4),
            expand=False,
        )
    )
    console.print()
    tbl = Table(box=_TABLE_BOX, show_edge=False, padding=(0, 2))
    tbl.add_column("", style=_KEY, no_wrap=True)
    tbl.add_column("", style=_VAL)
    tbl.add_row("Graph Store",  graph_store)
    tbl.add_row("Vector Store", vector_store)
    tbl.add_row("Profile",      profile)
    tbl.add_row("Config",       cli_ctx.config_path or "(defaults)")
    console.print(tbl)
    console.print()
    console.print(
        f"  [{_DIM}]Run [bold]semantica --help[/bold] for all commands  •  "
        f"[bold]semantica shell[/bold] for interactive mode[/{_DIM}]"
    )
    console.print()


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
    cls=RichGroup,
)
@click.version_option(version=__version__)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=str),
    default=None,
    help="Path to YAML/JSON config file.",
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        case_sensitive=False,
    ),
    default=None,
    help="Override logging level for this CLI invocation.",
)
@click.option("--json", "json_output", is_flag=True, default=False,
              help="Machine-readable JSON to stdout; errors to stderr.")
@click.option("--quiet", "-q", is_flag=True, default=False,
              help="Suppress all informational output.")
@click.option("--no-color", is_flag=True, default=False,
              help="Disable colored output.")
@click.option("--dry-run", "global_dry_run", is_flag=True, default=False,
              help="Preview without writing (all write commands).")
@click.option("--store", "store_backend", default=None,
              help="Override graph store backend.")
@click.option("--vector-store", "vector_store_backend", default=None,
              help="Override vector store backend.")
@click.option("--profile", default=None, help="Named config profile.")
@click.pass_context
def main(
    ctx: click.Context,
    config_path: Optional[str],
    log_level: Optional[str],
    json_output: bool,
    quiet: bool,
    no_color: bool,
    global_dry_run: bool,
    store_backend: Optional[str],
    vector_store_backend: Optional[str],
    profile: Optional[str],
) -> None:
    """Semantica - Semantic Layer & Knowledge Engineering Framework"""
    try:
        config = _build_runtime_config(config_path=config_path, log_level=log_level)
        # Always initialize logging so file handlers are installed; --quiet only
        # suppresses console output (controlled via _ok/_dry checks).
        _setup_cli_logging(
            config.get("logging", {}),
            quiet=quiet,
            json_output=json_output,
            allow_file_fallback=config_path is None,
        )
        effective_log_level = config.get("logging.level", "INFO")
        # Reinitialize the module-level console if --no-color was requested so
        # all subsequent console.print() calls in this invocation respect the flag.
        if no_color:
            global console  # noqa: PLW0603
            console = Console(no_color=True)
        ctx.obj = CLIContext(
            config_path=config_path,
            config=config,
            log_level=effective_log_level,
            log_level_override=log_level.upper() if log_level else None,
            json_output=json_output,
            quiet=quiet,
            no_color=no_color,
            dry_run_global=global_dry_run,
            store_backend=store_backend,
            vector_store_backend=vector_store_backend,
        )
        if ctx.invoked_subcommand is None:
            _show_startup(ctx.obj)
    except click.ClickException:
        raise
    except SemanticaError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(f"Failed to initialize CLI: {exc}") from exc


@main.group(invoke_without_command=True)
@click.pass_context
def kg(ctx: click.Context) -> None:
    """Knowledge graph and semantic build commands."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.group(invoke_without_command=True)
@click.pass_context
def pipeline(ctx: click.Context) -> None:
    """Pipeline command group (foundation placeholder)."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.group(name="services", invoke_without_command=True)
@click.pass_context
def services(ctx: click.Context) -> None:
    """Service management commands (server, explorer, mcp — foundation placeholder).

    Subcommands will follow the spec layout::

        semantica services server  start|stop|status
        semantica services explorer start|stop|status
        semantica services mcp      start|stop|status
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.group(name="config", invoke_without_command=True)
@click.pass_context
def config_group(ctx: click.Context) -> None:
    """Configuration command group."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.pass_obj
def info(cli_ctx: CLIContext):
    """Display information about Semantica."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        console.print(
            Panel(
                Text.from_markup(
                    f"[{_BRAND}]Semantica Framework[/{_BRAND}]  v{__version__}\n"
                    f"[{_DIM}]Semantic Layer & Knowledge Engineering[/{_DIM}]"
                ),
                box=box.ROUNDED,
                padding=(0, 2),
                expand=False,
            )
        )

        table = Table(box=_TABLE_BOX, show_edge=False, padding=(0, 1))
        table.add_column("Component", style=_KEY, no_wrap=True)
        table.add_column("Status", style=_VAL)

        table.add_row("Core Orchestrator", "Active")
        table.add_row("Knowledge Graph Engine", "Active")
        table.add_row("Pipeline Execution", "Active")
        table.add_row("Vector Store Integration", "Active")
        table.add_row("CLI Config File", cli_ctx.config_path or "(none)")
        table.add_row("CLI Log Level", cli_ctx.log_level)

        console.print(table)

    _run_with_error_handling(_action)


@main.command()
@click.pass_context
def shell(ctx: click.Context) -> None:
    """Interactive REPL — run subcommands without the 'semantica' prefix."""
    import shlex
    cli_ctx = _require_ctx(ctx.obj)
    try:
        import readline as _rl; del _rl  # side-effect: enables line editing on Unix
    except ImportError:
        # Optional dependency: readline may be unavailable on some platforms
        # (e.g., certain Windows/Python builds). Continue without line editing.
        pass

    if not cli_ctx.quiet:
        console.print(
            Panel(
                Text.from_markup(
                    f"[{_BRAND}]Semantica Shell[/{_BRAND}]  [{_DIM}]v{__version__}[/{_DIM}]\n"
                    f"[{_DIM}]Type a subcommand (e.g. [bold]kg stats[/bold]), "
                    f"[bold]help[/bold], or [bold]exit[/bold] to quit.[/{_DIM}]"
                ),
                box=box.ROUNDED, padding=(0, 2), expand=False,
            )
        )

    while True:
        try:
            line = input("semantica> ").strip()
        except (EOFError, KeyboardInterrupt):
            if not cli_ctx.quiet:
                console.print(f"\n[{_DIM}]Goodbye![/{_DIM}]")
            break
        if not line:
            continue
        if line in ("exit", "quit", "q", ":q"):
            if not cli_ctx.quiet:
                console.print(f"[{_DIM}]Goodbye![/{_DIM}]")
            break
        if line in ("help", "?"):
            click.echo(ctx.find_root().get_help())
            continue
        try:
            args = shlex.split(line)
        except ValueError as exc:
            _warn(cli_ctx, f"Parse error: {exc}")
            continue
        cmd_name = args[0]
        cmd = main.get_command(ctx, cmd_name)
        if cmd is None:
            _warn(cli_ctx, f"Unknown command: {cmd_name!r}")
            console.print(f"  [{_DIM}]Type [bold]help[/bold] to list available commands.[/{_DIM}]")
            continue
        try:
            with cmd.make_context(cmd_name, args[1:], parent=ctx) as sub_ctx:
                cmd.invoke(sub_ctx)
        except click.exceptions.Exit:
            # Subcommands may request termination via Click's Exit; keep REPL alive.
            continue
        except SystemExit:
            # Some commands/libraries may raise SystemExit; do not exit the shell loop.
            continue
        except click.ClickException as exc:
            exc.show()
        except Exception as exc:
            _warn(cli_ctx, f"Error: {exc}")


@main.command()
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def changelog(cli_ctx: CLIContext, local_json: bool) -> None:
    """Show release notes and check for a newer version."""
    import urllib.request
    import urllib.error

    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        api = "https://api.github.com/repos/semantica-agi/semantica/releases/latest"
        try:
            req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError:
            _warn(cli_ctx, "Could not reach GitHub — check your internet connection.")
            return

        tag: str = data.get("tag_name", "unknown")
        body: str = data.get("body", "").strip()
        html_url: str = data.get("html_url", "")
        latest = tag.lstrip("v")
        current = __version__

        if _is_json(cli_ctx, local_json):
            _jecho({"current": current, "latest": latest, "url": html_url, "notes": body})
            return

        up_to_date = latest == current
        status = (
            f"[{_SUCCESS}]You are on the latest version ({current})[/{_SUCCESS}]"
            if up_to_date
            else f"[{_WARN_STY}]Update available: {current} → {latest}[/{_WARN_STY}]\n"
                 f"[{_DIM}]pip install --upgrade semantica[/{_DIM}]"
        )
        console.print(
            Panel(
                Text.from_markup(
                    f"[{_BRAND}]Semantica {tag}[/{_BRAND}]\n\n"
                    f"{body}\n\n"
                    f"{status}"
                ),
                title="[bold]Changelog[/bold]",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        if html_url and not up_to_date:
            console.print(f"  [{_DIM}]Full notes: {html_url}[/{_DIM}]")

    _run_with_error_handling(_action)


@main.command()
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def doctor(cli_ctx: CLIContext, local_json: bool) -> None:
    """Run a health check on all Semantica components and backends."""
    import importlib.metadata
    cli_ctx = _require_ctx(cli_ctx)

    Check = Tuple[str, str, str, Optional[str]]  # label, status, note, hint

    def _check(label: str, fn: "Callable[[], str]", hint: Optional[str] = None) -> Check:
        try:
            note = fn()
            return label, "ok", note, None
        except Exception as exc:
            return label, "fail", str(exc), hint

    def _action() -> None:
        checks: List[Check] = []

        # Python version
        pv = sys.version_info
        checks.append(("Python", "ok" if pv >= (3, 8) else "fail",
                        f"{pv.major}.{pv.minor}.{pv.micro}",
                        "upgrade to Python 3.8+" if pv < (3, 8) else None))

        # Semantica version
        checks.append(("semantica", "ok", __version__, None))

        # Rich version
        def _rich_ver() -> str:
            return importlib.metadata.version("rich")
        checks.append(_check("rich", _rich_ver))

        # Graph store reachability
        def _graph() -> str:
            cfg = cli_ctx.config.to_dict()
            backend = cli_ctx.store_backend or cfg.get("graph_db", {}).get("backend", "memory")
            if backend == "memory":
                return "memory (always available)"
            gs = _get_graph_store(cli_ctx)
            gs.ping() if hasattr(gs, "ping") else gs.connect()
            return f"{backend} reachable"
        checks.append(_check("Graph store", _graph, hint="run 'semantica store list' to see configured backends"))

        # Vector store
        def _vector() -> str:
            cfg = cli_ctx.config.to_dict()
            backend = cli_ctx.vector_store_backend or cfg.get("vector_store", {}).get("backend", "faiss")
            if backend == "faiss":
                import faiss  # noqa: F401
            return f"{backend} importable"
        checks.append(_check("Vector store", _vector, hint="pip install semantica[vectorstore-…]"))

        # LLM provider keys
        for provider, var in [("OpenAI", "OPENAI_API_KEY"), ("Anthropic", "ANTHROPIC_API_KEY"),
                               ("Groq", "GROQ_API_KEY")]:
            val = os.environ.get(var, "")
            if val:
                checks.append((provider, "ok", f"{var} set ({val[:8]}…)", None))
            else:
                checks.append((provider, "warn", f"{var} not set", f"export {var}=…"))

        # Config file
        if cli_ctx.config_path:
            ok = Path(cli_ctx.config_path).is_file()
            checks.append(("Config file", "ok" if ok else "fail",
                            cli_ctx.config_path, None))
        else:
            checks.append(("Config file", "warn", "using defaults (no --config)", "run 'semantica init'"))

        checks.append(_check("Log directory", lambda: _check_log_directory(cli_ctx)))

        if _is_json(cli_ctx, local_json):
            _jecho([{"check": lbl, "status": st, "note": note, "hint": hint}
                    for lbl, st, note, hint in checks])
            return

        tbl = Table(box=_TABLE_BOX, show_edge=False, padding=(0, 2))
        tbl.add_column("Check",  style=_KEY, no_wrap=True, min_width=16)
        tbl.add_column("Status", no_wrap=True, min_width=6)
        tbl.add_column("Note",   style=_DIM)
        tbl.add_column("Hint",   style=_DIM)

        icons = {"ok": f"[{_SUCCESS}] ✓[/{_SUCCESS}]",
                 "warn": f"[{_WARN_STY}] ⚠[/{_WARN_STY}]",
                 "fail": "[bold red] ✗[/bold red]"}

        errors = warns = 0
        for lbl, st, note, hint in checks:
            tbl.add_row(lbl, icons.get(st, st), note or "", hint or "")
            if st == "fail":
                errors += 1
            elif st == "warn":
                warns += 1

        console.print()
        console.print(tbl)
        console.print()
        summary = (f"[{_SUCCESS}]All checks passed[/{_SUCCESS}]" if not errors and not warns
                   else f"[bold red]{errors} error(s)[/bold red]  [{_WARN_STY}]{warns} warning(s)[/{_WARN_STY}]")
        console.print(f"  {summary}")
        console.print()

    _run_with_error_handling(_action)


@main.command(name="init")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing config.")
@click.pass_obj
def init_cmd(cli_ctx: CLIContext, force: bool) -> None:
    """Interactive wizard to create ~/.semantica/config.yaml."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        config_dir = Path.home() / ".semantica"
        config_file = config_dir / "config.yaml"

        if config_file.exists() and not force:
            _warn(cli_ctx, f"Config already exists at {config_file}  (use --force to overwrite)")
            return

        if not cli_ctx.quiet:
            console.print(
                Panel(
                    Text.from_markup(
                        f"[{_BRAND}]Semantica Setup Wizard[/{_BRAND}]\n"
                        f"[{_DIM}]Creates ~/.semantica/config.yaml  •  press Ctrl+C to abort[/{_DIM}]"
                    ),
                    box=box.ROUNDED, padding=(0, 2), expand=False,
                )
            )
            console.print()

        graph_backend = click.prompt(
            "  Graph store backend",
            type=click.Choice(["memory", "neo4j", "falkordb", "neptune"], case_sensitive=False),
            default="memory",
        )
        vector_backend = click.prompt(
            "  Vector store backend",
            type=click.Choice(["faiss", "qdrant", "pinecone", "weaviate", "milvus"], case_sensitive=False),
            default="faiss",
        )
        llm_provider = click.prompt(
            "  LLM provider",
            type=click.Choice(["none", "openai", "anthropic", "groq", "ollama"], case_sensitive=False),
            default="none",
        )

        cfg: Dict[str, Any] = {
            "graph_db":     {"backend": graph_backend},
            "vector_store": {"backend": vector_backend},
        }

        if llm_provider != "none":
            env_var = f"{llm_provider.upper()}_API_KEY"
            existing = os.environ.get(env_var, "")
            prompt_str = f"  {env_var}" + (f" [{existing[:8]}…]" if existing else "")
            key = click.prompt(prompt_str, default=existing, hide_input=True, show_default=False)
            if key:
                cfg["llm"] = {"provider": llm_provider, "api_key_env": env_var}
                os.environ[env_var] = key

        config_dir.mkdir(parents=True, exist_ok=True)
        with config_file.open("w", encoding="utf-8") as fh:
            yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)

        console.print()
        _ok(cli_ctx, f"Config written to {config_file}")
        _info(cli_ctx, "Run 'semantica doctor' to verify your setup.")

    _run_with_error_handling(_action)


@main.command(name="watch")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--type", "ingestor_type", default=None, help="Force ingestor type.")
@click.option("--store", "store_override", default=None, help="Target graph backend.")
@click.option("--patterns", default="*.pdf,*.docx,*.txt,*.csv,*.json",
              show_default=True, help="Comma-separated glob patterns to match.")
@click.pass_obj
def watch_cmd(cli_ctx: CLIContext, path: str, ingestor_type: Optional[str],
              store_override: Optional[str], patterns: str) -> None:
    """Watch a directory and auto-ingest new or changed files.

    \b
    Requires: pip install semantica[watch]
    Examples:
      semantica watch ./data/contracts/
      semantica watch ./reports/ --patterns "*.pdf,*.docx"
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileSystemEvent
    except ImportError:
        raise click.ClickException(
            "watchdog is required — install it with: pip install semantica[watch]"
        )

    cli_ctx = _require_ctx(cli_ctx)
    watch_path = Path(path).resolve()
    pat_list = [p.strip() for p in patterns.split(",")]

    class _Handler(FileSystemEventHandler):
        def on_created(self, event: "FileSystemEvent") -> None:
            self._handle(event)

        def on_modified(self, event: "FileSystemEvent") -> None:
            self._handle(event)

        def _handle(self, event: "FileSystemEvent") -> None:
            if event.is_directory:
                return
            p = Path(str(event.src_path))
            if not any(p.match(pat) for pat in pat_list):
                return
            _info(cli_ctx, f"Detected {p.name} — ingesting…")
            try:
                from .ingest import ingest as _ingest
                kwargs: Dict[str, Any] = {}
                if ingestor_type:
                    kwargs["source_type"] = ingestor_type
                if store_override or cli_ctx.store_backend:
                    kwargs["store"] = store_override or cli_ctx.store_backend
                _ingest(str(p), **kwargs)
                _ok(cli_ctx, f"{p.name}")
            except Exception as exc:
                _warn(cli_ctx, f"{p.name}: {exc}")

    if not cli_ctx.quiet:
        console.print(
            Panel(
                Text.from_markup(
                    f"[{_BRAND}]Watching[/{_BRAND}] {watch_path}\n"
                    f"[{_DIM}]Patterns: {patterns}  •  Ctrl+C to stop[/{_DIM}]"
                ),
                box=box.ROUNDED, padding=(0, 2), expand=False,
            )
        )

    observer = Observer()
    observer.schedule(_Handler(), str(watch_path), recursive=True)
    observer.start()
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    if not cli_ctx.quiet:
        console.print(f"\n[{_DIM}]Stopped watching.[/{_DIM}]")


@kg.command("build")
@click.option("--source", "-s", multiple=True, help="Data sources to process.")
@click.option(
    "-c",
    "--config",
    "command_config_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=str),
    default=None,
    help="Path to YAML/JSON config file.",
)
@click.pass_obj
def kg_build(
    cli_ctx: CLIContext,
    source: Sequence[str],
    command_config_path: Optional[str],
):
    """Build a knowledge base from sources."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        _run_build_command(cli_ctx, source, command_config_path)

    _run_with_error_handling(_action)


@main.command("build", hidden=True)
@click.option("--source", "-s", multiple=True, help="Data sources to process.")
@click.option(
    "-c",
    "--config",
    "command_config_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=str),
    default=None,
    help="Path to YAML/JSON config file.",
)
@click.pass_obj
def build_alias(
    cli_ctx: CLIContext,
    source: Sequence[str],
    command_config_path: Optional[str],
):
    """Backward-compatible alias for 'kg build'."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        _run_build_command(cli_ctx, source, command_config_path)

    _run_with_error_handling(_action)


# ─── Graph store helper ──────────────────────────────────────────────────────


def _get_graph_store(cli_ctx: CLIContext) -> Any:
    """Return a GraphStore instance wired from the current CLIContext config."""
    from .graph_store import GraphStore
    cfg = cli_ctx.config.to_dict()
    graph_db = dict(cfg.get("graph_db", {}))
    backend = cli_ctx.store_backend or graph_db.pop("backend", "neo4j")
    return GraphStore(backend=backend, **graph_db)


# ─── Output helpers ──────────────────────────────────────────────────────────


def _jecho(data: Any) -> None:
    """Emit JSON to stdout."""
    click.echo(json.dumps(data, default=str))


def _ok(cli_ctx: CLIContext, text: str) -> None:
    if not cli_ctx.quiet:
        elapsed = time.perf_counter() - cli_ctx._start
        console.print(f"[{_SUCCESS}] ✓[/{_SUCCESS}] {text}  [{_DIM}]{elapsed:.1f}s[/{_DIM}]")


def _info(cli_ctx: CLIContext, text: str) -> None:
    if not cli_ctx.quiet:
        console.print(f"[{_DIM}] ·[/{_DIM}] {text}")


def _warn(cli_ctx: CLIContext, text: str) -> None:
    console.print(f"[{_WARN_STY}] ⚠[/{_WARN_STY}] {text}")


def _dry(cli_ctx: CLIContext, action: str, *, json_out: bool = False, **fields: Any) -> None:
    payload = {"dry_run": True, "action": action, **fields}
    if json_out or cli_ctx.json_output:
        _jecho(payload)
    elif not cli_ctx.quiet:
        console.print(f"[{_WARN_STY}] Dry run:[/{_WARN_STY}] would {action}: {fields}")


def _is_dry(cli_ctx: CLIContext, local_dry: bool) -> bool:
    return local_dry or cli_ctx.dry_run_global


def _is_json(cli_ctx: CLIContext, local_json: bool) -> bool:
    return local_json or cli_ctx.json_output


def _pprint(cli_ctx: CLIContext, data: Any) -> None:
    """Pretty-print a result to the terminal.

    Dicts and lists are rendered as syntax-highlighted JSON.
    Strings are printed as-is. Respects --quiet and --no-color.
    """
    if cli_ctx.quiet:
        return
    if isinstance(data, (dict, list)):
        console.print(
            Syntax(
                json.dumps(data, indent=2, default=str),
                "json",
                theme="monokai",
                word_wrap=True,
            )
        )
    else:
        console.print(str(data))


def _serialize_extract_result(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list):
        return [_serialize_extract_result(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize_extract_result(v) for k, v in obj.items()}
    return obj


# ─── Additional kg subcommands ────────────────────────────────────────────────


@kg.command("query")
@click.argument("query_str")
@click.option("--lang", type=click.Choice(["cypher", "sparql"]), default="cypher",
              show_default=True, help="Query language.")
@click.option("--limit", default=100, type=int, show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_query(cli_ctx: CLIContext, query_str: str, lang: str, limit: int, local_json: bool) -> None:
    """Run a Cypher or SPARQL query against the knowledge graph."""
    cli_ctx = _require_ctx(cli_ctx)
    json_out = _is_json(cli_ctx, local_json)

    def _action() -> None:
        try:
            from .graph_store import execute_query
        except ImportError as exc:
            raise click.ClickException(f"Graph store module not available: {exc}") from exc
        result = execute_query(query_str, lang=lang, limit=limit,
                               config=cli_ctx.config.to_dict())
        if json_out:
            _jecho(result if isinstance(result, (dict, list)) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@kg.command("stats")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_stats(cli_ctx: CLIContext, fmt: str, local_json: bool) -> None:
    """Show node/edge counts, density, and graph metrics."""
    cli_ctx = _require_ctx(cli_ctx)
    json_out = _is_json(cli_ctx, local_json) or fmt == "json"

    def _action() -> None:
        try:
            from .kg import GraphAnalyzer

            stats = GraphAnalyzer(
                config=cli_ctx.config.to_dict()
            ).compute_metrics()
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        if json_out:
            _jecho(stats)
        else:
            table = Table(title="[bold]Knowledge Graph Statistics[/bold]",
                          box=_TABLE_BOX, show_edge=False, padding=(0, 1))
            table.add_column("Metric", style=_KEY, no_wrap=True)
            table.add_column("Value", style=_VAL)
            for k, v in (stats.items() if isinstance(stats, dict) else []):
                table.add_row(str(k), str(v))
            console.print(table)

    _run_with_error_handling(_action)


@kg.command("analyze")
@click.option("--mode", type=click.Choice(["centrality", "community", "connectivity", "all"]),
              default="all", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_analyze(cli_ctx: CLIContext, mode: str, local_json: bool) -> None:
    """Run centrality, community detection, or connectivity analysis."""
    cli_ctx = _require_ctx(cli_ctx)
    json_out = _is_json(cli_ctx, local_json)

    def _action() -> None:
        try:
            from .kg import GraphAnalyzer
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        result = GraphAnalyzer(config=cli_ctx.config.to_dict()).analyze(mode=mode)
        if json_out:
            _jecho(result if isinstance(result, dict) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@kg.command("find-path")
@click.option("--from", "from_entity", required=True, help="Source entity name.")
@click.option("--to", "to_entity", required=True, help="Target entity name.")
@click.option("--type", "path_type",
              type=click.Choice(["shortest", "semantic", "causal"]),
              default="shortest", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_find_path(cli_ctx: CLIContext, from_entity: str, to_entity: str,
                 path_type: str, local_json: bool) -> None:
    """Find a path between two entities in the knowledge graph."""
    cli_ctx = _require_ctx(cli_ctx)
    json_out = _is_json(cli_ctx, local_json)

    def _action() -> None:
        try:
            from .kg import PathFinder
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        path = PathFinder(config=cli_ctx.config.to_dict()).find_path(
            from_entity, to_entity, path_type=path_type
        )
        if json_out:
            _jecho(path if isinstance(path, dict) else {"path": path})
        else:
            _pprint(cli_ctx, path)

    _run_with_error_handling(_action)


@kg.command("resolve")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_resolve(cli_ctx: CLIContext, local_json: bool) -> None:
    """Run entity resolution across the knowledge graph."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import EntityResolver
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        result = EntityResolver(config=cli_ctx.config.to_dict()).resolve()
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"result": str(result)})
        else:
            _ok(cli_ctx, f"Entity resolution complete: {result}")

    _run_with_error_handling(_action)


@kg.command("predict")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_predict(cli_ctx: CLIContext, local_json: bool) -> None:
    """Run link prediction on the knowledge graph."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import LinkPredictor
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        result = LinkPredictor(config=cli_ctx.config.to_dict()).predict()
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@kg.command("validate")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def kg_validate_cmd(cli_ctx: CLIContext, local_json: bool) -> None:
    """Run a graph integrity check."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import GraphValidator
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        result = GraphValidator(config=cli_ctx.config.to_dict()).validate()
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"result": str(result)})
        else:
            _ok(cli_ctx, f"Graph validation: {result}")

    _run_with_error_handling(_action)


# ─── Data In ──────────────────────────────────────────────────────────────────


_INGEST_TYPES = [
    "file", "web", "parquet", "xml", "rest", "db", "duckdb", "elastic",
    "email", "feed", "gdrive", "huggingface", "mcp", "mongo", "repo",
    "snowflake", "stream",
]

_INGEST_FORMATS = ["pdf", "docx", "csv", "excel", "html", "json", "parquet", "xml", "rdf"]


@main.command()
@click.argument("source")
@click.option("--type", "ingestor_type", type=click.Choice(_INGEST_TYPES), default=None,
              help="Force ingestor type (auto-detected by default).")
@click.option("--format", "fmt", type=click.Choice(_INGEST_FORMATS), default=None,
              help="Format hint.")
@click.option("--recursive", is_flag=True, default=False, help="Recurse into directories.")
@click.option("--watch", is_flag=True, default=False, help="Re-ingest on file changes.")
@click.option("--batch-size", default=500, type=int, show_default=True)
@click.option("--store", "store_override", default=None,
              help="Target graph backend: neo4j falkordb age neptune")
@click.option("--output", default=None, type=click.Path(), help="Write to file instead of graph store.")
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ingest(
    cli_ctx: CLIContext, source: str, ingestor_type: Optional[str], fmt: Optional[str],
    recursive: bool, watch: bool, batch_size: int, store_override: Optional[str],
    output: Optional[str], local_dry: bool, local_json: bool,
) -> None:
    """Load files, URLs, databases, or streams into the graph.

    \b
    Examples:
      semantica ingest ./reports/q1.pdf
      semantica ingest ./data/ --recursive --format csv
      semantica ingest https://feeds.example.com/news --type feed --watch
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "ingest", json_out=_is_json(cli_ctx, local_json),
                 source=source, type=ingestor_type, format=fmt)
            return
        kwargs: Dict[str, Any] = {"batch_size": batch_size}
        if ingestor_type:
            kwargs["source_type"] = ingestor_type
        if fmt:
            kwargs["format"] = fmt
        if recursive:
            kwargs["recursive"] = True
        if watch:
            kwargs["watch"] = True
        if store_override or cli_ctx.store_backend:
            kwargs["store"] = store_override or cli_ctx.store_backend
        if output:
            kwargs["output"] = output
        try:
            from .ingest import ingest as _ingest
            label = Path(source).name if Path(source).exists() else source
            if cli_ctx.quiet or cli_ctx.json_output:
                result = _ingest(source, **kwargs)
            else:
                with console.status(
                    f"[{_DIM}]Ingesting {label}{'  (recursive)' if recursive else ''}…[/{_DIM}]",
                    spinner="dots",
                ):
                    result = _ingest(source, **kwargs)
        except ImportError as exc:
            raise click.ClickException(f"Ingest module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"status": "ok"})
        else:
            _ok(cli_ctx, f"Ingested: {source}")

    _run_with_error_handling(_action)


@main.command("parse")
@click.argument("file", type=click.Path(exists=True))
@click.option("--parser",
              type=click.Choice(["pdf", "docx", "code", "csv", "email", "excel",
                                  "html", "image", "json", "pptx", "xml", "web"]),
              default=None, help="Parser override.")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml", "table"]),
              default="json", show_default=True)
@click.pass_obj
def parse_cmd(cli_ctx: CLIContext, file: str, parser: Optional[str], fmt: str) -> None:
    """Parse a document into structured content (stdout).

    \b
    Examples:
      semantica parse contract.pdf | jq '.entities'
      semantica parse source.py --parser code --format json > parsed.json
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        kwargs: Dict[str, Any] = {"file_path": file}
        if parser:
            kwargs["parser"] = parser
        try:
            from .parse import parse_document
            if cli_ctx.quiet or cli_ctx.json_output or fmt == "json":
                result = parse_document(**kwargs)
            else:
                with console.status(f"[{_DIM}]Parsing {Path(file).name}…[/{_DIM}]", spinner="dots"):
                    result = parse_document(**kwargs)
        except ImportError as exc:
            raise click.ClickException(f"Parse module not available: {exc}") from exc
        if fmt == "json" or _is_json(cli_ctx, False):
            click.echo(json.dumps(result, default=str))
        elif fmt == "yaml":
            click.echo(yaml.dump(result, default_flow_style=False))
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@main.command()
@click.argument("input_path")
@click.option("--strategy",
              type=click.Choice(["recursive", "semantic", "entity-aware", "relation-aware",
                                  "sliding-window", "structural", "table"]),
              default="recursive", show_default=True)
@click.option("--chunk-size", default=512, type=int, show_default=True)
@click.option("--overlap", default=64, type=int, show_default=True)
@click.option("--format", "fmt", type=click.Choice(["json", "jsonl", "text"]),
              default="json", show_default=True)
@click.option("--output", default=None, type=click.Path())
@click.pass_obj
def split(
    cli_ctx: CLIContext, input_path: str, strategy: str, chunk_size: int,
    overlap: int, fmt: str, output: Optional[str],
) -> None:
    """Chunk documents with configurable strategies.

    \b
    Examples:
      semantica split report.pdf --strategy semantic --chunk-size 256
      semantica split data.csv --strategy table --format jsonl > chunks.jsonl
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .split import split_recursive, get_split_method
            fn = get_split_method(strategy) if strategy != "recursive" else split_recursive
            chunks = fn(input_path, chunk_size=chunk_size, overlap=overlap)
        except ImportError as exc:
            raise click.ClickException(f"Split module not available: {exc}") from exc
        if fmt == "jsonl":
            lines = "\n".join(json.dumps(c, default=str) for c in (chunks or []))
        elif fmt == "json":
            lines = json.dumps(chunks, default=str)
        else:
            lines = "\n".join(str(c) for c in (chunks or []))
        if output:
            Path(output).write_text(lines, encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        else:
            click.echo(lines)

    _run_with_error_handling(_action)


@main.command()
@click.argument("input_text")
@click.option("--mode", type=click.Choice(["text", "temporal", "entity", "all"]),
              default="all", show_default=True)
@click.option("--domain", type=click.Choice(["healthcare", "legal", "finance", "general"]),
              default="general", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def normalize(cli_ctx: CLIContext, input_text: str, mode: str, domain: str,
              local_json: bool) -> None:
    """Normalize text and dates (deterministic, no LLM).

    \b
    Examples:
      semantica normalize "We met last Tuesday around noon." --mode temporal
      semantica normalize entities.json --mode entity --domain legal
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        src = Path(input_text)
        text = src.read_text(encoding="utf-8") if src.is_file() else input_text
        try:
            from .normalize import normalize_text, normalize_date, normalize_entity
            if mode == "temporal":
                result = normalize_date(text, domain=domain)
            elif mode == "entity":
                result = normalize_entity(text, domain=domain)
            elif mode == "text":
                result = normalize_text(text)
            else:
                result = normalize_text(normalize_date(normalize_entity(text, domain=domain)))
        except ImportError as exc:
            raise click.ClickException(f"Normalize module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho({"result": result})
        else:
            console.print(str(result))

    _run_with_error_handling(_action)


# ─── Processing ───────────────────────────────────────────────────────────────


@main.command()
@click.argument("input_path")
@click.option("--mode",
              type=click.Choice(["ner", "relations", "triplets", "events", "coreference", "all"]),
              default="all", show_default=True)
@click.option("--method", type=click.Choice(["pattern", "ml", "llm"]),
              default="ml", show_default=True)
@click.option("--model", default=None, help="LLM model when using --method llm.")
@click.option("--confidence", default=0.5, type=float, show_default=True,
              help="Minimum confidence 0.0-1.0.")
@click.option("--temporal", is_flag=True, default=False, help="Also extract temporal bounds.")
@click.option("--format", "fmt",
              type=click.Choice(["json", "yaml", "table", "rdf"]),
              default="json", show_default=True)
@click.option("--output", default=None, type=click.Path())
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def extract(
    cli_ctx: CLIContext, input_path: str, mode: str, method: str,
    model: Optional[str], confidence: float, temporal: bool,
    fmt: str, output: Optional[str], local_json: bool,
) -> None:
    """Run extraction (NER, relations, triplets, events) on text or files.

    \b
    Examples:
      semantica extract "Alice signed the contract with Acme Corp."
      semantica extract report.pdf --mode triplets --method llm --model claude-sonnet-4-6
      cat text.txt | semantica extract - --mode relations
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if input_path == "-":
            text = sys.stdin.read()
        else:
            p = Path(input_path)
            text = p.read_text(encoding="utf-8") if p.exists() else input_path
        try:
            from .semantic_extract import (
                NERExtractor,
                RelationExtractor,
                TripletExtractor,
                EventDetector,
            )

            extractor_config: Dict[str, Any] = {"min_confidence": confidence}
            if model:
                extractor_config["llm_model"] = model

            def _run_extraction() -> Any:
                if mode == "triplets":
                    extractor = TripletExtractor(
                        method=method, include_temporal=temporal, **extractor_config
                    )
                    return extractor.extract(text)
                elif mode == "relations":
                    ner = NERExtractor(method=method, **extractor_config)
                    entities = ner.extract(text)
                    extractor = RelationExtractor(
                        method=method, confidence_threshold=confidence, **extractor_config
                    )
                    return extractor.extract(text, entities=entities)
                elif mode == "ner":
                    extractor = NERExtractor(method=method, **extractor_config)
                    return extractor.extract(text)
                elif mode == "events":
                    extractor = EventDetector(method=method, **extractor_config)
                    return extractor.extract(text)
                else:
                    raise click.ClickException(
                        f"Extraction mode '{mode}' is not yet wired to a runtime extractor."
                    )

            if cli_ctx.quiet or cli_ctx.json_output:
                result = _run_extraction()
            else:
                with console.status(
                    f"[{_DIM}]Running {mode} extraction ({method})…[/{_DIM}]",
                    spinner="dots",
                ):
                    result = _run_extraction()
        except ImportError as exc:
            raise click.ClickException(f"Extract module not available: {exc}") from exc
        serialized = _serialize_extract_result(result)
        json_out = _is_json(cli_ctx, local_json) or fmt == "json"
        if json_out:
            text_out = json.dumps(
                serialized if isinstance(serialized, dict) else {"result": serialized},
                default=str,
            )
        elif fmt == "yaml":
            text_out = yaml.dump(serialized, default_flow_style=False)
        else:
            text_out = str(serialized)
        if output:
            Path(output).write_text(text_out, encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        else:
            click.echo(text_out)

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def embed(ctx: click.Context) -> None:
    """Generate, index, and search embeddings."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@embed.command("generate")
@click.argument("input_path")
@click.option("--model",
              type=click.Choice(["sentence-transformers", "fastembed", "openai", "bge"]),
              default="sentence-transformers", show_default=True)
@click.option("--store", "store_backend",
              type=click.Choice(["faiss", "pinecone", "weaviate", "qdrant", "milvus", "pgvector"]),
              default=None)
@click.option("--namespace", default=None)
@click.option("--output", default=None, type=click.Path())
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def embed_generate(cli_ctx: CLIContext, input_path: str, model: str,
                   store_backend: Optional[str], namespace: Optional[str],
                   output: Optional[str], local_json: bool) -> None:
    """Embed entities or documents and optionally index them.

    \b
    Example:
      semantica embed generate ./entities.json --model sentence-transformers --output embeddings.parquet
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .embeddings import generate_embeddings
            _gen = lambda: generate_embeddings(
                input_path, model=model,
                store=store_backend or cli_ctx.vector_store_backend,
                namespace=namespace,
            )
            if cli_ctx.quiet or cli_ctx.json_output:
                result = _gen()
            else:
                with console.status(
                    f"[{_DIM}]Generating embeddings ({model})…[/{_DIM}]",
                    spinner="dots",
                ):
                    result = _gen()
        except ImportError as exc:
            raise click.ClickException(f"Embeddings module not available: {exc}") from exc
        if output:
            Path(output).write_text(json.dumps(result, default=str), encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        elif _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"status": "ok"})
        else:
            _ok(cli_ctx, "Embeddings generated.")

    _run_with_error_handling(_action)


@embed.command("search")
@click.argument("query_text")
@click.option("--store",
              type=click.Choice(["faiss", "pinecone", "weaviate", "qdrant", "milvus", "pgvector"]),
              default=None)
@click.option("--top-k", default=10, type=int, show_default=True)
@click.option("--hybrid", is_flag=True, default=False, help="Dense + sparse hybrid search.")
@click.option("--namespace", default=None)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def embed_search(cli_ctx: CLIContext, query_text: str, store: Optional[str],
                 top_k: int, hybrid: bool, namespace: Optional[str], local_json: bool) -> None:
    """Semantic similarity search over the vector store.

    \b
    Example:
      semantica embed search "CEO of Acme Corp" --store qdrant --top-k 5 --hybrid
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .embeddings.methods import embed_text
            from .vector_store import search_vectors
            query_vector = embed_text(query_text)
            results = search_vectors(
                query_vector,
                k=top_k,
                hybrid=hybrid,
                store=store or cli_ctx.vector_store_backend,
                namespace=namespace,
            )
        except ImportError as exc:
            raise click.ClickException(f"Embeddings/vector store module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(results if isinstance(results, (dict, list)) else {"results": str(results)})
        else:
            _pprint(cli_ctx, results)

    _run_with_error_handling(_action)


@embed.command("index")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--store",
              type=click.Choice(["faiss", "pinecone", "weaviate", "qdrant", "milvus", "pgvector"]),
              default="faiss", show_default=True)
@click.option("--namespace", default=None)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def embed_index(cli_ctx: CLIContext, file_path: str, store: str,
                namespace: Optional[str], local_json: bool) -> None:
    """Index a Parquet/JSON embeddings file into a vector store.

    \b
    Example:
      semantica embed index embeddings.parquet --store faiss --namespace production
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            import numpy as np
            import pandas as pd
            from .vector_store import create_index
        except ImportError as exc:
            raise click.ClickException(f"Vector store module not available: {exc}") from exc

        fp = Path(file_path)
        suffix = fp.suffix.lower()
        if suffix == ".parquet":
            df = pd.read_parquet(fp)
        elif suffix in (".json", ".jsonl"):
            df = pd.read_json(fp, lines=(suffix == ".jsonl"))
        else:
            raise click.ClickException(
                f"Unsupported embeddings file format '{suffix}'. Use .parquet, .json, or .jsonl"
            )

        vector_col = next(
            (c for c in df.columns if isinstance(df[c].iloc[0] if len(df) else None, (list, np.ndarray))),
            None,
        ) if len(df) else None
        if vector_col is None:
            raise click.ClickException("No vector column found in embeddings file")

        id_col = next(
            (c for c in df.columns if c != vector_col and df[c].dtype == object), None
        )
        vectors = [np.array(v, dtype=np.float32) for v in df[vector_col]]
        ids = list(df[id_col].astype(str)) if id_col else None

        result = create_index(vectors, ids=ids, store=store, namespace=namespace)
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"status": "ok", "indexed": len(vectors)})
        else:
            _ok(cli_ctx, f"Indexed {len(vectors)} vectors from {file_path} into {store}")

    _run_with_error_handling(_action)


@main.command()
@click.option("--strategy", type=click.Choice(["blocking", "semantic", "hybrid"]),
              default="hybrid", show_default=True)
@click.option("--min-similarity", default=0.7, type=float, show_default=True)
@click.option("--action", "dedup_action",
              type=click.Choice(["detect", "merge", "report"]),
              default="detect", show_default=True)
@click.option("--sort-by",
              type=click.Choice(["similarity", "entity_count", "cluster_size"]),
              default="similarity")
@click.option("--output", default=None, type=click.Path())
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def deduplicate(
    cli_ctx: CLIContext, strategy: str, min_similarity: float, dedup_action: str,
    sort_by: str, output: Optional[str], local_dry: bool, local_json: bool,
) -> None:
    """Detect and resolve duplicate entities in the knowledge graph.

    \b
    Examples:
      semantica deduplicate --strategy hybrid --min-similarity 0.8
      semantica deduplicate --action merge --dry-run
      semantica deduplicate --action report --output duplicates.csv
    """
    cli_ctx = _require_ctx(cli_ctx)

    strategy_map = {
        "blocking": "blocking_v2",
        "semantic": "legacy",
        "hybrid": "hybrid_v2",
    }

    def _load_entities() -> List[Dict[str, Any]]:
        from .graph_store import get_nodes
        from .graph_store.config import graph_store_config

        graph_db = dict(cli_ctx.config.to_dict().get("graph_db", {}))
        backend = cli_ctx.store_backend or graph_db.pop("backend", None)
        previous_graph_config = graph_store_config.get_all()
        graph_store_config.update(graph_db)
        if backend:
            graph_store_config.set("default_backend", backend)
        try:
            return get_nodes(limit=sys.maxsize)
        finally:
            graph_store_config.update(previous_graph_config)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "deduplicate", json_out=_is_json(cli_ctx, local_json),
                 strategy=strategy, dedup_action=dedup_action)
            return
        try:
            from .deduplication import detect_duplicates
            from .deduplication.entity_merger import EntityMerger

            def _run_dedup() -> Any:
                entities = _load_entities()
                candidate_strategy = strategy_map.get(strategy, strategy)
                detector_sort_by = "similarity_score" if sort_by == "similarity" else "confidence"
                detection_kwargs: Dict[str, Any] = {
                    "candidate_strategy": candidate_strategy,
                    "sort_by": detector_sort_by,
                }
                if dedup_action == "detect":
                    return detect_duplicates(
                        entities,
                        method="group",
                        similarity_threshold=min_similarity,
                        **detection_kwargs,
                    )
                elif dedup_action == "merge":
                    merger = EntityMerger()
                    return merger.merge_duplicates(
                        entities,
                        threshold=min_similarity,
                        **detection_kwargs,
                    )
                else:  # report — pairwise pairs with similarity scores
                    pairs = detect_duplicates(
                        entities,
                        method="pairwise",
                        similarity_threshold=min_similarity,
                        **detection_kwargs,
                    )
                    return {
                        "total_entities": len(entities),
                        "duplicate_pairs": len(pairs),
                        "pairs": [
                            {
                                "entity_1": getattr(p, "entity1_id", None),
                                "entity_2": getattr(p, "entity2_id", None),
                                "similarity": getattr(p, "similarity_score", None),
                            }
                            for p in pairs
                        ],
                    }

            if cli_ctx.quiet or cli_ctx.json_output:
                result = _run_dedup()
            else:
                with console.status(
                    f"[{_DIM}]Running deduplication ({strategy}, {dedup_action})…[/{_DIM}]",
                    spinner="dots",
                ):
                    result = _run_dedup()
        except ImportError as exc:
            raise click.ClickException(f"Deduplication module not available: {exc}") from exc
        if output:
            Path(output).write_text(json.dumps(result, default=str), encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        elif _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, (dict, list)) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


# ─── Intelligence ─────────────────────────────────────────────────────────────


@main.group(invoke_without_command=True)
@click.pass_context
def reason(ctx: click.Context) -> None:
    """Run reasoning engines and explain conclusions."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@reason.command("run")
@click.option("--engine",
              type=click.Choice(["deductive", "abductive", "rete", "forward-chain",
                                  "datalog", "sparql", "graph"]),
              default="rete", show_default=True)
@click.option("--rules", default=None, type=click.Path(exists=True),
              help="Custom rules file (YAML/Datalog/SPARQL).")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def reason_run(cli_ctx: CLIContext, engine: str, rules: Optional[str],
               local_json: bool) -> None:
    """Execute a reasoning engine against the knowledge graph.

    \b
    Example:
      semantica reason run --engine rete --rules business-rules.yaml
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .reasoning import Reasoner
            r = Reasoner(engine=engine, config=cli_ctx.config.to_dict())
            if cli_ctx.quiet or cli_ctx.json_output:
                result = r.run(rules_file=rules)
            else:
                with console.status(
                    f"[{_DIM}]Running {engine} reasoning engine…[/{_DIM}]",
                    spinner="dots",
                ):
                    result = r.run(rules_file=rules)
        except ImportError as exc:
            raise click.ClickException(f"Reasoning module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@reason.command("explain")
@click.argument("conclusion")
@click.option("--depth", default=3, type=int, show_default=True)
@click.option("--format", "fmt", type=click.Choice(["text", "markdown", "json"]),
              default="text", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def reason_explain(cli_ctx: CLIContext, conclusion: str, depth: int,
                   fmt: str, local_json: bool) -> None:
    """Explain how a conclusion was reached.

    \b
    Example:
      semantica reason explain "Alice is-manager-of Engineering" --format markdown
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .reasoning import ExplanationGenerator
            gen = ExplanationGenerator(config=cli_ctx.config.to_dict())
            if cli_ctx.quiet or cli_ctx.json_output:
                expl = gen.explain(conclusion, depth=depth)
            else:
                with console.status(
                    f"[{_DIM}]Generating explanation (depth={depth})…[/{_DIM}]",
                    spinner="dots",
                ):
                    expl = gen.explain(conclusion, depth=depth)
        except ImportError as exc:
            raise click.ClickException(f"Reasoning module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(expl if isinstance(expl, dict) else {"explanation": str(expl)})
        else:
            _pprint(cli_ctx, expl)

    _run_with_error_handling(_action)


@reason.command("query")
@click.argument("query_str")
@click.option("--with-inference", is_flag=True, default=False,
              help="Include inferred facts in results.")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def reason_query(cli_ctx: CLIContext, query_str: str, with_inference: bool,
                 local_json: bool) -> None:
    """SPARQL or Datalog query with inference.

    \b
    Example:
      semantica reason query "SELECT ?x WHERE { ?x :hasRole :Manager }" --with-inference
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .reasoning import SPARQLReasoner
            r = SPARQLReasoner(config=cli_ctx.config.to_dict())
            result = r.query(query_str, with_inference=with_inference)
        except ImportError as exc:
            raise click.ClickException(f"Reasoning module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, (dict, list)) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@reason.command("list")
@click.pass_obj
def reason_list(cli_ctx: CLIContext) -> None:
    """List available reasoning engines."""
    cli_ctx = _require_ctx(cli_ctx)
    _builtin: List[str] = ["deductive", "abductive", "rete", "forward-chain", "datalog", "sparql", "graph"]
    try:
        import semantica.reasoning as _reasoning_mod
        _fn = getattr(_reasoning_mod, "get_available_engines", None)
        engines: List[str] = list(_fn()) if callable(_fn) else _builtin
    except ImportError:
        engines = _builtin
    if cli_ctx.json_output:
        _jecho({"engines": engines})
    else:
        table = Table(title="[bold]Available Reasoning Engines[/bold]",
                      box=_TABLE_BOX, show_edge=False, padding=(0, 1))
        table.add_column("Engine", style=_KEY)
        for e in engines:
            table.add_row(e)
        console.print(table)


@main.group(invoke_without_command=True)
@click.pass_context
def decision(ctx: click.Context) -> None:
    """Record, trace, and analyze decisions with causal provenance."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@decision.command("record")
@click.option("--title", required=True, help="Decision title.")
@click.option("--tags", default=None, help="Comma-separated tags.")
@click.option("--valid-from", default=None, help="ISO 8601 validity start.")
@click.option("--valid-until", default=None, help="ISO 8601 validity end.")
@click.option("--rationale", default=None, help="Decision rationale.")
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_record(cli_ctx: CLIContext, title: str, tags: Optional[str],
                    valid_from: Optional[str], valid_until: Optional[str],
                    rationale: Optional[str], local_dry: bool, local_json: bool) -> None:
    """Record a new decision.

    \b
    Example:
      semantica decision record --title "Approve vendor X" --tags "finance,vendor"
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "record decision", json_out=_is_json(cli_ctx, local_json),
                 title=title, tags=tag_list)
            return
        try:
            from .context.decision_methods import record_decision
            graph_store = _get_graph_store(cli_ctx)
            cross_ctx: Dict[str, Any] = {"tags": tag_list}
            if valid_from:
                cross_ctx["valid_from"] = valid_from
            if valid_until:
                cross_ctx["valid_until"] = valid_until
            # Map CLI flags to API: title→scenario, rationale→reasoning,
            # first tag (if any)→category, outcome and confidence use defaults.
            category = tag_list[0] if tag_list else "general"
            result = record_decision(
                graph_store,
                category=category,
                scenario=title,
                reasoning=rationale or "",
                outcome="recorded",
                confidence=1.0,
                cross_system_context=cross_ctx,
            )
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho({"id": str(result)})
        else:
            _ok(cli_ctx, f"Decision recorded: {result}")

    _run_with_error_handling(_action)


@decision.command("list")
@click.option("--limit", default=20, type=int, show_default=True)
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_list(cli_ctx: CLIContext, limit: int, fmt: str, local_json: bool) -> None:
    """List recent decisions."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .context.decision_query import DecisionQuery
            dq = DecisionQuery(_get_graph_store(cli_ctx))
            results_raw = dq.find_by_time_range(
                __import__("datetime").datetime.min,
                __import__("datetime").datetime.now(),
                limit=limit,
            )
            results = [
                {"id": d.decision_id, "title": d.scenario, "tags": [d.category]}
                for d in (results_raw or [])
            ]
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(results)
        else:
            table = Table(title="[bold]Recent Decisions[/bold]",
                          box=_TABLE_BOX, show_edge=False, padding=(0, 1))
            table.add_column("ID", style=_KEY, no_wrap=True)
            table.add_column("Title")
            table.add_column("Category")
            for d in results:
                table.add_row(str(d.get("id", "")), str(d.get("title", "")),
                              str(d.get("tags", [""])[0]))
            console.print(table)

    _run_with_error_handling(_action)


@decision.command("query")
@click.option("--filter", "filter_str", default=None, help="e.g. tag:finance")
@click.option("--since", default=None, help="ISO 8601 date.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_query(cli_ctx: CLIContext, filter_str: Optional[str],
                   since: Optional[str], fmt: str, local_json: bool) -> None:
    """Filter decisions by tag, entity, or date."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .context.decision_query import DecisionQuery
            import datetime as _dt
            dq = DecisionQuery(_get_graph_store(cli_ctx))
            since_dt = _dt.datetime.fromisoformat(since) if since else _dt.datetime.min
            raw = dq.find_by_time_range(since_dt, _dt.datetime.now(), limit=500)
            results: List[Dict[str, Any]] = [
                {"id": d.decision_id, "category": d.category, "scenario": d.scenario,
                 "outcome": d.outcome, "confidence": d.confidence}
                for d in (raw or [])
                if filter_str is None
                or filter_str.lstrip("tag:").lower() in d.category.lower()
            ]
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(results)
        else:
            _pprint(cli_ctx, results)

    _run_with_error_handling(_action)


@decision.command("trace")
@click.argument("decision_id")
@click.option("--format", "fmt", type=click.Choice(["text", "mermaid", "json"]),
              default="text", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_trace(cli_ctx: CLIContext, decision_id: str, fmt: str, local_json: bool) -> None:
    """Show the full causal decision chain for a decision ID.

    \b
    Example:
      semantica decision trace dec_abc123 --format mermaid
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .context.decision_methods import get_causal_chain
            chain_raw = get_causal_chain(_get_graph_store(cli_ctx), decision_id)
            chain: Any = [
                {"id": d.decision_id, "scenario": d.scenario, "outcome": d.outcome}
                for d in chain_raw
            ]
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(chain if isinstance(chain, (dict, list)) else {"chain": str(chain)})
        else:
            console.print(chain)

    _run_with_error_handling(_action)


@decision.command("similar")
@click.argument("decision_id")
@click.option("--top-k", default=3, type=int, show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_similar(cli_ctx: CLIContext, decision_id: str, top_k: int, local_json: bool) -> None:
    """Find precedent decisions similar to the given ID."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .context.decision_methods import find_precedents
            raw = find_precedents(_get_graph_store(cli_ctx), decision_id, limit=top_k)
            results: List[Dict[str, Any]] = [
                {"id": d.decision_id, "scenario": d.scenario, "category": d.category,
                 "confidence": d.confidence}
                for d in (raw or [])
            ]
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(results)
        else:
            _pprint(cli_ctx, results)

    _run_with_error_handling(_action)


@decision.command("impact")
@click.argument("decision_id")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_impact(cli_ctx: CLIContext, decision_id: str, local_json: bool) -> None:
    """Analyze downstream impact of a decision."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .context.decision_methods import analyze_decision_impact
            result = analyze_decision_impact(_get_graph_store(cli_ctx), decision_id)
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result)
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@decision.command("check")
@click.argument("decision_id")
@click.option("--rules", default=None, type=click.Path(exists=True),
              help="Policy rules YAML file.")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def decision_check(cli_ctx: CLIContext, decision_id: str, rules: Optional[str],
                   local_json: bool) -> None:
    """Validate a decision against policy rules."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .context.decision_methods import check_decision_compliance
            # The API expects a policy_id string; derive it from the rules file stem
            # if provided, otherwise use the decision ID itself as the policy key.
            policy_id = Path(rules).stem if rules else decision_id
            result = check_decision_compliance(
                _get_graph_store(cli_ctx), decision_id, policy_id
            )
        except ImportError as exc:
            raise click.ClickException(f"Context module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result)
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def temporal(ctx: click.Context) -> None:
    """Point-in-time queries and Allen interval algebra."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@temporal.command("snapshot")
@click.option("--at", "at_time", required=True, help="ISO 8601 datetime.")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]),
              default="json", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def temporal_snapshot(cli_ctx: CLIContext, at_time: str, fmt: str, local_json: bool) -> None:
    """Graph state at a specific point in time.

    \b
    Example:
      semantica temporal snapshot --at "2026-01-15T09:00:00Z"
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import TemporalGraphQuery
            tgq = TemporalGraphQuery(config=cli_ctx.config.to_dict())
            result = tgq.snapshot(at=at_time)
        except ImportError as exc:
            raise click.ClickException(f"KG temporal module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(result if isinstance(result, dict) else {"snapshot": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@temporal.command("query")
@click.argument("query_str")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def temporal_query(cli_ctx: CLIContext, query_str: str, local_json: bool) -> None:
    """Temporal-aware graph query."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import TemporalGraphQuery
            tgq = TemporalGraphQuery(config=cli_ctx.config.to_dict())
            result = tgq.query(query_str)
        except ImportError as exc:
            raise click.ClickException(f"KG temporal module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, (dict, list)) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@temporal.command("history")
@click.argument("entity_id")
@click.option("--since", default=None, help="ISO 8601 date filter.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def temporal_history(cli_ctx: CLIContext, entity_id: str, since: Optional[str],
                     fmt: str, local_json: bool) -> None:
    """Change history for an entity.

    \b
    Example:
      semantica temporal history entity_alice --since 2025-01-01 --format table
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import TemporalVersionManager
            tvm = TemporalVersionManager(config=cli_ctx.config.to_dict())
            result = tvm.history(entity_id, since=since)
        except ImportError as exc:
            raise click.ClickException(f"KG temporal module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(result if isinstance(result, list) else [])
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@temporal.command("distance")
@click.option("--event1", required=True)
@click.option("--event2", required=True)
@click.option("--history", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def temporal_distance(cli_ctx: CLIContext, event1: str, event2: str,
                      history: bool, local_json: bool) -> None:
    """Temporal distance between two events."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import TemporalGraphQuery
            tgq = TemporalGraphQuery(config=cli_ctx.config.to_dict())
            result = tgq.distance(event1, event2, include_history=history)
        except ImportError as exc:
            raise click.ClickException(f"KG temporal module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"distance": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@temporal.command("allen")
@click.option("--interval1", required=True)
@click.option("--interval2", required=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def temporal_allen(cli_ctx: CLIContext, interval1: str, interval2: str,
                   local_json: bool) -> None:
    """Allen interval algebra relation between two intervals."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .reasoning import TemporalReasoningEngine
            engine = TemporalReasoningEngine(config=cli_ctx.config.to_dict())
            result = engine.allen_relation(interval1, interval2)
        except ImportError as exc:
            raise click.ClickException(f"Reasoning module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho({"interval1": interval1, "interval2": interval2, "relation": str(result)})
        else:
            console.print(f"{interval1} ── {result} ──► {interval2}")

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def provenance(ctx: click.Context) -> None:
    """Lineage, audit logs, and W3C PROV-O export."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@provenance.command("lineage")
@click.argument("entity_id")
@click.option("--depth", default=3, type=int, show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def provenance_lineage(cli_ctx: CLIContext, entity_id: str, depth: int, local_json: bool) -> None:
    """Show data lineage for an entity.

    \b
    Example:
      semantica provenance lineage entity_alice --depth 3
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            result = pm.lineage(entity_id, depth=depth)
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"lineage": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@provenance.command("audit")
@click.option("--since", default=None, help="ISO 8601 date.")
@click.option("--format", "fmt", type=click.Choice(["json", "csv", "table"]),
              default="table", show_default=True)
@click.option("--output", default=None, type=click.Path())
@click.option("--json", "local_json", is_flag=True, default=False)
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def provenance_audit(cli_ctx: CLIContext, since: Optional[str], fmt: str,
                     output: Optional[str], local_json: bool,
                     local_dry: bool) -> None:
    """Export the audit log.

    \b
    Example:
      semantica provenance audit --since 2026-01-01 --format csv --output audit.csv
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "export audit log", since=since, format=fmt, output=output)
            return
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            result = pm.audit_log(since=since, format=fmt)
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        text = json.dumps(result, default=str) if _is_json(cli_ctx, local_json) else str(result)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        else:
            click.echo(text)

    _run_with_error_handling(_action)


@provenance.command("export")
@click.option("--format", "fmt", type=click.Choice(["turtle", "ntriples", "jsonld"]),
              default="turtle", show_default=True)
@click.option("--base-uri", "base_uri", default=None,
              help="Namespace URI entities/agents/activities are minted under "
                   "(default: ProvenanceManager.DEFAULT_BASE_URI).")
@click.option("--output", default=None, type=click.Path())
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def provenance_export(cli_ctx: CLIContext, fmt: str, base_uri: Optional[str],
                      output: Optional[str], local_dry: bool) -> None:
    """Export provenance as W3C PROV-O RDF.

    \b
    Example:
      semantica provenance export --format turtle --output prov.ttl
      semantica provenance export --base-uri https://example.org/kg# --output prov.ttl
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "export provenance", format=fmt, base_uri=base_uri, output=output)
            return
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            data = pm.export_prov(format=fmt, base_uri=base_uri)
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        if output:
            Path(output).write_text(data, encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        else:
            click.echo(data)

    _run_with_error_handling(_action)


@provenance.command("check")
@click.option("--strict", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def provenance_check(cli_ctx: CLIContext, strict: bool, local_json: bool) -> None:
    """Validate provenance integrity."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            result = pm.check(strict=strict)
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        is_valid = not isinstance(result, dict) or result.get("valid", True)
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"valid": bool(result)})
        elif is_valid:
            _ok(cli_ctx, f"Provenance check: {result}")
        else:
            _warn(cli_ctx, f"Provenance check: {result}")
        if strict and not is_valid:
            raise click.ClickException(
                f"Provenance integrity check failed: {result.get('errors')} error(s)"
            )

    _run_with_error_handling(_action)


@provenance.command("invalidate")
@click.argument("entity_id")
@click.option("--by", "agent_id", required=True, help="Agent responsible for the invalidation.")
@click.option("--reason", default=None, help="Human-readable reason for the invalidation.")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def provenance_invalidate(cli_ctx: CLIContext, entity_id: str, agent_id: str,
                          reason: Optional[str], local_json: bool,
                          local_dry: bool) -> None:
    """Mark a tracked entity as invalidated (tombstone, not a hard delete).

    \b
    Example:
      semantica provenance invalidate entity_alice --by reviewer_jane --reason "Source retracted"
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "invalidate provenance entity", entity_id=entity_id, by=agent_id, reason=reason)
            return
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            result = pm.invalidate(entity_id, agent_id=agent_id, reason=reason)
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result.to_dict())
        else:
            _ok(cli_ctx, f"Invalidated {entity_id} (by {agent_id})")

    _run_with_error_handling(_action)


@provenance.command("verify-chain")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def provenance_verify_chain(cli_ctx: CLIContext, local_json: bool) -> None:
    """Verify the hash chain across all provenance entries.

    Detects wholesale row deletion: per-row checksums alone only prove a
    surviving row wasn't edited in place, not that no row is missing.

    \b
    Example:
      semantica provenance verify-chain
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            result = pm.verify_chain()
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result)
        elif result.get("valid"):
            _ok(cli_ctx, f"Chain verified: {result.get('total_entries')} entries, no breaks")
        else:
            _warn(cli_ctx, f"Chain verification failed: {len(result.get('broken_links', []))} broken link(s)")
            for link in result.get("broken_links", []):
                click.echo(f"  {link}")

    _run_with_error_handling(_action)


@provenance.command("descendants")
@click.argument("entity_id")
@click.option("--depth", default=None, type=int, show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def provenance_descendants(cli_ctx: CLIContext, entity_id: str, depth: Optional[int],
                           local_json: bool) -> None:
    """Show downstream descendants (reverse lineage) for an entity.

    The counterpart to `provenance lineage`, which only traces upstream
    ancestors. Answers "entity X was wrong — what downstream facts used it?"

    \b
    Example:
      semantica provenance descendants entity_alice --depth 3
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .provenance import ProvenanceManager
            pm = ProvenanceManager(config=cli_ctx.config.to_dict())
            if depth is not None:
                entries = [e.to_dict() for e in pm.trace_descendants(entity_id, max_depth=depth)]
                result = {"entity_id": entity_id, "depth": depth, "entries": entries}
            else:
                result = pm.get_descendants(entity_id) or {"entity_id": entity_id, "entries": []}
        except ImportError as exc:
            raise click.ClickException(f"Provenance module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result)
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def validate(ctx: click.Context) -> None:
    """SHACL shapes and conflict detection."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@validate.command("shacl")
@click.option("--shapes", default=None, type=click.Path(exists=True),
              help="SHACL shapes file (auto-generated if omitted).")
@click.option("--strictness", type=click.Choice(["strict", "moderate", "lenient"]),
              default="moderate", show_default=True)
@click.option("--report", default=None, type=click.Path(),
              help="Write validation report to file.")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def validate_shacl(cli_ctx: CLIContext, shapes: Optional[str], strictness: str,
                   report: Optional[str], local_json: bool) -> None:
    """Validate data against SHACL constraint shapes.

    \b
    Example:
      semantica validate shacl --strictness strict --report report.json
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import OntologyValidator
            v = OntologyValidator(config=cli_ctx.config.to_dict())
            result = v.validate_shacl(shapes_file=shapes, strictness=strictness)
        except ImportError as exc:
            raise click.ClickException(f"Ontology/validation module not available: {exc}") from exc
        payload = result if isinstance(result, dict) else {"valid": bool(result)}
        if report:
            Path(report).write_text(json.dumps(payload, default=str), encoding="utf-8")
            _ok(cli_ctx, f"Wrote {report}")
        if _is_json(cli_ctx, local_json):
            _jecho(payload)
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@validate.command("conflicts")
@click.option("--strategy",
              type=click.Choice(["value", "property", "type", "relationship",
                                  "temporal", "logical", "entity", "all"]),
              default="all", show_default=True)
@click.option("--format", "fmt", type=click.Choice(["json", "table"]),
              default="json", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def validate_conflicts(cli_ctx: CLIContext, strategy: str, fmt: str, local_json: bool) -> None:
    """Detect value, type, temporal, and logical conflicts.

    \b
    Example:
      semantica validate conflicts --format json | jq '.conflicts | length'
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .conflicts import detect_conflicts
            result = detect_conflicts(strategy=strategy, config=cli_ctx.config.to_dict())
        except ImportError as exc:
            raise click.ClickException(f"Conflicts module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(result if isinstance(result, dict) else {"conflicts": result})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@validate.command("integrity")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def validate_integrity(cli_ctx: CLIContext, local_json: bool) -> None:
    """Run graph integrity checks."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .kg import GraphValidator
            v = GraphValidator(config=cli_ctx.config.to_dict())
            result = v.integrity_check()
        except ImportError as exc:
            raise click.ClickException(f"KG module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"valid": bool(result)})
        else:
            _ok(cli_ctx, f"Integrity check: {result}")

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def ontology(ctx: click.Context) -> None:
    """OWL generation, import, SHACL, and SKOS vocabularies."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@ontology.command("generate")
@click.option("--domain", default=None, help="Domain hint (e.g. healthcare).")
@click.option("--output", default=None, type=click.Path())
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_generate(cli_ctx: CLIContext, domain: Optional[str], output: Optional[str],
                      local_dry: bool, local_json: bool) -> None:
    """Auto-generate OWL ontology from graph data.

    \b
    Example:
      semantica ontology generate --domain healthcare --output healthcare.ttl
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "generate ontology", json_out=_is_json(cli_ctx, local_json),
                 domain=domain, output=output)
            return
        try:
            from .ontology import OntologyGenerator
            gen = OntologyGenerator(config=cli_ctx.config.to_dict())
            result = gen.generate(domain=domain)
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        if output:
            Path(output).write_text(str(result), encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        elif _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"ontology": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@ontology.command("import")
@click.argument("source")
@click.option("--format", "fmt",
              type=click.Choice(["turtle", "rdfxml", "jsonld", "ntriples"]),
              default=None)
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_import(cli_ctx: CLIContext, source: str, fmt: Optional[str],
                    local_dry: bool, local_json: bool) -> None:
    """Import OWL/RDF/Turtle/JSON-LD from a file or URL.

    \b
    Example:
      semantica ontology import schema.org.ttl --format turtle
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "import ontology", json_out=_is_json(cli_ctx, local_json),
                 source=source, format=fmt)
            return
        try:
            from .ontology import ingest_ontology
            result = ingest_ontology(source, format=fmt, config=cli_ctx.config.to_dict())
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"status": "ok"})
        else:
            _ok(cli_ctx, f"Imported: {source}")

    _run_with_error_handling(_action)


@ontology.command("validate")
@click.option("--shapes", default=None, type=click.Path(exists=True))
@click.option("--strictness", type=click.Choice(["strict", "moderate", "lenient"]),
              default="moderate", show_default=True)
@click.option("--report", default=None, type=click.Path())
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_validate(cli_ctx: CLIContext, shapes: Optional[str], strictness: str,
                      report: Optional[str], local_json: bool) -> None:
    """Run SHACL validation on the ontology."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import validate_ontology
            result = validate_ontology(shapes_file=shapes, strictness=strictness,
                                       config=cli_ctx.config.to_dict())
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        payload = result if isinstance(result, dict) else {"valid": bool(result)}
        if report:
            Path(report).write_text(json.dumps(payload, default=str), encoding="utf-8")
            _ok(cli_ctx, f"Wrote {report}")
        if _is_json(cli_ctx, local_json):
            _jecho(payload)
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@ontology.command("shacl")
@click.option("--output", default=None, type=click.Path())
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_shacl(cli_ctx: CLIContext, output: Optional[str], local_json: bool) -> None:
    """Generate SHACL shapes from the ontology."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import SHACLGenerator
            gen = SHACLGenerator(config=cli_ctx.config.to_dict())
            result = gen.generate()
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        text = str(result)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        elif _is_json(cli_ctx, local_json):
            _jecho({"shacl": text})
        else:
            click.echo(text)

    _run_with_error_handling(_action)


@ontology.group("skos", invoke_without_command=True)
@click.pass_context
def ontology_skos(ctx: click.Context) -> None:
    """Manage SKOS concept schemes and vocabulary hierarchies."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@ontology_skos.command("search")
@click.argument("term")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def skos_search(cli_ctx: CLIContext, term: str, local_json: bool) -> None:
    """Search SKOS concept schemes for a term."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import OntologyGenerator
            gen = OntologyGenerator(config=cli_ctx.config.to_dict())
            result = gen.skos_search(term)
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, (dict, list)) else {"results": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@ontology_skos.command("hierarchy")
@click.argument("uri")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def skos_hierarchy(cli_ctx: CLIContext, uri: str, local_json: bool) -> None:
    """Show concept hierarchy tree for a URI."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import OntologyGenerator
            gen = OntologyGenerator(config=cli_ctx.config.to_dict())
            result = gen.skos_hierarchy(uri)
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"hierarchy": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@ontology.command("align")
@click.option("--source", required=True, type=click.Path(exists=True))
@click.option("--target", required=True, type=click.Path(exists=True))
@click.option("--strategy", type=click.Choice(["semantic", "structural", "lexical"]),
              default="semantic", show_default=True)
@click.option("--output", default=None, type=click.Path())
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_align(cli_ctx: CLIContext, source: str, target: str, strategy: str,
                   output: Optional[str], local_json: bool) -> None:
    """Align two ontologies.

    \b
    Example:
      semantica ontology align --source mine.ttl --target schema.ttl --strategy semantic
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import OntologyGenerator
            gen = OntologyGenerator(config=cli_ctx.config.to_dict())
            result = gen.align(source, target, strategy=strategy)
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        if output:
            Path(output).write_text(json.dumps(result, default=str), encoding="utf-8")
            _ok(cli_ctx, f"Wrote {output}")
        elif _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"alignments": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@ontology.command("health")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]),
              default="table", show_default=True)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_health(cli_ctx: CLIContext, fmt: str, local_json: bool) -> None:
    """Show ontology health dashboard."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .ontology import OntologyValidator
            v = OntologyValidator(config=cli_ctx.config.to_dict())
            result = v.health()
        except ImportError as exc:
            raise click.ClickException(f"Ontology module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(result if isinstance(result, dict) else {"health": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@ontology.command("version")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def ontology_version(cli_ctx: CLIContext, local_json: bool) -> None:
    """Manage ontology versions."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .change_management import OntologyVersionManager
            v = OntologyVersionManager(**cli_ctx.config.to_dict())
            result = v.current()
        except ImportError as exc:
            raise click.ClickException(f"Change management module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"version": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


# ─── Data Out ─────────────────────────────────────────────────────────────────


_EXPORT_FORMATS = [
    "turtle", "jsonld", "ntriples", "rdfxml",
    "parquet", "arrow", "csv", "json", "yaml",
    "graphml", "owl", "shacl", "arangodb", "distance-enriched",
]


@main.command()
@click.option("--format", "fmt", type=click.Choice(_EXPORT_FORMATS),
              default="json", show_default=True)
@click.option("--output", default=None, type=click.Path(),
              help="Write to file (stdout if omitted).")
@click.option("--with-provenance", is_flag=True, default=False,
              help="Embed W3C lineage metadata.")
@click.option("--filter", "filter_str", default=None, help="e.g. type:Person")
@click.option("--compress", is_flag=True, default=False, help="Gzip the output.")
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def export(
    cli_ctx: CLIContext, fmt: str, output: Optional[str], with_provenance: bool,
    filter_str: Optional[str], compress: bool, local_dry: bool, local_json: bool,
) -> None:
    """Export the graph in 14 supported formats.

    \b
    Examples:
      semantica export --format turtle --output graph.ttl
      semantica export --format parquet --with-provenance --output graph.parquet
      semantica export --format csv --filter "type:Person" --output persons.csv
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "export", json_out=_is_json(cli_ctx, local_json),
                 format=fmt, output=output)
            return
        try:
            import tempfile

            from .export import get_export_method
            from .graph_store import get_nodes, get_relationships
            from .graph_store.config import graph_store_config

            fn = get_export_method("export", "knowledge_graph")
            if fn is None:
                raise click.ClickException("Export method not available: export/knowledge_graph")

            graph_db = dict(cli_ctx.config.to_dict().get("graph_db", {}))
            backend = cli_ctx.store_backend or graph_db.pop("backend", None)
            previous_graph_config = graph_store_config.get_all()
            graph_store_config.update(graph_db)
            if backend:
                graph_store_config.set("default_backend", backend)
            try:
                entities = get_nodes(limit=sys.maxsize)
                relationships = get_relationships(limit=sys.maxsize)
            finally:
                graph_store_config.update(previous_graph_config)

            knowledge_graph = {
                "entities": entities,
                "relationships": relationships,
                "nodes": entities,
                "edges": relationships,
            }

            kwargs: Dict[str, Any] = {"format": fmt}
            if with_provenance:
                kwargs["include_provenance"] = True
            if filter_str:
                kwargs["filter"] = filter_str

            temp_output = None
            target_output = output
            if target_output is None or compress:
                temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
                temp_output = temp_handle.name
                temp_handle.close()
                target_output = temp_output

            fn(knowledge_graph, target_output, **kwargs)
        except ImportError as exc:
            raise click.ClickException(f"Export module not available: {exc}") from exc
        if compress:
            import gzip

            assert temp_output is not None
            compressed = gzip.compress(Path(temp_output).read_bytes())
            if output:
                Path(output).write_bytes(compressed)
                _ok(cli_ctx, f"Wrote compressed {output}")
            else:
                sys.stdout.buffer.write(compressed)
        elif output:
            _ok(cli_ctx, f"Wrote {output}")
        else:
            assert temp_output is not None
            try:
                click.echo(Path(temp_output).read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                sys.stdout.buffer.write(Path(temp_output).read_bytes())

        if temp_output:
            Path(temp_output).unlink(missing_ok=True)

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def visualize(ctx: click.Context) -> None:
    """Render interactive graph and ontology diagrams."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _viz_command(name: str, fn_name: str, title: str) -> None:
    @visualize.command(name)
    @click.option("--layout",
                  type=click.Choice(["forceatlas2", "spring", "circular", "hierarchical", "spectral"]),
                  default="spring", show_default=True)
    @click.option("--format", "fmt", type=click.Choice(["html", "svg", "png", "pdf"]),
                  default="html", show_default=True)
    @click.option("--filter", "filter_str", default=None)
    @click.option("--color-scheme",
                  type=click.Choice(["default", "dark", "categorical", "entity-type"]),
                  default="default", show_default=True)
    @click.option("--output", default=None, type=click.Path())
    @click.pass_obj
    def _cmd(cli_ctx: CLIContext, layout: str, fmt: str, filter_str: Optional[str],
             color_scheme: str, output: Optional[str]) -> None:
        cli_ctx = _require_ctx(cli_ctx)

        def _action() -> None:
            try:
                from .visualization import get_visualization_method
                viz_fn = get_visualization_method(fn_name)
                result = viz_fn(
                    layout=layout, format=fmt, filter=filter_str,
                    color_scheme=color_scheme, config=cli_ctx.config.to_dict(),
                )
            except ImportError as exc:
                raise click.ClickException(f"Visualization module not available: {exc}") from exc
            if output:
                if isinstance(result, bytes):
                    Path(output).write_bytes(result)
                else:
                    Path(output).write_text(str(result), encoding="utf-8")
                _ok(cli_ctx, f"Wrote {output}")
            else:
                # No --output: emit to stdout so the caller can redirect or pipe.
                if isinstance(result, bytes):
                    sys.stdout.buffer.write(result)
                else:
                    click.echo(result)

        _run_with_error_handling(_action)

    _cmd.__doc__ = title


_viz_command("kg", "visualize_kg", "Render an interactive knowledge graph.")
_viz_command("ontology", "visualize_ontology", "Render an OWL class and property diagram.")
_viz_command("embeddings", "visualize_embeddings", "Render the embedding space (UMAP/t-SNE).")
_viz_command("temporal", "visualize_temporal", "Render a timeline and temporal event chart.")
_viz_command("analytics", "visualize_analytics", "Render centrality and community analytics.")


# ─── Orchestration ────────────────────────────────────────────────────────────


_PIPELINE_TEMPLATES = [
    "ingest-extract-kg", "rag", "ontology-build", "decision-track", "full",
]


@pipeline.command("init")
@click.option("--template", type=click.Choice(_PIPELINE_TEMPLATES),
              default="ingest-extract-kg", show_default=True)
@click.option("--output", default="pipeline.yaml", show_default=True, type=click.Path())
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def pipeline_init(cli_ctx: CLIContext, template: str, output: str, local_dry: bool) -> None:
    """Scaffold a new pipeline config from a template.

    \b
    Example:
      semantica pipeline init --template ingest-extract-kg --output pipeline.yaml
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "init pipeline", template=template, output=output)
            return
        try:
            from .pipeline import PipelineTemplateManager
            mgr = PipelineTemplateManager()
            content = mgr.scaffold(template)
        except ImportError:
            content = f"# Pipeline template: {template}\nsteps: []\n"
        Path(output).write_text(content, encoding="utf-8")
        _ok(cli_ctx, f"Created {output} from template '{template}'")

    _run_with_error_handling(_action)


@pipeline.command("validate")
@click.argument("pipeline_file", type=click.Path(exists=True))
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def pipeline_validate(cli_ctx: CLIContext, pipeline_file: str, local_json: bool) -> None:
    """Validate a pipeline config without running it."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .pipeline import PipelineValidator
            v = PipelineValidator()
            result = v.validate(pipeline_file)
        except ImportError as exc:
            raise click.ClickException(f"Pipeline module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"valid": bool(result)})
        else:
            _ok(cli_ctx, f"Pipeline config valid: {pipeline_file}")

    _run_with_error_handling(_action)


@pipeline.command("run")
@click.argument("pipeline_file", type=click.Path(exists=True))
@click.option("--parallel", default=4, type=int, show_default=True,
              help="Worker concurrency.")
@click.option("--incremental", is_flag=True, default=False,
              help="Delta mode — skip unchanged records.")
@click.option("--watch", is_flag=True, default=False,
              help="Re-run on source changes.")
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def pipeline_run(cli_ctx: CLIContext, pipeline_file: str, parallel: int,
                 incremental: bool, watch: bool, local_dry: bool) -> None:
    """Execute a pipeline.

    \b
    Example:
      semantica pipeline run pipeline.yaml --parallel 8
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "run pipeline", file=pipeline_file, parallel=parallel)
            return
        try:
            from .pipeline import ExecutionEngine
            engine = ExecutionEngine(config=cli_ctx.config.to_dict())
            result = engine.run(
                pipeline_file, workers=parallel,
                incremental=incremental, watch=watch,
            )
        except ImportError as exc:
            raise click.ClickException(f"Pipeline module not available: {exc}") from exc
        _ok(cli_ctx, f"Pipeline completed: {result}")

    _run_with_error_handling(_action)


@pipeline.command("status")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def pipeline_status(cli_ctx: CLIContext, local_json: bool) -> None:
    """Show status of a running pipeline."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .pipeline import ExecutionEngine
            engine = ExecutionEngine(config=cli_ctx.config.to_dict())
            result = engine.status()
        except ImportError as exc:
            raise click.ClickException(f"Pipeline module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, dict) else {"status": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


@pipeline.command("stop")
@click.pass_obj
def pipeline_stop(cli_ctx: CLIContext) -> None:
    """Stop a running pipeline."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .pipeline import ExecutionEngine
            engine = ExecutionEngine(config=cli_ctx.config.to_dict())
            engine.stop()
        except ImportError as exc:
            raise click.ClickException(f"Pipeline module not available: {exc}") from exc
        _ok(cli_ctx, "Pipeline stopped.")

    _run_with_error_handling(_action)


@main.group(invoke_without_command=True)
@click.pass_context
def store(ctx: click.Context) -> None:
    """Manage graph, vector, and triplet store backends."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@store.command("list")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def store_list(cli_ctx: CLIContext, local_json: bool) -> None:
    """List all configured backends."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        cfg = cli_ctx.config.to_dict()
        store_cfg = cfg.get("store", {})
        backends = {k: v for k, v in store_cfg.items() if isinstance(v, dict)}
        if _is_json(cli_ctx, local_json):
            _jecho(backends)
        else:
            table = Table(title="[bold]Configured Backends[/bold]",
                          box=_TABLE_BOX, show_edge=False, padding=(0, 1))
            table.add_column("Type", style=_KEY, no_wrap=True)
            table.add_column("Backend")
            table.add_column("URI/Host")
            for store_type, info in backends.items():
                table.add_row(
                    store_type,
                    str(info.get("backend", "-")),
                    str(info.get("uri", info.get("host", "-"))),
                )
            console.print(table)

    _run_with_error_handling(_action)


@store.command("connect")
@click.option("--backend", required=True, help="Backend name.")
@click.option("--uri", default=None, help="Connection URI.")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def store_connect(cli_ctx: CLIContext, backend: str, uri: Optional[str], local_json: bool) -> None:
    """Test a backend connection."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .graph_store import get_graph_store_method
            store_cls = get_graph_store_method(backend)
            cfg = dict(cli_ctx.config.to_dict().get("graph_db", {}))
            if uri:
                cfg["uri"] = uri
            # Attempt instantiation as the minimal connectivity probe; backends
            # that require a live connection will fail here if unreachable.
            store_instance = store_cls(config=cfg)
            for probe in ("health_check", "ping", "connect"):
                fn = getattr(store_instance, probe, None)
                if callable(fn):
                    fn()
                    break
            result = {"backend": backend, "connected": True}
        except ImportError as exc:
            result = {"backend": backend, "connected": False,
                      "error": f"Module not available: {exc}"}
        except Exception as exc:
            result = {"backend": backend, "connected": False, "error": str(exc)}
        if _is_json(cli_ctx, local_json):
            _jecho(result)
        else:
            status = "[green]connected[/green]" if result.get("connected") else "[red]failed[/red]"
            console.print(f"Backend {backend}: {status}")
            if not result.get("connected") and "error" in result:
                console.print(f"  Error: {result['error']}")

    _run_with_error_handling(_action)


@store.command("stats")
@click.option("--backend", required=True)
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def store_stats(cli_ctx: CLIContext, backend: str, fmt: str, local_json: bool) -> None:
    """Show backend statistics."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from .graph_store import run_analytics
            stats = run_analytics(backend=backend, config=cli_ctx.config.to_dict())
        except ImportError as exc:
            raise click.ClickException(f"Graph store module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json) or fmt == "json":
            _jecho(stats if isinstance(stats, dict) else {"stats": str(stats)})
        else:
            console.print(stats)

    _run_with_error_handling(_action)


@store.command("migrate")
@click.option("--from", "from_backend", required=True)
@click.option("--to", "to_backend", required=True)
@click.option("--namespace", default=None)
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def store_migrate(cli_ctx: CLIContext, from_backend: str, to_backend: str,
                  namespace: Optional[str], local_dry: bool) -> None:
    """Migrate data between backends.

    \b
    Example:
      semantica store migrate --from faiss --to qdrant --namespace production --dry-run
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "migrate", from_backend=from_backend, to_backend=to_backend)
            return
        raise click.ClickException(
            f"Direct backend migration ({from_backend} → {to_backend}) is not yet supported "
            "by the vector store layer. To migrate, export your data first:\n"
            "  semantica export --format parquet --output dump.parquet\n"
            f"  semantica embed index dump.parquet --store {to_backend}"
            + (f" --namespace {namespace}" if namespace else "")
        )

    _run_with_error_handling(_action)


@store.command("flush")
@click.option("--namespace", default=None)
@click.option("--confirm", is_flag=True, default=False,
              help="Required safety confirmation.")
@click.pass_obj
def store_flush(cli_ctx: CLIContext, namespace: Optional[str], confirm: bool) -> None:
    """Clear a namespace (requires --confirm)."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        if not confirm:
            raise click.UsageError("--confirm is required to flush a namespace.")
        try:
            from .vector_store import delete_vectors
            delete_vectors(namespace=namespace, config=cli_ctx.config.to_dict())
        except ImportError as exc:
            raise click.ClickException(f"Store module not available: {exc}") from exc
        _ok(cli_ctx, f"Flushed namespace: {namespace or 'default'}")

    _run_with_error_handling(_action)


# ─── Backup ───────────────────────────────────────────────────────────────────


@main.group(invoke_without_command=True)
@click.pass_context
def backup(ctx: click.Context) -> None:
    """Back up and restore all Semantica data."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _collect_backup_sources(
    cfg: Dict[str, Any],
    config_path: Optional[str],
    include: str,
    strip_config: bool,
) -> List[Tuple[str, Path]]:
    """Return (arcname, local_path) pairs for local files to include in a backup."""
    sources: List[Tuple[str, Path]] = []

    if not strip_config and include in ("config", "all"):
        candidates: List[str] = [c for c in [config_path, "semantica.yaml", "semantica.yml"] if c]
        for c in candidates:
            p = Path(c)
            if p.is_file():
                sources.append(("config/semantica.yaml", p))
                break

    if include in ("ontology", "all"):
        _ont: Any = cfg.get("ontology_path") or (cfg.get("ontology") or {}).get("path")
        ont_path: Optional[str] = str(_ont) if _ont else None
        if ont_path:
            p = Path(ont_path)
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        sources.append((f"ontology/{f.relative_to(p)}", f))
            elif p.is_file():
                sources.append((f"ontology/{p.name}", p))

    store_map = {"graph": "graph_db", "vector": "vector_store", "triplet": "triplet_store"}
    for store_type, cfg_key in store_map.items():
        if include not in (store_type, "all"):
            continue
        info = cfg.get(cfg_key)
        if not isinstance(info, dict):
            continue
        # Only file-addressable backends have a local path key
        _dp: Any = info.get("path") or info.get("data_path") or info.get("index_path")
        data_path: Optional[str] = str(_dp) if _dp else None
        if not data_path:
            continue
        p = Path(data_path)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    sources.append((f"{store_type}/{f.relative_to(p)}", f))
        elif p.is_file():
            sources.append((f"{store_type}/{p.name}", p))

    return sources


def _redact(uri: str) -> str:
    """Redact passwords/tokens from a connection URI."""
    import re
    return re.sub(r"(:)[^@/]+(@)", r"\1••••••••\2", uri)


@backup.command("info")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def backup_info(cli_ctx: CLIContext, local_json: bool) -> None:
    """Show backend type, data location, and backup method per store."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        cfg = cli_ctx.config.to_dict()
        # Config normalizes store sections into graph_db / vector_store / triplet_store
        section_keys = {
            "graph": "graph_db",
            "vector": "vector_store",
            "triplet": "triplet_store",
        }
        rows = []
        for store_type, cfg_key in section_keys.items():
            info = cfg.get(cfg_key)
            if not isinstance(info, dict) or not info:
                continue
            backend = info.get("backend", "unknown")
            uri_raw = info.get("uri", info.get("host", ""))
            uri = _redact(str(uri_raw)) if uri_raw else "(none)"
            cloud_backends = {"pinecone", "neptune", "snowflake"}
            if backend in cloud_backends:
                method = "use `semantica export` (cloud-managed)"
            elif backend in {"neo4j", "qdrant", "blazegraph", "falkordb"}:
                method = "native dump API"
            else:
                method = "file copy"
            rows.append({"store": store_type, "backend": backend, "uri": uri, "method": method})
        if _is_json(cli_ctx, local_json):
            _jecho(rows)
        else:
            table = Table(title="[bold]Backup Info[/bold] [dim](credentials redacted)[/dim]",
                          box=_TABLE_BOX, show_edge=False, padding=(0, 1))
            table.add_column("Store", style=_KEY, no_wrap=True)
            table.add_column("Backend")
            table.add_column("URI/Location")
            table.add_column("Method", style=_VAL)
            for r in rows:
                table.add_row(r["store"], r["backend"], r["uri"], r["method"])
            console.print(table)

    _run_with_error_handling(_action)


@backup.command("create")
@click.argument("destination", type=click.Path())
@click.option("--include",
              type=click.Choice(["graph", "vector", "triplet", "config", "ontology", "all"]),
              default="all", show_default=True)
@click.option("--compress", is_flag=True, default=False)
@click.option("--encrypt", is_flag=True, default=False,
              help="AES-256 encrypt (passphrase prompted interactively).")
@click.option("--keyfile", default=None, type=click.Path(),
              help="Read passphrase from file (must not be world-readable).")
@click.option("--strip-config", is_flag=True, default=False,
              help="Exclude semantica.yaml to avoid storing credentials at rest.")
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--quiet", "local_quiet", is_flag=True, default=False)
@click.pass_obj
def backup_create(
    cli_ctx: CLIContext, destination: str, include: str, compress: bool,
    encrypt: bool, keyfile: Optional[str], strip_config: bool,
    local_dry: bool, local_quiet: bool,
) -> None:
    """Create a full backup archive.

    \b
    Example:
      semantica backup create ./backups/semantica-2026-05-25.tar.gz --compress --encrypt
    """
    cli_ctx = _require_ctx(cli_ctx)
    quiet = cli_ctx.quiet or local_quiet

    def _action() -> None:
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "backup create", destination=destination, include=include)
            return

        if keyfile:
            kp = Path(keyfile)
            if not kp.exists():
                raise click.ClickException(f"Keyfile not found: {keyfile}")
            stat_result = kp.stat()
            # Reject group-readable (0o040) or world-readable (0o004) keyfiles.
            if stat_result.st_mode & 0o044:
                raise click.ClickException(
                    f"Keyfile {keyfile} is readable by group or others. "
                    f"Run: chmod 600 {keyfile}"
                )
            # On POSIX, also verify ownership to catch sudo/setuid misuse.
            if hasattr(os, "getuid") and stat_result.st_uid != os.getuid():  # type: ignore[attr-defined]
                raise click.ClickException(
                    f"Keyfile {keyfile} is not owned by the current user."
                )
            passphrase = kp.read_text(encoding="utf-8").strip()
            if not passphrase:
                raise click.ClickException(f"Keyfile {keyfile} is empty; cannot derive encryption key.")
        elif encrypt:
            passphrase = click.prompt("Backup passphrase", hide_input=True,
                                      confirmation_prompt=True)
        else:
            passphrase = None

        cfg = cli_ctx.config.to_dict()
        if not strip_config and not encrypt and passphrase is None:
            if not quiet:
                console.print(
                    f"[{_WARN_STY}] ⚠[/{_WARN_STY}] backup includes semantica.yaml which may contain "
                    "credentials. Use --encrypt or --strip-config to suppress this warning."
                )
            click.confirm("Continue without encryption?", abort=True)

        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)

        import tarfile, tempfile, shutil
        sources = _collect_backup_sources(cfg, cli_ctx.config_path, include, strip_config)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest: Dict[str, Any] = {
                "include": include,
                "version": str(__version__),
                "files": [arcname for arcname, _ in sources],
            }
            (tmp_path / "backup_manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
            # Build the tar archive in a temp file; we'll compress/encrypt on top.
            raw_tar = Path(tmp) / "semantica-backup.tar"
            with tarfile.open(str(raw_tar), "w") as tar:
                tar.add(str(tmp_path / "backup_manifest.json"),
                        arcname="semantica-backup/backup_manifest.json")
                for arcname, local_path in sources:
                    tar.add(str(local_path), arcname=f"semantica-backup/{arcname}")

            # Compress (gzip) if requested.
            if compress:
                import gzip
                compressed = Path(tmp) / "semantica-backup.tar.gz"
                with open(str(raw_tar), "rb") as f_in, gzip.open(str(compressed), "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                raw_tar.unlink()
                payload_path = compressed
            else:
                payload_path = raw_tar

            # Encrypt with AES-256-GCM if --encrypt was requested.
            if encrypt and passphrase:
                try:
                    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                    from cryptography.hazmat.primitives import hashes
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                except ImportError as exc:
                    raise click.ClickException(
                        "Encryption requires the 'cryptography' package: "
                        "pip install cryptography"
                    ) from exc
                salt = os.urandom(32)
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(), length=32,
                    salt=salt, iterations=480_000,
                )
                key = kdf.derive(passphrase.encode())
                nonce = os.urandom(12)
                plaintext = payload_path.read_bytes()
                ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
                # Wire format: magic(4) + salt(32) + nonce(12) + ciphertext
                enc_path = Path(tmp) / "semantica-backup.enc"
                enc_path.write_bytes(b"SEM1" + salt + nonce + ciphertext)
                payload_path = enc_path

            shutil.copy2(str(payload_path), str(dest))

        try:
            os.chmod(str(dest), 0o600)
        except OSError:
            pass

        if not quiet:
            enc_note = " (AES-256-GCM encrypted)" if encrypt and passphrase else ""
            _ok(cli_ctx, f"Backup created: {destination}{enc_note}")

    _run_with_error_handling(_action)


@backup.command("sync")
@click.argument("destination", type=click.Path())
@click.option("--include",
              type=click.Choice(["graph", "vector", "triplet", "config", "ontology", "all"]),
              default="all", show_default=True)
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.option("--quiet", "local_quiet", is_flag=True, default=False)
@click.pass_obj
def backup_sync(cli_ctx: CLIContext, destination: str, include: str,
                local_dry: bool, local_quiet: bool) -> None:
    """Incremental folder sync (idempotent, copies only changed files).

    \b
    Example:
      semantica backup sync /mnt/external/semantica-backup
    """
    cli_ctx = _require_ctx(cli_ctx)
    quiet = cli_ctx.quiet or local_quiet

    def _action() -> None:
        import shutil
        dest = Path(destination)
        cfg = cli_ctx.config.to_dict()
        sources = _collect_backup_sources(cfg, cli_ctx.config_path, include, strip_config=False)
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "sync backup", destination=str(dest), include=include,
                 files=[a for a, _ in sources])
            return
        dest.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(dest), 0o700)
        except OSError:
            pass
        copied = 0
        for arcname, src_path in sources:
            dst_file = dest / arcname
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            # Incremental: skip if destination is up-to-date
            if dst_file.exists() and dst_file.stat().st_mtime >= src_path.stat().st_mtime:
                continue
            shutil.copy2(str(src_path), str(dst_file))
            copied += 1
        if not quiet:
            _ok(cli_ctx, f"Synced {copied} file(s) to {destination}")

    _run_with_error_handling(_action)


@backup.command("restore")
@click.argument("source", type=click.Path(exists=True))
@click.option("--dry-run", "local_dry", is_flag=True, default=False)
@click.pass_obj
def backup_restore(cli_ctx: CLIContext, source: str, local_dry: bool) -> None:
    """Restore from a backup archive or folder.

    \b
    Example:
      semantica backup restore ./backups/semantica-2026-05-25.tar.gz --dry-run
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        import shutil, tarfile as _tf
        src = Path(source)
        if _is_dry(cli_ctx, local_dry):
            _dry(cli_ctx, "restore", source=str(src))
            return

        # Determine payload: decrypt .enc first, then extract archive or copy dir.
        work_path = src
        if src.suffix == ".enc":
            passphrase = click.prompt("Backup passphrase", hide_input=True)
            try:
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError as exc:
                raise click.ClickException(
                    "Decryption requires the 'cryptography' package: pip install cryptography"
                ) from exc
            raw = src.read_bytes()
            if not raw.startswith(b"SEM1") or len(raw) < 4 + 32 + 12:
                raise click.ClickException("Unrecognised or corrupted backup file.")
            salt, nonce, ciphertext = raw[4:36], raw[36:48], raw[48:]
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
            key = kdf.derive(passphrase.encode())
            try:
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
            except Exception as exc:
                raise click.ClickException("Decryption failed — wrong passphrase?") from exc
            import tempfile
            tmp_enc = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
            tmp_enc.write(plaintext)
            tmp_enc.close()
            work_path = Path(tmp_enc.name)

        try:
            if _tf.is_tarfile(str(work_path)):
                restore_root = Path.cwd().resolve()
                with _tf.open(str(work_path), "r:*") as tar:
                    # Dry-run listing was already handled above; extract now
                    for member in tar.getmembers():
                        # Strip the leading "semantica-backup/" prefix
                        member.name = member.name.replace("semantica-backup/", "", 1)
                        if not member.name:
                            continue

                        # Reject members whose resolved path escapes the
                        # restore root (path traversal / absolute paths),
                        # regardless of the "semantica-backup/" prefix.
                        member_path = (restore_root / member.name).resolve()
                        try:
                            member_path.relative_to(restore_root)
                        except ValueError:
                            raise click.ClickException(
                                f"Refusing to restore '{member.name}': "
                                "path escapes the restore directory."
                            )

                        # Reject symlink/hardlink members whose target
                        # escapes the restore root. Checked two ways:
                        # lexically (linkname itself, so an absolute path or
                        # a literal ".." segment is rejected outright, with
                        # no dependence on what else does or doesn't already
                        # exist on disk) and by resolution (catches any
                        # remaining traversal the lexical check misses).
                        if member.issym() or member.islnk():
                            linkname = member.linkname or ""
                            linkname_parts = PurePosixPath(
                                linkname.replace("\\", "/")
                            ).parts
                            if (
                                not linkname
                                or os.path.isabs(linkname)
                                or PureWindowsPath(linkname).is_absolute()
                                or ".." in linkname_parts
                            ):
                                raise click.ClickException(
                                    f"Refusing to restore '{member.name}': "
                                    "link target is absolute or traverses "
                                    "out of the archive."
                                )
                            link_target = (
                                member_path.parent / linkname
                            ).resolve()
                            try:
                                link_target.relative_to(restore_root)
                            except ValueError:
                                raise click.ClickException(
                                    f"Refusing to restore '{member.name}': "
                                    "link target escapes the restore directory."
                                )

                        extract_kwargs: Dict[str, Any] = {"path": str(restore_root)}
                        if hasattr(_tf, "data_filter"):
                            # Python >=3.12: also reject device files, and
                            # further harden the traversal/ownership checks.
                            extract_kwargs["filter"] = "data"
                        tar.extract(member, **extract_kwargs)
                        console.print(f"  restored: {member.name}")
            elif src.is_dir():
                restore_root = Path.cwd()
                for f in src.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(src)
                        dst = restore_root / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(f), str(dst))
                        console.print(f"  restored: {rel}")
            else:
                raise click.ClickException(f"Cannot restore from {source}: not a tar archive or directory.")
        finally:
            if src.suffix == ".enc":
                work_path.unlink(missing_ok=True)

        _ok(cli_ctx, f"Restore complete from {source}")

    _run_with_error_handling(_action)


@backup.command("schedule")
@click.option("--dest", required=True, type=click.Path(), help="Backup destination path.")
@click.option("--freq", type=click.Choice(["daily", "hourly", "weekly"]),
              default="daily", show_default=True)
@click.option("--encrypt", is_flag=True, default=False)
@click.pass_obj
def backup_schedule(cli_ctx: CLIContext, dest: str, freq: str, encrypt: bool) -> None:
    """Print a ready-to-paste cron snippet.

    \b
    Example:
      semantica backup schedule --dest /mnt/external/semantica --freq daily --encrypt
    """
    cli_ctx = _require_ctx(cli_ctx)
    schedules = {"daily": "0 2 * * *", "hourly": "0 * * * *", "weekly": "0 2 * * 0"}
    cron_time = schedules[freq]
    enc_flag = " --encrypt" if encrypt else ""
    snippet = (
        f"{cron_time} semantica backup sync {dest}{enc_flag} --quiet"
    )
    if cli_ctx.json_output:
        _jecho({"cron": snippet})
    else:
        console.print(f"[bold]Suggested cron entry:[/bold]\n{snippet}")


# ─── Services ─────────────────────────────────────────────────────────────────


def _pid_file(name: str) -> Path:
    return Path.home() / ".semantica" / f"{name}.pid"


def _write_pid(name: str, pid: int) -> None:
    pf = _pid_file(name)
    pf.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(pf.parent), 0o700)
    except OSError:
        pass
    # Use low-level open to avoid following symlinks (TOCTOU / symlink-clobber
    # attacks). O_NOFOLLOW is POSIX-only; fall back gracefully on Windows.
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW  # type: ignore[attr-defined]
    try:
        fd = os.open(str(pf), flags, 0o600)
    except OSError as exc:
        raise click.ClickException(f"Failed to write PID file {pf}: {exc}") from exc
    try:
        os.write(fd, str(pid).encode())
    finally:
        os.close(fd)


def _read_pid(name: str) -> Optional[int]:
    pf = _pid_file(name)
    if pf.exists():
        try:
            return int(pf.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return None


def _kill_service(name: str) -> bool:
    pid = _read_pid(name)
    if pid is None:
        return False
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
        _pid_file(name).unlink(missing_ok=True)
        return True
    except ProcessLookupError:
        _pid_file(name).unlink(missing_ok=True)
        return False


def _service_status(name: str) -> str:
    pid = _read_pid(name)
    if pid is None:
        return "stopped"
    try:
        os.kill(pid, 0)
        return f"running (pid {pid})"
    except ProcessLookupError:
        _pid_file(name).unlink(missing_ok=True)
        return "stopped"


@main.group(invoke_without_command=True)
@click.pass_context
def server(ctx: click.Context) -> None:
    """Start/stop/status the REST API server (port 8000)."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@server.command("start")
@click.option("--port", default=8000, type=int, show_default=True)
@click.option("--workers", default=1, type=int, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Enable hot reload.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.pass_obj
def server_start(cli_ctx: CLIContext, port: int, workers: int, reload: bool, host: str) -> None:
    """Start the REST API server.

    \b
    Example:
      semantica server start --port 8000 --workers 4
    """
    cli_ctx = _require_ctx(cli_ctx)

    _LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
    if host not in _LOOPBACK_HOSTS:
        console.print(
            f"[{_WARN_STY}] ⚠[/{_WARN_STY}] Binding to [cyan]{host}[/cyan] exposes "
            "the server to the network. Set SEMANTICA_API_KEY before doing this "
            "in any reachable environment — without it, protected routes refuse "
            "all requests (503), and with SEMANTICA_ALLOW_ANONYMOUS=true they are "
            "wide open."
        )

    def _action() -> None:
        import subprocess as sp
        cmd = [
            sys.executable, "-m", "uvicorn", "semantica.server:app",
            "--host", host, "--port", str(port),
            "--workers", str(workers),
        ]
        if reload:
            cmd.append("--reload")
        proc = sp.Popen(cmd)
        _write_pid("server", proc.pid)
        _ok(cli_ctx, f"Server started on {host}:{port} (pid {proc.pid})")

    _run_with_error_handling(_action)


@server.command("stop")
@click.pass_obj
def server_stop(cli_ctx: CLIContext) -> None:
    """Stop the REST API server."""
    cli_ctx = _require_ctx(cli_ctx)
    if _kill_service("server"):
        _ok(cli_ctx, "Server stopped.")
    else:
        console.print(f"[{_WARN_STY}] ⚠[/{_WARN_STY}] Server is not running.")


@server.command("status")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def server_status(cli_ctx: CLIContext, local_json: bool) -> None:
    """Show REST API server status."""
    cli_ctx = _require_ctx(cli_ctx)
    status = _service_status("server")
    if _is_json(cli_ctx, local_json):
        _jecho({"service": "server", "status": status})
    else:
        console.print(f"Server: {status}")


@main.group(invoke_without_command=True)
@click.pass_context
def explorer(ctx: click.Context) -> None:
    """Start/stop/status the Knowledge Explorer UI (port 5173)."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@explorer.command("start")
@click.option("--port", default=5173, type=int, show_default=True)
@click.option("--api-url", default="http://localhost:8000", show_default=True)
@click.option("--graph", default=None, type=click.Path(exists=True),
              help="Optional graph JSON file to preload.")
@click.pass_obj
def explorer_start(cli_ctx: CLIContext, port: int, api_url: str,
                   graph: Optional[str]) -> None:
    """Start the Knowledge Explorer dashboard.

    \b
    Example:
      semantica explorer start --port 5173 --api-url http://localhost:8000
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        import subprocess as sp
        cmd = [sys.executable, "-m", "semantica.explorer", "--port", str(port)]
        if graph:
            cmd += ["--graph", graph]
        env = os.environ.copy()
        env["SEMANTICA_API_URL"] = api_url
        proc = sp.Popen(cmd, env=env)
        _write_pid("explorer", proc.pid)
        _ok(cli_ctx, f"Explorer started on port {port} using API {api_url} (pid {proc.pid})")

    _run_with_error_handling(_action)


@explorer.command("stop")
@click.pass_obj
def explorer_stop(cli_ctx: CLIContext) -> None:
    """Stop the Knowledge Explorer."""
    cli_ctx = _require_ctx(cli_ctx)
    if _kill_service("explorer"):
        _ok(cli_ctx, "Explorer stopped.")
    else:
        console.print(f"[{_WARN_STY}] ⚠[/{_WARN_STY}] Explorer is not running.")


@explorer.command("status")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def explorer_status(cli_ctx: CLIContext, local_json: bool) -> None:
    """Show Explorer status."""
    cli_ctx = _require_ctx(cli_ctx)
    status = _service_status("explorer")
    if _is_json(cli_ctx, local_json):
        _jecho({"service": "explorer", "status": status})
    else:
        console.print(f"Explorer: {status}")


@explorer.command("open")
@click.option("--port", default=5173, type=int, show_default=True)
@click.pass_obj
def explorer_open(cli_ctx: CLIContext, port: int) -> None:
    """Open the Explorer in the default browser."""
    cli_ctx = _require_ctx(cli_ctx)
    import webbrowser
    url = f"http://localhost:{port}"
    webbrowser.open(url)
    _ok(cli_ctx, f"Opened {url}")


@main.group(invoke_without_command=True)
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Start/stop the MCP server and call tools directly."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@mcp.command("start")
@click.option("--transport", type=click.Choice(["stdio", "http"]),
              default="stdio", show_default=True)
@click.option("--port", default=3000, type=int, show_default=True)
@click.pass_obj
def mcp_start(cli_ctx: CLIContext, transport: str, port: int) -> None:
    """Start the MCP server.

    \b
    Example:
      semantica mcp start --transport http --port 3000
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        import subprocess as sp
        cmd = [sys.executable, "-m", "mcp.server"]
        if transport == "http":
            cmd += ["--port", str(port)]
        proc = sp.Popen(cmd)
        _write_pid("mcp", proc.pid)
        _ok(cli_ctx, f"MCP server started (pid {proc.pid})")

    _run_with_error_handling(_action)


@mcp.command("stop")
@click.pass_obj
def mcp_stop(cli_ctx: CLIContext) -> None:
    """Stop the MCP server."""
    cli_ctx = _require_ctx(cli_ctx)
    if _kill_service("mcp"):
        _ok(cli_ctx, "MCP server stopped.")
    else:
        console.print(f"[{_WARN_STY}] ⚠[/{_WARN_STY}] MCP server is not running.")


@mcp.command("status")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def mcp_status(cli_ctx: CLIContext, local_json: bool) -> None:
    """Show MCP server status."""
    cli_ctx = _require_ctx(cli_ctx)
    status = _service_status("mcp")
    if _is_json(cli_ctx, local_json):
        _jecho({"service": "mcp", "status": status})
    else:
        console.print(f"MCP server: {status}")


@mcp.command("list-tools")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def mcp_list_tools(cli_ctx: CLIContext, local_json: bool) -> None:
    """List available MCP tools."""
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            from mcp.tools import __all__ as tools
        except ImportError:
            tools = [
                "extract_entities", "extract_relations", "build_graph",
                "query_graph", "get_graph_analytics", "run_reasoning",
                "record_decision", "get_decisions", "export_graph",
                "validate_shacl", "get_provenance", "embed_and_search",
            ]
        if _is_json(cli_ctx, local_json):
            _jecho({"tools": list(tools)})
        else:
            table = Table(title="[bold]MCP Tools[/bold]",
                          box=_TABLE_BOX, show_edge=False, padding=(0, 1))
            table.add_column("Tool", style=_KEY)
            for t in tools:
                table.add_row(str(t))
            console.print(table)

    _run_with_error_handling(_action)


@mcp.command("call")
@click.argument("tool_name")
@click.option("--args", default="{}", help="JSON arguments string.")
@click.option("--json", "local_json", is_flag=True, default=False)
@click.pass_obj
def mcp_call(cli_ctx: CLIContext, tool_name: str, args: str, local_json: bool) -> None:
    """Invoke an MCP tool directly from the terminal.

    \b
    Example:
      semantica mcp call extract_entities --args '{"text": "Alice works at Acme Corp."}'
    """
    cli_ctx = _require_ctx(cli_ctx)

    def _action() -> None:
        try:
            tool_args = json.loads(args)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Invalid JSON in --args: {exc}") from exc
        try:
            from mcp.session import MCPSession
            session = MCPSession(config=cli_ctx.config.to_dict())
            result = session.call_tool(tool_name, **tool_args)
        except ImportError as exc:
            raise click.ClickException(f"MCP module not available: {exc}") from exc
        if _is_json(cli_ctx, local_json):
            _jecho(result if isinstance(result, (dict, list)) else {"result": str(result)})
        else:
            _pprint(cli_ctx, result)

    _run_with_error_handling(_action)


# ─── Shell completion ─────────────────────────────────────────────────────────


@main.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish", "powershell"]))
def completion(shell: str) -> None:
    """Output shell completion script.

    \b
    Install:
      semantica completion bash        >> ~/.bashrc
      semantica completion zsh         >> ~/.zshrc
      semantica completion fish        > ~/.config/fish/completions/semantica.fish
      semantica completion powershell  >> $PROFILE
    """
    shell_map = {
        "bash": ("bash", "~/.bashrc"),
        "zsh": ("zsh", "~/.zshrc"),
        "fish": ("fish", "~/.config/fish/completions/semantica.fish"),
        "powershell": ("powershell", "$PROFILE"),
    }
    click_shell, install_path = shell_map[shell]
    env_var = "_SEMANTICA_COMPLETE"
    try:
        from click.shell_completion import ShellComplete
        complete = ShellComplete(main, ctx_args={}, prog_name="semantica",
                                 complete_var=env_var)
        src = complete.source()
        click.echo(src, nl=False)
    except Exception:
        click.echo(
            f"# Add this to {install_path}:\n"
            f'eval "$({env_var}={click_shell}_source semantica)"'
        )


# ─── Wire services subgroups into the existing 'services' group ───────────────


services.add_command(server, name="server")
services.add_command(explorer, name="explorer")
services.add_command(mcp, name="mcp")


if __name__ == "__main__":
    main()
