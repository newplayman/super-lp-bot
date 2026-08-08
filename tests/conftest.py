"""Repository-wide pytest collection hygiene."""

# These preserved tests import helpers and artifacts from a retired developer
# workstation path. Ignore them before module import so default collection is
# portable and cannot fail before a runtime skip/marker would take effect.
collect_ignore_glob = ["legacy_quarantine/test_*.py"]
