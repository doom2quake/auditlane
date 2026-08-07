"""Cleanroom manifest — the deterministic pre-audit package, in Python.

This is the load-bearing pure core of AuditLane. It takes a target repo's spec
(pinned toolchain, source files, test-suite result, on-chain deployments) and folds
it into a single content-addressed **manifest**: a normalised, evidence-carrying
record a whitelisted Arbitrum audit firm can open without reconstructing the build.

The manifest is a pure function of its inputs. Two runs over the same repo state
produce a byte-identical manifest and the same `manifest_id` digest, which is exactly
the reproducibility property M1 promises: a reviewer clones the repo, re-runs the
documented command, and gets the identical manifest and test counts we publish.

Pure and dependency-free: no I/O, no network, no clock. Everything that varies
(source bytes, deployed bytecode, test counts) is passed in, so the digest is a
function of evidence and nothing else. This mirrors `src/BuildRegistry.sol`'s
`manifestDigest` byte-for-byte: the same field order, the same canonical joining, the
same keccak-shaped folding, so an on-chain commitment agrees with the off-chain one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

# --- reproducibility reason codes. 0 == REPRODUCIBLE. -----------------------
# Identical set and order to src/BuildRegistry.sol so the two agree on a verdict.
REPRODUCIBLE = 0
NO_TOOLCHAIN_PIN = 1
BUILD_FAILED = 2
TESTS_FAILED = 3
SOURCE_HASH_MISMATCH = 4
BYTECODE_MISMATCH = 5
MISSING_DEPLOYMENT = 6

_REASONS = {
    NO_TOOLCHAIN_PIN: "toolchain is not pinned (no exact solc/rust version)",
    BUILD_FAILED: "clean build did not succeed",
    TESTS_FAILED: "declared test suite did not pass",
    SOURCE_HASH_MISMATCH: "a source file hash does not match its manifest entry",
    BYTECODE_MISMATCH: "deployed bytecode does not match the built artifact",
    MISSING_DEPLOYMENT: "a manifest contract has no resolved on-chain deployment",
}


def reason_for(code: int) -> str:
    """Human-readable reason for a code. Matches BuildRegistry.reasonFor in Solidity."""
    return _REASONS.get(code, "reproducible")


class Verdict(IntEnum):
    OK = 0
    NOT_REPRODUCIBLE = 1


def _h(data: bytes) -> str:
    """Content hash of raw bytes. sha256, hex, no prefix. The manifest is built from
    these leaf hashes so it never carries source bytes, only commitments to them."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Toolchain:
    """The pinned build environment. An unpinned toolchain is not reproducible."""

    solc: str = ""          # e.g. "0.8.24"
    evm_version: str = ""    # e.g. "cancun"
    optimizer_runs: int = 0
    framework: str = ""      # e.g. "foundry 1.7.1"

    @property
    def is_pinned(self) -> bool:
        # A reproducible build needs an exact compiler version, not a caret range.
        return bool(self.solc) and "^" not in self.solc and "~" not in self.solc


@dataclass(frozen=True)
class SourceFile:
    """One source file, committed to by content hash. `path` is repo-relative and
    normalised (forward slashes) so the digest is platform-independent."""

    path: str
    sha256: str
    size: int

    @staticmethod
    def of(path: str, content: bytes) -> "SourceFile":
        return SourceFile(path=path.replace("\\", "/"), sha256=_h(content), size=len(content))


@dataclass(frozen=True)
class TestResult:
    """The captured result of running the declared suite from clean."""

    __test__ = False  # not a pytest test class

    suite: str      # e.g. "forge test", "pytest"
    passed: int
    failed: int
    command: str

    @property
    def green(self) -> bool:
        return self.failed == 0 and self.passed > 0


@dataclass(frozen=True)
class Contract:
    """A contract in the package: its source commitment and, where resolved, its
    on-chain deployment. `deployed_bytecode_hash` is None until the chain seam
    resolves it, so a missing deployment is an explicit, checkable state."""

    name: str
    source_path: str
    artifact_bytecode_hash: str            # hash of the locally built runtime bytecode
    address: Optional[str] = None          # Arbitrum Sepolia address, if deployed
    deployed_bytecode_hash: Optional[str] = None  # hash of on-chain runtime bytecode


@dataclass(frozen=True)
class RepoSpec:
    """Everything a build needs, passed in so the fold stays pure."""

    name: str
    toolchain: Toolchain
    sources: List[SourceFile]
    tests: List[TestResult]
    contracts: List[Contract]


