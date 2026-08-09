"""Execution sidecars.

This package is intentionally separate from the read-only strategy scripts.  A
production deployment runs it as a dedicated Unix account; strategy code only
submits validated intents and never receives keystore paths or passwords.
"""
