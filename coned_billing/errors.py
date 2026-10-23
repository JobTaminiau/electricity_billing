"""Package-specific exceptions.

Every error raised deliberately by ``coned_billing`` derives from
:class:`ConEdBillingError`. Errors about invalid input values also derive from
:class:`ValueError`, so existing ``except ValueError`` handlers keep working.
"""

from __future__ import annotations

__all__ = ["ConEdBillingError", "LoadDataError"]


class ConEdBillingError(Exception):
    """Base class for errors raised by coned_billing."""


class LoadDataError(ConEdBillingError, ValueError):
    """The load profile violates the input contract (see docs/load_data.md)."""
