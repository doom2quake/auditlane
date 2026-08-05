"""AuditLane — a reproducible pre-audit cleanroom for the Arbitrum Audit Program.

`auditlane build` folds an Arbitrum repo into a content-addressed manifest: a pinned
toolchain, captured test counts, and every contract's source hash and Arbitrum Sepolia
deployed-bytecode hash checked against the built artifact. A whitelisted audit firm
opens a build that already works instead of reconstructing one, and a reviewer re-runs
the same command to get the identical manifest id.

One reproducibility spec, two co-validating implementations: the Solidity BuildRegistry
(`src/BuildRegistry.sol`) and the Python core (`auditlane/manifest.py`) share the same
reason codes and the same fixed check order, so a divergence is a failing test.
"""

from .config import AuditLaneSettings, settings
from .manifest import (
    Contract,
    Manifest,
    RepoSpec,
    SourceFile,
    TestResult,
    Toolchain,
    Verdict,
    build,
    check,
    manifest_json,
    reason_for,
)

__all__ = [
    "AuditLaneSettings", "settings",
    "Toolchain", "SourceFile", "TestResult", "Contract", "RepoSpec",
    "Manifest", "Verdict", "build", "check", "manifest_json", "reason_for",
]

__version__ = "0.1.0"
