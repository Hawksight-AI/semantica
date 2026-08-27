"""
Progress Tracking Module

This module provides comprehensive progress tracking with visual indicators (emojis)
for file, module, and submodule processing across console, log files, and Jupyter notebooks.

Key Features:
    - Automatic module/submodule detection via introspection
    - Real-time progress updates with percentages and item counts
    - Dynamic update intervals based on dataset size for performance
    - Consolidated display for concurrent tasks to prevent scrolling
    - Console, Jupyter notebook, and log file support
    - Zero configuration required - works automatically
    - Final summary display

Main Classes:
    - ProgressTracker: Main tracking coordinator
    - ProgressDisplay: Abstract base class for displays
    - ConsoleProgressDisplay: Real-time console output
    - JupyterProgressDisplay: IPython/Jupyter notebook display
    - FileProgressDisplay: Log file progress tracking
    - track_progress: Decorator for automatic progress tracking

Example Usage:
    >>> from semantica.utils import track_progress
    >>> 
    >>> @track_progress
    >>> def process_file(file_path):
    ...     # Processing code - progress tracked automatically
    ...     pass

Author: Semantica Contributors
License: MIT
"""

import inspect
import os
import sys
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .logging import get_logger

DISABLE_JUPYTER_PROGRESS = os.getenv("SEMANTICA_DISABLE_JUPYTER_PROGRESS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _progress_disabled_from_env() -> bool:
    """Return whether progress output is disabled for this process."""
    return os.getenv("SEMANTICA_DISABLE_PROGRESS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _progress_forced_from_env() -> bool:
    """Return whether console progress is forced on despite a non-interactive stdout."""
    return os.getenv("SEMANTICA_FORCE_PROGRESS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _stdout_is_tty() -> bool:
    """Return whether stdout is an interactive terminal.

    Replacement streams do not always implement ``isatty`` and closed streams can
    raise, so both cases are treated as non-interactive.
    """
    try:
        return bool(sys.stdout is not None and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


# Try to import IPython for Jupyter support
try:
    from IPython import get_ipython
    from IPython.display import HTML, clear_output, display

    IPYTHON_AVAILABLE = True
except (ImportError, OSError):
    IPYTHON_AVAILABLE = False
    get_ipython = None
    HTML = None
    clear_output = None
    display = None


@dataclass
class ProgressItem:
    """Progress tracking item."""

    file: Optional[str] = None
    module: Optional[str] = None
    submodule: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    message: str = ""
    emoji: str = "⏳"
    metadata: Dict[str, Any] = field(default_factory=dict)
    progress_percentage: Optional[float] = None  # Progress percentage (0-100)
    total_items: Optional[int] = None  # Total items to process
    processed_items: Optional[int] = None  # Items processed so far
    estimated_remaining: Optional[float] = None  # Estimated remaining time in seconds
    pipeline_id: Optional[str] = None  # Pipeline ID this item belongs to
    pipeline_order: Optional[int] = None  # Order of this module in the pipeline


class ProgressDisplay(ABC):
    """Abstract base class for progress displays."""

    @abstractmethod
    def update(self, item: ProgressItem) -> None:
        """Update progress display."""
        pass

    @abstractmethod
    def show_summary(self, items: List[ProgressItem]) -> None:
        """Show final summary."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear display."""
        pass


class ConsoleProgressDisplay(ProgressDisplay):
    """Console progress display with real-time updates."""

    def __init__(self, use_emoji: bool = True, update_interval: float = 0.1):
        self.use_emoji = use_emoji
        
        # Check if stdout supports emojis (especially on Windows)
        if self.use_emoji:
            try:
                # Try encoding a test emoji with stdout's encoding
                encoding = getattr(sys.stdout, "encoding", None)
                if encoding:
                    "🧠".encode(encoding)
            except (UnicodeEncodeError, LookupError, AttributeError):
                self.use_emoji = False

        self.update_interval = update_interval
        self.last_update = 0.0
        self.current_lines: Dict[str, str] = {}
        self.lock = threading.Lock()

    def _should_update(self) -> bool:
        """Check if enough time has passed for update."""
        now = time.time()
        # If last_update is 0.0 or very old, always update (forced update)
        if self.last_update <= 0.0 or (now - self.last_update) >= self.update_interval:
            self.last_update = now
            return True
        return False

    def _get_emoji_for_module(self, module: str) -> str:
        """Get emoji for module type."""
        if not self.use_emoji:
            return ""

        emoji_map = {
            "ingest": "📥",
            "parse": "🔍",
            "kg": "🧠",
            "embeddings": "💾",
            "normalize": "🔧",
            "ontology": "📚",
            "semantic_extract": "🎯",
            "seed": "🌱",
            "split": "✂️",
            "triplet_store": "🗄️",
            "vector_store": "📊",
            "export": "💾",
            "reasoning": "🤔",
            "kg_qa": "✅",
            "visualization": "📈",
            "context": "🔗",
            "conflicts": "⚠️",
            "deduplication": "🔄",
            "pipeline": "⚙️",
        }

        # Check if module name contains any key
        module_lower = module.lower()
        for key, emoji in emoji_map.items():
            if key in module_lower:
                return emoji

        return "⏳"

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for status."""
        if not self.use_emoji:
            return ""

        status_map = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }
        return status_map.get(status, "⏳")

    def _get_action_message(self, module: Optional[str], message: str) -> str:
        """Get action message based on module."""
        # Map modules to actions
        action_map = {
            "ingest": "is ingesting",
            "parse": "is parsing",
            "kg": "is building",
            "embeddings": "is embedding",
            "normalize": "is normalizing",
            "ontology": "is generating",
            "semantic_extract": "is extracting",
            "seed": "is seeding",
            "split": "is splitting",
            "triplet_store": "is storing",
            "vector_store": "is indexing",
            "export": "is exporting",
            "reasoning": "is reasoning",
            "kg_qa": "is validating",
            "visualization": "is visualizing",
            "context": "is processing",
            "conflicts": "is resolving",
            "deduplication": "is deduplicating",
            "pipeline": "is executing",
            "core": "is processing",
        }

        action = action_map.get(module or "", "is processing")
        base_msg = f"Semantica {action}"

        if not message:
            return base_msg
            
        # If message already contains Semantica format, use it
        if "Semantica:" in message:
            return message.split("Semantica:")[-1].strip()
            
        # Otherwise combine them
        return f"{base_msg}: {message}"

    def _safe_write(self, text: str) -> None:
        """Safely write text to stdout handling encoding errors."""
        try:
            sys.stdout.write(text)
        except UnicodeEncodeError:
            # Fallback: encode with replacement and write decoded
            # Use ascii as safe fallback if encoding is unknown or caused error
            encoding = getattr(sys.stdout, "encoding", None) or "ascii"
            safe_text = text.encode(encoding, errors="replace").decode(encoding)
            sys.stdout.write(safe_text)

    def update(self, item: ProgressItem) -> None:
        """Update console progress display."""
        if not self._should_update():
            return

        with self.lock:
            # If item is part of a pipeline, get all pipeline items for display
            pipeline_items = []
            if item.pipeline_id:
                # Get tracker instance to access pipeline items
                # Use the singleton instance directly
                tracker = ProgressTracker.get_instance()
                pipeline_items = tracker.get_pipeline_items(item.pipeline_id)
            
            # If we have pipeline items, show all of them
            if pipeline_items:
                # Clear and show all pipeline items
                self._safe_write("\r" + " " * 150 + "\r")

                # Show header if first time
                if not hasattr(self, '_pipeline_header_shown'):
                    if self.use_emoji:
                        self._safe_write("🧠 Semantica - 📊 Current Progress\n")
                    else:
                        self._safe_write("Semantica - Current Progress\n")
                    self._safe_write("=" * 150 + "\n")
                    self._pipeline_header_shown = True

                # Display all pipeline items
                for pipeline_item in pipeline_items:
                    self._display_item_line(pipeline_item)
                    self._safe_write("\n")
                
                sys.stdout.flush()
            else:
                # Original single-item display
                self._display_item_line(item)
                sys.stdout.flush()
    
    def _display_item_line(self, item: ProgressItem) -> None:
        """Display a single progress item line."""
        # Create unique key for this item
        key = f"{item.module}:{item.submodule}"
        if item.file:
            key = f"{item.file}:{key}"

        # Build progress line
        parts = []

        # Status emoji
        if self.use_emoji:
            status_emoji = self._get_status_emoji(item.status)
            parts.append(status_emoji)

        # Create action message based on module
        action_msg = self._get_action_message(item.module, item.message)
        parts.append(action_msg)

        # Module and Submodule
        if self.use_emoji:
            module_emoji = self._get_emoji_for_module(item.module or "")
            parts.append(f"{module_emoji} {item.module or 'N/A'}")
        else:
            parts.append(f"{item.module or 'N/A'}")
        parts.append(f"{item.submodule or 'N/A'}")

        # Progress bar and percentage
        if item.progress_percentage is not None:
            pct = item.progress_percentage
            bar_width = 15
            filled = int(bar_width * pct / 100)
            bar = "█" * filled + "░" * (bar_width - filled)
            parts.append(f"|{bar}| {pct:.1f}%")
        else:
            parts.append("|" + "░" * 15 + "| 0.0%")

        # ETA
        if item.estimated_remaining is not None and item.estimated_remaining > 0:
            if item.estimated_remaining < 60:
                parts.append(f"ETA: {item.estimated_remaining:.1f}s")
            elif item.estimated_remaining < 3600:
                parts.append(f"ETA: {item.estimated_remaining/60:.1f}m")
            else:
                parts.append(f"ETA: {item.estimated_remaining/3600:.1f}h")
        else:
            parts.append("ETA: -")

        # Rate
        if item.start_time and item.processed_items is not None and item.processed_items > 0:
            elapsed = time.time() - item.start_time
            if elapsed > 0:
                rate = item.processed_items / elapsed
                parts.append(f"Rate: {rate:.1f}/s")
        else:
            parts.append("Rate: -")

        # Time
        if item.start_time:
            if item.end_time:
                elapsed = item.end_time - item.start_time
                parts.append(f"Time: {elapsed:.2f}s")
            else:
                elapsed = time.time() - item.start_time
                parts.append(f"Time: {elapsed:.2f}s")
        else:
            parts.append("Time: -")

        # Extraction counts (if available)
        if item.metadata.get('extraction_counts'):
            counts = item.metadata['extraction_counts']
            count_parts = []
            if 'tables' in counts:
                count_parts.append(f"{counts['tables']} tables")
            if 'images' in counts:
                count_parts.append(f"{counts['images']} images")
            if 'pages' in counts:
                count_parts.append(f"{counts['pages']} pages")
            if count_parts:
                extracted = ", ".join(count_parts)
                # Add Docling indicator if core dependency is docling
                if item.metadata.get('core_dependency') == 'docling':
                    parts.append(f"Extracted (Docling): {extracted}")
                else:
                    parts.append(f"Extracted: {extracted}")
        else:
            parts.append("Extracted: -")

        line = " ".join(parts)
        self.current_lines[key] = line
        self._safe_write(line)

    def show_summary(self, items: List[ProgressItem]) -> None:
        """Show final summary."""
        with self.lock:
            # Clear current display
            self._safe_write("\n" + "=" * 80 + "\n")

            # Summary header
            if self.use_emoji:
                self._safe_write("🧠 Semantica - 📊 Progress Summary\n")
            else:
                self._safe_write("Semantica - Progress Summary\n")
            self._safe_write("=" * 80 + "\n")

            # Group by module
            by_module: Dict[str, List[ProgressItem]] = {}
            for item in items:
                module = item.module or "unknown"
                if module not in by_module:
                    by_module[module] = []
                by_module[module].append(item)

            # Show summary by module
            total_time = 0.0
            completed = 0
            failed = 0

            for module, module_items in by_module.items():
                if self.use_emoji:
                    emoji = self._get_emoji_for_module(module)
                    self._safe_write(f"\n{emoji} {module.upper()}\n")
                else:
                    self._safe_write(f"\n{module.upper()}\n")
                self._safe_write("-" * 80 + "\n")

                for item in module_items:
                    status_emoji = self._get_status_emoji(item.status)
                    duration = ""
                    if item.start_time and item.end_time:
                        duration = f" ({item.end_time - item.start_time:.2f}s)"
                    elif item.start_time:
                        duration = f" (running...)"

                    line = f"  {status_emoji} {item.submodule or 'N/A'}"
                    if item.file:
                        line += f" - {Path(item.file).name}"
                    line += duration

                    self._safe_write(line + "\n")

                    if item.status == "completed":
                        completed += 1
                    elif item.status == "failed":
                        failed += 1

                    if item.start_time and item.end_time:
                        total_time += item.end_time - item.start_time

            # Final stats
            self._safe_write("\n" + "=" * 80 + "\n")
            if self.use_emoji:
                self._safe_write(
                    f"✅ Completed: {completed} | ❌ Failed: {failed} | ⏱️  Total Time: {total_time:.2f}s\n"
                )
            else:
                self._safe_write(
                    f"Completed: {completed} | Failed: {failed} | Total Time: {total_time:.2f}s\n"
                )
            self._safe_write("=" * 80 + "\n")
            sys.stdout.flush()

    def clear(self) -> None:
        """Clear console display."""
        with self.lock:
            self._safe_write("\r" + " " * 100 + "\r")
            sys.stdout.flush()
            self.current_lines.clear()


class JupyterProgressDisplay(ProgressDisplay):
    """Jupyter notebook progress display."""

    def __init__(self, use_emoji: bool = True):
        self.use_emoji = use_emoji
        self.display_handle = None
        self.items: List[ProgressItem] = []

    def _get_emoji_for_module(self, module: str) -> str:
        """Get emoji for module type."""
        if not self.use_emoji:
            return ""

        emoji_map = {
            "ingest": "📥",
            "parse": "🔍",
            "kg": "🧠",
            "embeddings": "💾",
            "normalize": "🔧",
            "ontology": "📚",
            "semantic_extract": "🎯",
            "seed": "🌱",
            "split": "✂️",
            "triplet_store": "🗄️",
            "vector_store": "📊",
            "export": "💾",
            "reasoning": "🤔",
            "kg_qa": "✅",
            "visualization": "📈",
            "context": "🔗",
            "conflicts": "⚠️",
            "deduplication": "🔄",
            "pipeline": "⚙️",
        }

        module_lower = module.lower()
        for key, emoji in emoji_map.items():
            if key in module_lower:
                return emoji
        return "⏳"

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for status."""
        if not self.use_emoji:
            return ""

        status_map = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }
        return status_map.get(status, "⏳")

    def _get_action_message(self, module: Optional[str], message: str) -> str:
        """Get action message based on module."""
        # Extract action from message if it contains "Semantica:"
        if message and "Semantica:" in message:
            # Use the message as-is if it already has Semantica format
            return (
                message.split("Semantica:")[-1].strip()
                if "Semantica:" in message
                else message
            )

        # Map modules to actions
        action_map = {
            "ingest": "is ingesting",
            "parse": "is parsing",
            "kg": "is building",
            "embeddings": "is embedding",
            "normalize": "is normalizing",
            "ontology": "is generating",
            "semantic_extract": "is extracting",
            "seed": "is seeding",
            "split": "is splitting",
            "triplet_store": "is storing",
            "vector_store": "is indexing",
            "export": "is exporting",
            "reasoning": "is reasoning",
            "kg_qa": "is validating",
            "visualization": "is visualizing",
            "context": "is processing",
            "conflicts": "is resolving",
            "deduplication": "is deduplicating",
            "pipeline": "is executing",
            "core": "is processing",
        }

        action = action_map.get(module or "", "is processing")
        return f"Semantica {action}"

    def _build_html(self, items: List[ProgressItem]) -> str:
        """Build HTML for display."""
        html_parts = ["<div style='font-family: monospace;'>"]

        # Current status
        html_parts.append("<h4>🧠 Semantica - 📊 Current Progress</h4>")
        html_parts.append("<table style='width: 100%; border-collapse: collapse;'>")
        
        # Check if any item is part of a pipeline
        pipeline_id = None
        pipeline_items = []
        for item in items:
            if item.pipeline_id:
                pipeline_id = item.pipeline_id
                break
        
        # If pipeline context exists, get all pipeline items
        if pipeline_id:
            tracker = ProgressTracker.get_instance()
            pipeline_items = tracker.get_pipeline_items(pipeline_id)
            # Also include expected modules that haven't started yet
            if pipeline_id in tracker.pipeline_contexts:
                expected_modules = tracker.pipeline_contexts[pipeline_id]
                module_order = tracker.pipeline_module_order.get(pipeline_id, {})
                # Create pending items for modules not yet started
                existing_modules = {item.module for item in pipeline_items if item.module}
                for module in expected_modules:
                    if module not in existing_modules:
                        pending_item = ProgressItem(
                            module=module,
                            submodule="Pending",
                            status="pending",
                            progress_percentage=0.0,
                            pipeline_id=pipeline_id,
                            pipeline_order=module_order.get(module, 999)
                        )
                        pipeline_items.append(pending_item)
                # Sort by pipeline order
                pipeline_items.sort(key=lambda x: (x.pipeline_order if x.pipeline_order is not None else 999, x.module or ""))
        
        # Use pipeline items if available, otherwise use regular items
        display_items = pipeline_items if pipeline_items else items[-10:]
        
        # Determine column header based on whether we have Docling items
        has_docling = any(item.metadata.get('core_dependency') == 'docling' for item in display_items)
        extracted_header = "Extracted (Docling)" if has_docling else "Extracted"
        
        html_parts.append(
            f"<tr><th>Status</th><th>Action</th><th>Module</th><th>Submodule</th><th>Progress</th><th>ETA</th><th>Rate</th><th>Time</th><th>{extracted_header}</th></tr>"
        )

        # Show pipeline items or last 10 items
        for item in display_items:
            status_emoji = self._get_status_emoji(item.status)
            module_emoji = self._get_emoji_for_module(item.module or "")
            action_msg = self._get_action_message(item.module, item.message)

            # Progress information
            progress_str = "-"
            if item.progress_percentage is not None:
                progress_str = f"{item.progress_percentage:.1f}%"
                if item.processed_items is not None and item.total_items is not None:
                    progress_str += f" ({item.processed_items}/{item.total_items})"
            
            # ETA information
            eta_str = "-"
            if item.estimated_remaining is not None and item.estimated_remaining > 0:
                if item.estimated_remaining < 60:
                    eta_str = f"{item.estimated_remaining:.1f}s"
                elif item.estimated_remaining < 3600:
                    eta_str = f"{item.estimated_remaining/60:.1f}m"
                else:
                    eta_str = f"{item.estimated_remaining/3600:.1f}h"
            
            # Processing rate
            rate_str = "-"
            if item.start_time and item.processed_items is not None and item.processed_items > 0:
                elapsed = time.time() - item.start_time
                if elapsed > 0:
                    rate = item.processed_items / elapsed
                    rate_str = f"{rate:.1f}/s"

            elapsed = ""
            if item.start_time:
                if item.end_time:
                    elapsed = f"{(item.end_time - item.start_time):.2f}s"
                else:
                    elapsed = f"{(time.time() - item.start_time):.2f}s"
            else:
                elapsed = "-"

            file_name = Path(item.file).name if item.file else "-"
            
            # Extraction counts
            extracted_str = "-"
            if item.metadata.get('extraction_counts'):
                counts = item.metadata['extraction_counts']
                count_parts = []
                if 'tables' in counts:
                    count_parts.append(f"{counts['tables']} tables")
                if 'images' in counts:
                    count_parts.append(f"{counts['images']} images")
                if 'pages' in counts:
                    count_parts.append(f"{counts['pages']} pages")
                if count_parts:
                    extracted_str = ", ".join(count_parts)
            elif item.status == "pending":
                extracted_str = "-"
            elif item.status == "running" and item.module == "parse":
                # Show progress message for running parse operations
                if "Docling" in item.message or item.metadata.get('core_dependency') == 'docling':
                    extracted_str = "Converting with Docling..."
                else:
                    extracted_str = "-"

            html_parts.append(
                f"<tr>"
                f"<td>{status_emoji}</td>"
                f"<td>{action_msg}</td>"
                f"<td>{module_emoji} {item.module or 'N/A'}</td>"
                f"<td>{item.submodule or 'N/A'}</td>"
                f"<td>{progress_str}</td>"
                f"<td>{eta_str}</td>"
                f"<td>{rate_str}</td>"
                f"<td>{elapsed}</td>"
                f"<td>{extracted_str}</td>"
                f"</tr>"
            )

        html_parts.append("</table>")
        html_parts.append("</div>")

        return "".join(html_parts)

    def update(self, item: ProgressItem) -> None:
        """Update Jupyter progress display (works in Jupyter and Google Colab)."""
        # Add or update item
        existing = None
        for i, existing_item in enumerate(self.items):
            if (
                existing_item.module == item.module
                and existing_item.submodule == item.submodule
                and existing_item.file == item.file
            ):
                existing = i
                break

        if existing is not None:
            self.items[existing] = item
        else:
            self.items.append(item)

        # If item is part of a pipeline, get all pipeline items for display
        display_items = self.items
        if item.pipeline_id:
            tracker = ProgressTracker.get_instance()
            pipeline_items = tracker.get_pipeline_items(item.pipeline_id)
            # Also include expected modules that haven't started yet
            if item.pipeline_id in tracker.pipeline_contexts:
                expected_modules = tracker.pipeline_contexts[item.pipeline_id]
                module_order = tracker.pipeline_module_order.get(item.pipeline_id, {})
                # Create pending items for modules not yet started
                existing_modules = {item.module for item in pipeline_items if item.module}
                for module in expected_modules:
                    if module not in existing_modules:
                        pending_item = ProgressItem(
                            module=module,
                            submodule="Pending",
                            status="pending",
                            progress_percentage=0.0,
                            pipeline_id=item.pipeline_id,
                            pipeline_order=module_order.get(module, 999)
                        )
                        pipeline_items.append(pending_item)
                # Sort by pipeline order
                pipeline_items.sort(key=lambda x: (x.pipeline_order if x.pipeline_order is not None else 999, x.module or ""))
                display_items = pipeline_items

        # Update display - always update immediately in Jupyter/Colab
        if IPYTHON_AVAILABLE:
            html = self._build_html(display_items)
            try:
                # Check if we're in Google Colab (Colab sometimes needs fresh displays)
                is_colab = False
                try:
                    import sys
                    import os
                    is_colab = ('google.colab' in sys.modules or 
                               os.environ.get("COLAB_GPU") is not None)
                except Exception:
                    pass
                
                if self.display_handle is None:
                    # First time - create display
                    self.display_handle = display(HTML(html), display_id=True)
                else:
                    # Try to update existing display
                    try:
                        # In Colab, sometimes update() doesn't work, so we recreate
                        if is_colab:
                            # Clear and recreate for Colab compatibility
                            try:
                                clear_output(wait=False)
                            except Exception:
                                pass
                            self.display_handle = display(HTML(html), display_id=True)
                        else:
                            # Regular Jupyter - try update first
                            self.display_handle.update(HTML(html))
                    except (AttributeError, TypeError, Exception):
                        # If update fails, create new display (works in both Jupyter and Colab)
                        try:
                            clear_output(wait=False)
                        except Exception:
                            pass
                        self.display_handle = display(HTML(html), display_id=True)
            except Exception:
                # Fallback: always create new display if update fails
                try:
                    clear_output(wait=False)
                except Exception:
                    pass
                self.display_handle = display(HTML(html), display_id=True)

    def show_summary(self, items: List[ProgressItem]) -> None:
        """Show final summary in Jupyter."""
        if not IPYTHON_AVAILABLE:
            return

        html_parts = ["<div style='font-family: monospace;'>"]
        html_parts.append("<h3>🧠 Semantica - 📊 Progress Summary</h3>")

        # Group by module
        by_module: Dict[str, List[ProgressItem]] = {}
        for item in items:
            module = item.module or "unknown"
            if module not in by_module:
                by_module[module] = []
            by_module[module].append(item)

        # Summary table
        html_parts.append(
            "<table style='width: 100%; border-collapse: collapse; border: 1px solid #ddd;'>"
        )
        html_parts.append(
            "<tr style='background-color: #f2f2f2;'>"
            "<th>Module</th><th>Submodule</th><th>File</th><th>Status</th><th>Time</th>"
            "</tr>"
        )

        completed = 0
        failed = 0
        total_time = 0.0

        for module, module_items in by_module.items():
            module_emoji = self._get_emoji_for_module(module)
            for item in module_items:
                status_emoji = self._get_status_emoji(item.status)
                duration = ""
                if item.start_time and item.end_time:
                    duration = f"{(item.end_time - item.start_time):.2f}s"
                    total_time += item.end_time - item.start_time
                elif item.start_time:
                    duration = "running..."

                file_name = Path(item.file).name if item.file else "-"

                html_parts.append(
                    f"<tr>"
                    f"<td>{module_emoji} {module}</td>"
                    f"<td>{item.submodule or 'N/A'}</td>"
                    f"<td>{file_name}</td>"
                    f"<td>{status_emoji}</td>"
                    f"<td>{duration}</td>"
                    f"</tr>"
                )

                if item.status == "completed":
                    completed += 1
                elif item.status == "failed":
                    failed += 1

        html_parts.append("</table>")

        # Stats
        html_parts.append(
            f"<p><strong>✅ Completed:</strong> {completed} | <strong>❌ Failed:</strong> {failed} | <strong>⏱️ Total Time:</strong> {total_time:.2f}s</p>"
        )
        html_parts.append("</div>")

        html = "".join(html_parts)
        display(HTML(html))

    def clear(self) -> None:
        """Clear Jupyter display."""
        if IPYTHON_AVAILABLE and self.display_handle:
            clear_output(wait=True)
            self.display_handle = None
        self.items.clear()


class FileProgressDisplay(ProgressDisplay):
    """File-based progress display (logs)."""

    def __init__(self, logger=None):
        self.logger = logger or get_logger("progress")
        self.items: List[ProgressItem] = []

    def update(self, item: ProgressItem) -> None:
        """Update file progress display."""
        # Add or update item
        existing = None
        for i, existing_item in enumerate(self.items):
            if (
                existing_item.module == item.module
                and existing_item.submodule == item.submodule
                and existing_item.file == item.file
            ):
                existing = i
                break

        if existing is not None:
            self.items[existing] = item
        else:
            self.items.append(item)

        # Log progress
        parts = [f"[{item.status.upper()}]"]
        if item.module:
            parts.append(f"Module: {item.module}")
        if item.submodule:
            parts.append(f"Submodule: {item.submodule}")
        if item.file:
            parts.append(f"File: {Path(item.file).name}")
        if item.message:
            parts.append(f"Message: {item.message}")

        self.logger.info(" | ".join(parts))

    def show_summary(self, items: List[ProgressItem]) -> None:
        """Show final summary in log file."""
        self.logger.info("=" * 80)
        self.logger.info("SEMANTICA - PROGRESS SUMMARY")
        self.logger.info("=" * 80)

        # Group by module
        by_module: Dict[str, List[ProgressItem]] = {}
        for item in items:
            module = item.module or "unknown"
            if module not in by_module:
                by_module[module] = []
            by_module[module].append(item)

        completed = 0
        failed = 0
        total_time = 0.0

        for module, module_items in by_module.items():
            self.logger.info(f"\n{module.upper()}:")
            for item in module_items:
                duration = ""
                if item.start_time and item.end_time:
                    duration = f" ({(item.end_time - item.start_time):.2f}s)"
                    total_time += item.end_time - item.start_time

                file_name = Path(item.file).name if item.file else "N/A"
                self.logger.info(
                    f"  [{item.status.upper()}] {item.submodule or 'N/A'} - {file_name}{duration}"
                )

                if item.status == "completed":
                    completed += 1
                elif item.status == "failed":
                    failed += 1

        self.logger.info("=" * 80)
        self.logger.info(
            f"Completed: {completed} | Failed: {failed} | Total Time: {total_time:.2f}s"
        )
        self.logger.info("=" * 80)

    def clear(self) -> None:
        """Clear file display (no-op for logs)."""
        pass


class ModuleDetector:
    """Utility for automatic module/submodule detection."""

    @staticmethod
    def detect_from_frame(frame) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect module and submodule from frame.

        Returns:
            Tuple of (module_name, submodule_name)
        """
        try:
            # Get the frame's module
            module_name = frame.f_globals.get("__name__", "")

            # Extract module name (e.g., 'semantica.ingest.file_ingestor' -> 'ingest')
            if "semantica." in module_name:
                parts = module_name.split(".")
                if len(parts) >= 2:
                    module_name = parts[1]  # Get 'ingest', 'parse', etc.
                else:
                    module_name = None
            else:
                module_name = None

            # Get class name from 'self' if available
            submodule_name = None
            if "self" in frame.f_locals:
                self_obj = frame.f_locals["self"]
                if hasattr(self_obj, "__class__"):
                    submodule_name = self_obj.__class__.__name__
            elif "cls" in frame.f_locals:
                cls_obj = frame.f_locals["cls"]
                if isinstance(cls_obj, type):
                    submodule_name = cls_obj.__name__

            # Fallback: try to get from frame code
            if not submodule_name:
                code = frame.f_code
                # Try to extract class name from qualified name
                if hasattr(code, "co_qualname"):
                    qualname = code.co_qualname
                    if "." in qualname:
                        submodule_name = qualname.split(".")[0]

            return module_name, submodule_name

        except Exception:
            return None, None

    @staticmethod
    def detect_from_call_stack(depth: int = 2) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect module and submodule from call stack.

        Args:
            depth: Stack depth to check (default: 2, meaning caller's caller)

        Returns:
            Tuple of (module_name, submodule_name)
        """
        try:
            frame = inspect.currentframe()
            if frame is None:
                return None, None

            # Go up the stack to find the actual caller
            for _ in range(depth):
                frame = frame.f_back
                if frame is None:
                    return None, None

            return ModuleDetector.detect_from_frame(frame)
        except Exception:
            return None, None


class ProgressTracker:
    """Main progress tracking coordinator."""

    _instance: Optional["ProgressTracker"] = None
    _lock = threading.Lock()

    def __init__(
        self, enabled: bool = True, use_emoji: bool = True, update_interval: float = 0.1
    ):
        """
        Initialize progress tracker.

        Args:
            enabled: Enable progress tracking (default: True)
            use_emoji: Use emoji indicators
            update_interval: Minimum time between updates (seconds)
        """
        self._progress_forced_disabled = _progress_disabled_from_env()
        self._enabled = False
        self.enabled = enabled
        self.use_emoji = use_emoji
        self.update_interval = update_interval

        # Detect environment - will be checked dynamically
        self.is_jupyter = self._detect_jupyter()
        self.disable_jupyter_progress = DISABLE_JUPYTER_PROGRESS

        # Create displays
        self.displays: List[ProgressDisplay] = []

        # Console output only suits an interactive stdout. When output is piped or
        # redirected (scripts, CI logs) the progress bars and their escape
        # sequences would otherwise drown the program's own output.
        console_ok = _stdout_is_tty() or self.is_jupyter or _progress_forced_from_env()

        # Always try Jupyter first if available, fallback to console
        if IPYTHON_AVAILABLE:
            # Try to detect Jupyter - if available, use it
            if self.is_jupyter and not self.disable_jupyter_progress:
                self.displays.append(JupyterProgressDisplay(use_emoji=use_emoji))
            # Also add console as fallback for immediate feedback
            if console_ok:
                self.displays.append(
                    ConsoleProgressDisplay(
                        use_emoji=use_emoji, update_interval=update_interval
                    )
                )
        elif console_ok:
            self.displays.append(
                ConsoleProgressDisplay(
                    use_emoji=use_emoji, update_interval=update_interval
                )
            )

        # Always add file display
        self.displays.append(FileProgressDisplay())

        # Track items
        self.items: List[ProgressItem] = []
        self.active_items: Dict[str, ProgressItem] = {}
        self.lock = threading.Lock()
        
        # Pipeline context tracking
        self.pipeline_contexts: Dict[str, List[str]] = {}  # pipeline_id -> list of module names
        self.pipeline_items: Dict[str, Dict[str, ProgressItem]] = {}  # pipeline_id -> {tracking_id: item}
        self.pipeline_module_order: Dict[str, Dict[str, int]] = {}  # pipeline_id -> {module: order}

    @property
    def enabled(self) -> bool:
        """Whether progress tracking is currently enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set progress enabled unless disabled by environment."""
        if value and (self._progress_forced_disabled or _progress_disabled_from_env()):
            self._progress_forced_disabled = True
            self._enabled = False
            return
        self._enabled = bool(value)

    def _detect_jupyter(self) -> bool:
        """Detect if running in Jupyter notebook or Google Colab."""
        if not IPYTHON_AVAILABLE:
            return False
        try:
            ipython = get_ipython()
            if ipython is None:
                return False
            
            # Method 1: Check for Google Colab
            # Colab has 'google.colab' in sys.modules or environment variables
            try:
                import sys
                import os
                if 'google.colab' in sys.modules:
                    return True
                # Check environment variables (Colab sets these)
                if os.environ.get("COLAB_GPU") is not None or os.environ.get("COLAB_JUPYTER_TRANSPORT") is not None:
                    return True
                # Check IPython config for Colab
                if hasattr(ipython, 'config') and hasattr(ipython.config, 'IPKernelApp'):
                    config_str = str(ipython.config.IPKernelApp)
                    if 'google.colab' in config_str or 'colab' in config_str.lower():
                        return True
            except Exception:
                pass
            
            # Method 2: Check for kernel attribute (Jupyter/Colab)
            if hasattr(ipython, "kernel"):
                return True
            
            # Method 3: Check for IPython shell class name
            if hasattr(ipython, "__class__"):
                class_name = ipython.__class__.__name__
                # Check for Jupyter, Colab, or ZMQ shell types
                if any(name in class_name for name in ["ZMQInteractiveShell", "Jupyter", "Colab", "InteractiveShell"]):
                    return True
            
            # Method 4: Check for IPython display capability
            if hasattr(ipython, "display_pub"):
                return True
            
            return False
        except Exception:
            return False

    @classmethod
    def get_instance(cls) -> "ProgressTracker":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_jupyter_display(self) -> None:
        """Add a Jupyter display dynamically when the environment becomes available."""
        if not self.enabled or not IPYTHON_AVAILABLE or self.is_jupyter:
            return

        is_jupyter = self._detect_jupyter()
        if not is_jupyter:
            return

        with self.lock:
            self.is_jupyter = True
            if (
                not self.disable_jupyter_progress
                and not any(isinstance(d, JupyterProgressDisplay) for d in self.displays)
            ):
                self.displays.insert(0, JupyterProgressDisplay(use_emoji=self.use_emoji))

    def _update_displays(
        self,
        displays: List[ProgressDisplay],
        item: ProgressItem,
        *,
        force_console: bool = False,
    ) -> None:
        """Update displays without holding the tracker lock."""
        for display in displays:
            if force_console and isinstance(display, ConsoleProgressDisplay):
                original_last_update = display.last_update
                display.last_update = 0.0
                display.update(item)
                display.last_update = original_last_update
            else:
                display.update(item)

    def register_pipeline_modules(
        self, pipeline_id: str, module_list: List[str], module_order: Optional[Dict[str, int]] = None
    ) -> None:
        """
        Register modules that belong to a pipeline.

        Args:
            pipeline_id: Unique pipeline identifier
            module_list: List of module names in the pipeline
            module_order: Optional dict mapping module names to their order in pipeline
        """
        if not self.enabled:
            return

        with self.lock:
            self.pipeline_contexts[pipeline_id] = module_list
            if module_order:
                self.pipeline_module_order[pipeline_id] = module_order
            else:
                # Auto-generate order if not provided
                self.pipeline_module_order[pipeline_id] = {
                    module: idx for idx, module in enumerate(module_list)
                }
            # Initialize pipeline items dict
            if pipeline_id not in self.pipeline_items:
                self.pipeline_items[pipeline_id] = {}

    def get_pipeline_items(self, pipeline_id: str) -> List[ProgressItem]:
        """
        Get all items for a pipeline (completed + active).

        Args:
            pipeline_id: Pipeline identifier

        Returns:
            List of ProgressItem objects for the pipeline, ordered by pipeline_order
        """
        if not self.enabled or pipeline_id not in self.pipeline_contexts:
            return []

        with self.lock:
            items = []
            # Get items from pipeline_items (completed)
            if pipeline_id in self.pipeline_items:
                items.extend(self.pipeline_items[pipeline_id].values())
            
            # Get active items that belong to this pipeline
            for tracking_id, item in self.active_items.items():
                if item.pipeline_id == pipeline_id:
                    items.append(item)
            
            # Sort by pipeline_order
            items.sort(key=lambda x: (x.pipeline_order if x.pipeline_order is not None else 999, x.module or ""))
            return items

    def clear_pipeline_context(self, pipeline_id: str) -> None:
        """
        Clear pipeline context when pipeline completes.

        Args:
            pipeline_id: Pipeline identifier to clear
        """
        if not self.enabled:
            return

        with self.lock:
            if pipeline_id in self.pipeline_contexts:
                del self.pipeline_contexts[pipeline_id]
            if pipeline_id in self.pipeline_items:
                del self.pipeline_items[pipeline_id]
            if pipeline_id in self.pipeline_module_order:
                del self.pipeline_module_order[pipeline_id]

    def start_tracking(
        self,
        file: Optional[str] = None,
        module: Optional[str] = None,
        submodule: Optional[str] = None,
        message: str = "",
        pipeline_id: Optional[str] = None,
    ) -> str:
        """
        Start tracking a progress item.

        Args:
            file: File being processed
            module: Module name
            submodule: Submodule/class name
            message: Progress message

        Returns:
            Tracking ID
        """
        if not self.enabled:
            return ""

        self._ensure_jupyter_display()

        # Auto-detect if not provided
        if not module or not submodule:
            detected_module, detected_submodule = ModuleDetector.detect_from_call_stack(
                depth=3
            )
            module = module or detected_module
            submodule = submodule or detected_submodule

        # Create tracking ID
        tracking_id = f"{module}:{submodule}:{file or ''}"

        with self.lock:
            # Determine pipeline_id and pipeline_order if module is part of a pipeline
            pipeline_order = None
            if pipeline_id is None and module:
                # Try to find pipeline_id from existing contexts
                for pid, modules in self.pipeline_contexts.items():
                    if module in modules:
                        pipeline_id = pid
                        if pid in self.pipeline_module_order:
                            pipeline_order = self.pipeline_module_order[pid].get(module)
                        break

            item = ProgressItem(
                file=file,
                module=module,
                submodule=submodule,
                status="running",
                start_time=time.time(),
                message=message,
                emoji=self._get_emoji_for_module(module or ""),
                pipeline_id=pipeline_id,
                pipeline_order=pipeline_order,
            )

            self.active_items[tracking_id] = item
            
            # If part of pipeline, also store in pipeline_items
            if pipeline_id:
                if pipeline_id not in self.pipeline_items:
                    self.pipeline_items[pipeline_id] = {}
                self.pipeline_items[pipeline_id][tracking_id] = item

            displays = list(self.displays)

        self._update_displays(displays, item)
        return tracking_id

    def update_tracking(
        self, tracking_id: str, status: str = "running", message: str = ""
    ) -> None:
        """
        Update tracking status.

        Args:
            tracking_id: Tracking ID from start_tracking
            status: New status (running, completed, failed)
            message: Progress message
        """
        if not self.enabled or not tracking_id:
            return

        item = None
        displays: List[ProgressDisplay] = []
        with self.lock:
            if tracking_id in self.active_items:
                item = self.active_items[tracking_id]
                item.status = status
                item.message = message

                # Calculate ETA if progress information is available
                if item.processed_items is not None and item.total_items is not None:
                    item.progress_percentage = (
                        (item.processed_items / item.total_items * 100)
                        if item.total_items > 0
                        else 0.0
                    )
                    item.estimated_remaining = self._calculate_eta(item)

                if status in ("completed", "failed"):
                    item.end_time = time.time()
                    # Reset progress fields on completion
                    item.progress_percentage = 100.0 if status == "completed" else None
                    item.estimated_remaining = 0.0 if status == "completed" else None
                    
                    # If part of an active pipeline, keep it in pipeline_items instead of removing
                    if item.pipeline_id and item.pipeline_id in self.pipeline_contexts:
                        # Keep in pipeline_items for visibility
                        if item.pipeline_id not in self.pipeline_items:
                            self.pipeline_items[item.pipeline_id] = {}
                        self.pipeline_items[item.pipeline_id][tracking_id] = item
                        # Remove from active_items but keep in pipeline_items
                        del self.active_items[tracking_id]
                    else:
                        # Not part of pipeline, move to completed items as before
                        self.items.append(item)
                        del self.active_items[tracking_id]

                displays = list(self.displays)

        if item is not None:
            self._update_displays(displays, item)

    def update_progress(
        self,
        tracking_id: str,
        processed: int,
        total: int,
        message: str = "",
    ) -> None:
        """
        Update progress with item counts and calculate ETA.

        Args:
            tracking_id: Tracking ID from start_tracking
            processed: Number of items processed so far
            total: Total number of items to process
            message: Optional progress message
        """
        if not self.enabled or not tracking_id:
            return

        self._ensure_jupyter_display()

        item = None
        displays: List[ProgressDisplay] = []
        with self.lock:
            if tracking_id in self.active_items:
                item = self.active_items[tracking_id]
                item.processed_items = processed
                item.total_items = total
                item.progress_percentage = (
                    (processed / total * 100) if total > 0 else 0.0
                )
                item.estimated_remaining = self._calculate_eta(item)
                if message:
                    item.message = message

                displays = list(self.displays)

        if item is not None:
            self._update_displays(displays, item, force_console=True)

    def _calculate_eta(self, item: ProgressItem) -> Optional[float]:
        """
        Calculate estimated time remaining based on progress.

        Args:
            item: ProgressItem with progress information

        Returns:
            Estimated remaining time in seconds, or None if cannot calculate
        """
        if (
            item.start_time is None
            or item.processed_items is None
            or item.total_items is None
            or item.processed_items <= 0
        ):
            return None

        elapsed = time.time() - item.start_time
        if elapsed <= 0:
            return None

        # Calculate processing rate (items per second)
        rate = item.processed_items / elapsed
        if rate <= 0:
            return None

        # Calculate remaining items
        remaining_items = item.total_items - item.processed_items
        if remaining_items <= 0:
            return 0.0

        # Calculate ETA
        eta_seconds = remaining_items / rate
        return max(0.0, eta_seconds)

    def stop_tracking(
        self, tracking_id: str, status: str = "completed", message: str = "", metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Stop tracking an item.

        Args:
            tracking_id: Tracking ID from start_tracking
            status: Final status (completed, failed)
            message: Final message
            metadata: Optional metadata to store (e.g., extraction_counts, core_dependency)
        """
        with self.lock:
            # Update metadata if provided
            if tracking_id in self.active_items:
                item = self.active_items[tracking_id]
                if metadata:
                    item.metadata.update(metadata)
            # Also check pipeline_items
            for pipeline_id, items in self.pipeline_items.items():
                if tracking_id in items:
                    item = items[tracking_id]
                    if metadata:
                        item.metadata.update(metadata)
                    break
        
        self.update_tracking(tracking_id, status=status, message=message)

    def _get_emoji_for_module(self, module: str) -> str:
        """Get emoji for module."""
        if not self.use_emoji or not module:
            return ""

        emoji_map = {
            "ingest": "📥",
            "parse": "🔍",
            "kg": "🧠",
            "embeddings": "💾",
            "normalize": "🔧",
            "ontology": "📚",
            "semantic_extract": "🎯",
            "seed": "🌱",
            "split": "✂️",
            "triplet_store": "🗄️",
            "vector_store": "📊",
            "export": "💾",
            "reasoning": "🤔",
            "kg_qa": "✅",
            "visualization": "📈",
            "context": "🔗",
            "conflicts": "⚠️",
            "deduplication": "🔄",
            "pipeline": "⚙️",
        }

        module_lower = module.lower()
        for key, emoji in emoji_map.items():
            if key in module_lower:
                return emoji
        return "⏳"

    def show_summary(self) -> None:
        """Show final progress summary."""
        if not self.enabled:
            return

        with self.lock:
            # Add any remaining active items
            all_items = self.items + list(self.active_items.values())
            displays = list(self.displays)

        # Show summary on all displays without holding the tracker lock.
        for display in displays:
            display.show_summary(all_items)

    @contextmanager
    def track(
        self,
        file: Optional[str] = None,
        module: Optional[str] = None,
        submodule: Optional[str] = None,
        message: str = "",
    ):
        """
        Context manager for automatic tracking.

        Usage:
            with progress_tracker.track(file="doc.pdf", message="Processing"):
                # code here
        """
        tracking_id = self.start_tracking(
            file=file, module=module, submodule=submodule, message=message
        )
        try:
            yield tracking_id
            self.stop_tracking(tracking_id, status="completed")
        except Exception as e:
            self.stop_tracking(tracking_id, status="failed", message=str(e))
            raise


# Global singleton instance
_global_tracker: Optional[ProgressTracker] = None


def get_progress_tracker() -> ProgressTracker:
    """Get global progress tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ProgressTracker.get_instance()

    _global_tracker._ensure_jupyter_display()
    
    return _global_tracker


def track_progress(
    file: Optional[str] = None,
    module: Optional[str] = None,
    submodule: Optional[str] = None,
):
    """
    Decorator for automatic progress tracking.

    Usage:
        @track_progress
        def my_function():
            # Automatically tracked
            pass

        @track_progress(file="doc.pdf")
        def process_file():
            # Tracked with file context
            pass
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            tracker = get_progress_tracker()

            # Try to extract file from args/kwargs
            detected_file = file
            if not detected_file:
                # Look for common file parameter names
                for arg_name in ["file", "file_path", "path", "source", "filename"]:
                    if arg_name in kwargs:
                        detected_file = str(kwargs[arg_name])
                        break
                    elif args and isinstance(args[0], (str, Path)):
                        detected_file = str(args[0])
                        break

            # Auto-detect module/submodule if not provided
            detected_module = module
            detected_submodule = submodule
            if not detected_module or not detected_submodule:
                frame_module, frame_submodule = ModuleDetector.detect_from_call_stack(
                    depth=2
                )
                detected_module = detected_module or frame_module
                detected_submodule = detected_submodule or frame_submodule

            # Use function name as fallback for submodule
            if not detected_submodule:
                detected_submodule = func.__name__

            # Start tracking
            tracking_id = tracker.start_tracking(
                file=detected_file,
                module=detected_module,
                submodule=detected_submodule,
                message=f"Running {func.__name__}",
            )

            try:
                result = func(*args, **kwargs)
                tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Completed {func.__name__}",
                )
                return result
            except Exception as e:
                tracker.stop_tracking(
                    tracking_id,
                    status="failed",
                    message=f"Failed {func.__name__}: {str(e)}",
                )
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    # Handle both @track_progress and @track_progress(...) usage
    if callable(file):
        # Used as @track_progress without parentheses
        func = file
        file = None
        return decorator(func)
    else:
        # Used as @track_progress(...) with arguments
        return decorator
