"""
Invocation policy for methods registered through a MethodRegistry.

Every module that supports custom methods used to wrap the registered callable
in a bare `except Exception`, log a warning, and carry on into the built-in
implementation. That makes a registered method advisory: it can add behaviour,
but it cannot decline.

For a gate, a validator or a policy check that is the whole point. Raising is
how such a method says "do not produce this output". Catching the exception and
running the default produces exactly the output the caller registered the method
to prevent, and the only trace is a warning (issue #1108).

Exceptions from a registered method therefore propagate by default. Callers who
relied on the old behaviour can pass `fallback_on_custom_error=True`, which
restores the warn-and-continue path for that call.
"""

from typing import Any, Callable


class _FellBack:
    """Sentinel: the custom method failed and the caller should use the default."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "CUSTOM_METHOD_FELL_BACK"


#: Returned by :func:`call_custom_method` when a custom method raised and
#: ``fallback_on_custom_error=True`` was passed. Compare with ``is``.
CUSTOM_METHOD_FELL_BACK = _FellBack()


def call_custom_method(
    logger: Any,
    method: Any,
    custom_method: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Invoke a registered custom method.

    Args:
        logger: Module logger, used only on the opt-in fallback path.
        method: The registered name, for the warning message.
        custom_method: The registered callable.
        *args: Positional arguments for the custom method.
        **kwargs: Keyword arguments for the custom method. The reserved key
            ``fallback_on_custom_error`` is consumed here and never forwarded.

    Returns:
        Whatever the custom method returns, or :data:`CUSTOM_METHOD_FELL_BACK`
        when it raised and the caller opted into falling back.

    Raises:
        Exception: Whatever the custom method raised, unless the caller passed
            ``fallback_on_custom_error=True``.
    """
    fallback = bool(kwargs.pop("fallback_on_custom_error", False))

    if not fallback:
        return custom_method(*args, **kwargs)

    try:
        return custom_method(*args, **kwargs)
    except Exception as exc:
        logger.warning(
            f"Custom method {method} failed: {exc}, falling back to default "
            "because fallback_on_custom_error was set"
        )
        return CUSTOM_METHOD_FELL_BACK
