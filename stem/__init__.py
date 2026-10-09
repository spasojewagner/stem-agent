"""Stem agent v2.

The core (everything in this package except `envs/` and `cli.py`) knows nothing
about any domain. Its only built-in capability is development: looking at the
environment it has been placed in and reshaping its own genome until it works
there. `tests/test_core_is_domain_free.py` enforces that.
"""

__version__ = "2.0.0-dev"
