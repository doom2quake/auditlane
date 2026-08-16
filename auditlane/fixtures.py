"""Offline fixture — a self-contained sample Arbitrum repo and its matching seed.

M1 must run keyless. This module ships a small sample Arbitrum project on disk
(`fixtures/sample-vault/`: one contract, its built artifact, a deployments map, and a
captured test result) and a helper that seeds the offline chain resolver so the
sample's Arbitrum Sepolia deployment resolves to the SAME runtime bytecode hash the
built artifact carries. That is the honest, reproducible case: a reviewer runs
`auditlane build` with no RPC and gets a green, content-addressed manifest.

The seed is computed from the fixture's own artifact bytes, not hard-coded, so if the
sample contract changes the honest case stays honest and a tampered artifact still
fails closed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .chain import ChainResolver
from .config import AuditLaneSettings

# The sample Arbitrum repo AuditLane builds by default.
FIXTURE_REPO = str((Path(__file__).resolve().parent.parent / "fixtures" / "sample-vault"))


def _artifact_hash(repo: Path, contract: str) -> str:
    art = repo / "out" / f"{contract}.sol" / f"{contract}.json"
    data = json.loads(art.read_text())
    obj = (data.get("deployedBytecode") or {}).get("object") or ""
    if obj.startswith("0x"):
        obj = obj[2:]
    return hashlib.sha256(bytes.fromhex(obj)).hexdigest()


def seed_fixture_resolver(cfg: AuditLaneSettings | None = None) -> ChainResolver:
    """A ChainResolver whose offline fixture returns, for each of the sample repo's
    deployment addresses, the runtime bytecode hash of the sample's built artifact —
    the honest 'deployed == built' case that yields a reproducible manifest."""
    resolver = ChainResolver(cfg or AuditLaneSettings(offline=True))
    repo = Path(FIXTURE_REPO)
    deployments = json.loads((repo / "auditlane.deployments.json").read_text()).get("contracts", {})
    for name, meta in deployments.items():
        address = meta.get("address")
        if not address:
            continue
        resolver.seed(address, _artifact_hash(repo, name))
    return resolver
