"""Repo scanner — read an Arbitrum repo on disk into a RepoSpec.

`auditlane build` points the scanner at a target repo directory. The scanner reads:

  * the pinned toolchain from `foundry.toml` (solc version, evm version, optimizer),
  * every Solidity source under `src/` (committed by content hash),
  * the build artifacts under `out/` (each contract's runtime bytecode hash),
  * an `auditlane.deployments.json` mapping contract name -> Arbitrum Sepolia address.

It resolves each contract's deployed bytecode hash through the chain seam, then hands
the assembled RepoSpec to `manifest.build`. Everything the scanner reads is on disk or
on-chain, so a reviewer who clones the repo and re-runs gets the same inputs and the
same manifest.

The one thing the scanner does NOT do is invent a green test suite: the test counts
come from a captured `auditlane.tests.json` the build command writes after running the
suite, so the counts in the manifest are the counts that actually ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from .chain import ChainResolver
from .config import AuditLaneSettings, settings
from .manifest import (
    Contract,
    Manifest,
    RepoSpec,
    SourceFile,
    TestResult,
    Toolchain,
    build,
)


def _read_toolchain(repo: Path) -> Toolchain:
    """Parse foundry.toml for the pinned toolchain. Minimal hand parser (no toml dep):
    we only need four keys and want a keyless, dependency-light build."""
    ft = repo / "foundry.toml"
    solc = evm = fw = ""
    runs = 0
    if ft.exists():
        for raw in ft.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key in ("solc", "solc_version"):
                solc = val
            elif key == "evm_version":
                evm = val
            elif key == "optimizer_runs":
                try:
                    runs = int(val)
                except ValueError:
                    runs = 0
    fw = "foundry"
    return Toolchain(solc=solc, evm_version=evm, optimizer_runs=runs, framework=fw)


def _read_sources(repo: Path) -> List[SourceFile]:
    """Every .sol file under src/, committed by content hash, sorted by path."""
    src = repo / "src"
    out: List[SourceFile] = []
    if src.exists():
        for p in sorted(src.rglob("*.sol")):
            rel = p.relative_to(repo).as_posix()
            out.append(SourceFile.of(rel, p.read_bytes()))
    return out


def _artifact_bytecode_hash(repo: Path, contract: str) -> Optional[str]:
    """Read the built runtime bytecode for `contract` from Foundry's out/ layout
    (out/<Contract>.sol/<Contract>.json -> deployedBytecode.object) and hash it."""
    import hashlib

    art = repo / "out" / f"{contract}.sol" / f"{contract}.json"
    if not art.exists():
        return None
    data = json.loads(art.read_text())
    obj = (data.get("deployedBytecode") or {}).get("object") or ""
    if obj.startswith("0x"):
        obj = obj[2:]
    if not obj:
        return None
    return hashlib.sha256(bytes.fromhex(obj)).hexdigest()


def _read_tests(repo: Path) -> List[TestResult]:
    """The captured test result the build command wrote after running the suite."""
    tf = repo / "auditlane.tests.json"
    if not tf.exists():
        return []
    data = json.loads(tf.read_text())
    out: List[TestResult] = []
    for t in data.get("suites", []):
        out.append(TestResult(
            suite=t["suite"], passed=int(t["passed"]),
            failed=int(t["failed"]), command=t.get("command", ""),
        ))
    return out


def _read_deployments(repo: Path) -> dict:
    df = repo / "auditlane.deployments.json"
    if not df.exists():
        return {}
    return json.loads(df.read_text()).get("contracts", {})


def scan(repo_path: str, cfg: AuditLaneSettings | None = None,
         resolver: ChainResolver | None = None) -> RepoSpec:
    """Read a repo on disk into a RepoSpec, resolving each contract's on-chain
    deployment through the chain seam."""
    cfg = cfg or settings
    repo = Path(repo_path)
    resolver = resolver or ChainResolver(cfg)

    toolchain = _read_toolchain(repo)
    sources = _read_sources(repo)
    tests = _read_tests(repo)
    deployments = _read_deployments(repo)

    contracts: List[Contract] = []
    for name, meta in sorted(deployments.items()):
        source_path = meta.get("source", f"src/{name}.sol")
        artifact_hash = _artifact_bytecode_hash(repo, name) or meta.get("artifact_bytecode_hash", "")
        address = meta.get("address")
        deployed_hash = None
        if address:
            deployed_hash = resolver.resolve(address).deployed_bytecode_hash or None
        contracts.append(Contract(
            name=name,
            source_path=source_path,
            artifact_bytecode_hash=artifact_hash,
            address=address,
            deployed_bytecode_hash=deployed_hash,
        ))

    return RepoSpec(
        name=meta_name(repo, deployments),
        toolchain=toolchain,
        sources=sources,
        tests=tests,
        contracts=contracts,
    )


def meta_name(repo: Path, deployments: dict) -> str:
    df = repo / "auditlane.deployments.json"
    if df.exists():
        data = json.loads(df.read_text())
        if data.get("repo"):
            return data["repo"]
    return repo.name


def build_manifest(repo_path: str, cfg: AuditLaneSettings | None = None,
                   resolver: ChainResolver | None = None) -> Manifest:
    """Scan a repo and fold it into a finished manifest — the M1 deliverable."""
    return build(scan(repo_path, cfg=cfg, resolver=resolver))
