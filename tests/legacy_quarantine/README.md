# Legacy test quarantine

These tests are retained unchanged for provenance, but depend on a retired
developer-workstation path and therefore are excluded from default pytest
collection by `tests/conftest.py` before import.

`legacy_quarantine` is registered in `pytest.ini` for any future migration that
turns an ignored module into an explicitly selectable, portable test. Moving a
test back into the default suite requires replacing its workstation paths with
repository-relative fixtures first.
