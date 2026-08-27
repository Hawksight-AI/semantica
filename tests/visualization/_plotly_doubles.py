"""Shared helper for visualization tests.

The visualization modules treat Plotly as optional: they bind ``px``, ``go`` and
``make_subplots`` to ``None`` when the import fails, and raise ``ProcessingError``
from ``_check_dependencies()``. Tests that exercise a Plotly-backed path need
those names to be usable, otherwise ``patch("...go.Figure")`` fails on ``None``
and the visualizers refuse to run.

``plotly_doubles`` fills in a double for each alias that is ``None``, so the
tests describe their own requirements instead of depending on whether Plotly
happens to be installed. When Plotly is installed the aliases are left alone and
the patches keep asserting against the real attribute names.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

PLOTLY_ALIASES = ("px", "go", "make_subplots")


@contextmanager
def plotly_doubles(*modules):
    """Stand in for the module-level Plotly aliases that are unavailable."""
    with ExitStack() as stack:
        for module in modules:
            for alias in PLOTLY_ALIASES:
                if getattr(module, alias, "unused") is None:
                    stack.enter_context(patch.object(module, alias, MagicMock()))
        yield