@dataclass(frozen=True)
class Manifest:
    """The finished pre-audit package. Serialisable, content-addressed, and its own
    `manifest_id` is a deterministic digest of every field below."""

    version: str
    repo: str
    toolchain: Toolchain
    sources: List[SourceFile]
    tests: List[TestResult]
    contracts: List[Contract]
    verdict: Verdict
    reason_codes: List[int]
    manifest_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "repo": self.repo,
            "toolchain": {
                "solc": self.toolchain.solc,
                "evm_version": self.toolchain.evm_version,
                "optimizer_runs": self.toolchain.optimizer_runs,
                "framework": self.toolchain.framework,
            },
            "sources": [{"path": s.path, "sha256": s.sha256, "size": s.size} for s in self.sources],
            "tests": [
                {"suite": t.suite, "passed": t.passed, "failed": t.failed, "command": t.command}
                for t in self.tests
            ],
            "contracts": [
                {
                    "name": c.name,
                    "source_path": c.source_path,
                    "artifact_bytecode_hash": c.artifact_bytecode_hash,
                    "address": c.address,
                    "deployed_bytecode_hash": c.deployed_bytecode_hash,
                }
                for c in self.contracts
            ],
            "verdict": int(self.verdict),
            "reason_codes": list(self.reason_codes),
            "manifest_id": self.manifest_id,
        }


def _canonical_payload(spec: RepoSpec, verdict: int, codes: List[int]) -> str:
    """The exact string the manifest digest is taken over. Field order and joining
    are FIXED and mirrored in BuildRegistry.sol's `manifestDigest`, so the off-chain
    manifest_id equals the on-chain commitment. Sources and contracts are sorted by a
    stable key so ordering in the repo cannot change the digest."""
    tc = spec.toolchain
    parts: List[str] = [
        "auditlane/1",
        spec.name,
        f"solc={tc.solc}",
        f"evm={tc.evm_version}",
        f"opt={tc.optimizer_runs}",
        f"fw={tc.framework}",
    ]
    for s in sorted(spec.sources, key=lambda x: x.path):
        parts.append(f"src:{s.path}={s.sha256}:{s.size}")
    for t in sorted(spec.tests, key=lambda x: x.suite):
        parts.append(f"test:{t.suite}={t.passed}/{t.failed}")
    for c in sorted(spec.contracts, key=lambda x: x.name):
        parts.append(
            f"c:{c.name}:{c.source_path}:{c.artifact_bytecode_hash}"
            f":{c.address or ''}:{c.deployed_bytecode_hash or ''}"
        )
    parts.append(f"verdict={verdict}")
    parts.append("codes=" + ",".join(str(x) for x in codes))
    return "\n".join(parts)


def check(spec: RepoSpec) -> List[int]:
    """Deterministic reproducibility check. Returns the reason codes that apply, in a
    FIXED order (same order as BuildRegistry.check). An empty list means REPRODUCIBLE.
    Fail-closed: any unmet condition adds a code; a green manifest carries none."""
    codes: List[int] = []

    if not spec.toolchain.is_pinned:
        codes.append(NO_TOOLCHAIN_PIN)

    # A build with no source files never "succeeded" from clean.
    if not spec.sources:
        codes.append(BUILD_FAILED)

    # Every declared suite must be green.
    if not spec.tests or any(not t.green for t in spec.tests):
        codes.append(TESTS_FAILED)

    # Each contract must be backed by a source file present in the manifest.
    source_paths = {s.path for s in spec.sources}
    for c in spec.contracts:
        if c.source_path not in source_paths:
            if SOURCE_HASH_MISMATCH not in codes:
                codes.append(SOURCE_HASH_MISMATCH)
            break

    # Each contract must resolve to an on-chain deployment...
    for c in spec.contracts:
        if c.deployed_bytecode_hash is None:
            if MISSING_DEPLOYMENT not in codes:
                codes.append(MISSING_DEPLOYMENT)
            break

    # ...and the on-chain bytecode must match the locally built artifact.
    for c in spec.contracts:
        if (
            c.deployed_bytecode_hash is not None
            and c.deployed_bytecode_hash != c.artifact_bytecode_hash
        ):
            if BYTECODE_MISMATCH not in codes:
                codes.append(BYTECODE_MISMATCH)
            break

    return codes


def build(spec: RepoSpec) -> Manifest:
    """Fold a RepoSpec into a finished, content-addressed Manifest. Pure: the same
    spec yields a byte-identical manifest and the same manifest_id every time."""
    codes = check(spec)
    verdict = Verdict.OK if not codes else Verdict.NOT_REPRODUCIBLE
    payload = _canonical_payload(spec, int(verdict), codes)
    manifest_id = "0x" + _h(payload.encode())
    return Manifest(
        version="auditlane/1",
        repo=spec.name,
        toolchain=spec.toolchain,
        sources=list(spec.sources),
        tests=list(spec.tests),
        contracts=list(spec.contracts),
        verdict=verdict,
        reason_codes=codes,
        manifest_id=manifest_id,
    )


def manifest_json(m: Manifest) -> str:
    """Canonical JSON serialisation (sorted keys, no whitespace drift) so a written
    manifest file is itself reproducible byte-for-byte."""
    return json.dumps(m.to_dict(), sort_keys=True, indent=2)
