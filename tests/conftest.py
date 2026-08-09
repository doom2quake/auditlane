"""Keyless, deterministic test environment: in-memory state, offline Arbitrum seam."""

import os

os.environ.setdefault("AUDITLANE_IN_MEMORY_STATE", "1")
os.environ.setdefault("AUDITLANE_OFFLINE", "1")
