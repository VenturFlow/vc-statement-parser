"""Extractor registry.

Two registration paths are supported:

1. **In-tree** — for extractors that ship with this package, append the
   instance to ``_BUILTIN_EXTRACTORS`` below. This is the right path when
   contributing back to the project (see ``CONTRIBUTING.md``).

2. **External plugin** — third-party packages can register extractors via
   the ``vc_statement_parser.extractors`` setuptools entry point. The plugin
   author writes::

       # in their pyproject.toml
       [project.entry-points."vc_statement_parser.extractors"]
       my_admin = "my_pkg.my_module:MyAdminExtractor"

   The referenced object can be either an ``Extractor`` subclass (it will be
   instantiated) or an instance. After ``pip install my-extractor-pkg``, the
   extractor is automatically available to ``parse_statement()`` — no edits
   to this repository required.

   See ``docs/PLUGINS.md`` for a complete walkthrough.

The exported ``DETERMINISTIC_EXTRACTORS`` tuple is computed once at import
time by concatenating the in-tree list with whatever entry-point plugins
are installed. In-tree extractors take precedence (earlier in the tuple);
plugin extractors are appended in the order ``importlib.metadata`` returns
them, which is normally install order.
"""

from __future__ import annotations

import logging
import warnings
from importlib import metadata

from .base import Extractor
from .gaap_scpc import GaapScpcExtractor
from .standish import StandishExtractor

_log = logging.getLogger(__name__)

# Plugins should register against this group name. Documented in PLUGINS.md.
ENTRY_POINT_GROUP = "vc_statement_parser.extractors"

# In-tree extractors. PRs that add an administrator append here.
_BUILTIN_EXTRACTORS: tuple[Extractor, ...] = (
    StandishExtractor(),
    GaapScpcExtractor(),
)


def _load_plugin_extractors() -> tuple[Extractor, ...]:
    """Discover and instantiate extractors registered via setuptools entry points.

    A misbehaving plugin (import error, attribute not found, wrong type) is
    skipped with a warning rather than crashing the host application — one
    bad plugin must not break parsing for everyone else. Failures are also
    logged at WARNING level so operators can find them in production logs.
    """
    discovered: list[Extractor] = []
    try:
        eps = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception as e:  # pragma: no cover - defensive, very-old-Python paths
        _log.debug("entry_points() lookup failed: %s", e)
        return ()

    for ep in eps:
        try:
            obj = ep.load()
        except Exception as e:
            warnings.warn(
                f"vc-statement-parser: failed to load extractor plugin "
                f"{ep.name!r} ({ep.value!r}): {e}",
                stacklevel=2,
            )
            _log.warning("failed to load extractor plugin %r: %s", ep.name, e)
            continue

        # Accept either an Extractor subclass (instantiate) or an instance.
        try:
            instance = obj() if isinstance(obj, type) else obj
        except Exception as e:
            warnings.warn(
                f"vc-statement-parser: failed to instantiate plugin extractor {ep.name!r}: {e}",
                stacklevel=2,
            )
            continue

        if not isinstance(instance, Extractor):
            warnings.warn(
                f"vc-statement-parser: plugin {ep.name!r} did not return an "
                f"Extractor instance (got {type(instance).__name__!r}); skipping.",
                stacklevel=2,
            )
            continue

        discovered.append(instance)

    return tuple(discovered)


# Built once at import time. In-tree extractors take precedence — they're at
# the head of the tuple and are matched first by `parse_statement()`.
DETERMINISTIC_EXTRACTORS: tuple[Extractor, ...] = (
    *_BUILTIN_EXTRACTORS,
    *_load_plugin_extractors(),
)

__all__ = [
    "DETERMINISTIC_EXTRACTORS",
    "ENTRY_POINT_GROUP",
    "Extractor",
    "GaapScpcExtractor",
    "StandishExtractor",
]
