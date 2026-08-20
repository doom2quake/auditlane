"""AuditLane CLI — a reproducible pre-audit cleanroom for Arbitrum projects.

    auditlane build <repo>     # scan a repo -> content-addressed pre-audit manifest
    auditlane demo             # the whole hero story in one run
    auditlane --help

The hero: point AuditLane at an Arbitrum repo and it produces a normalised,
evidence-carrying package a whitelisted audit firm can open without reconstruction:
a pinned toolchain, the captured test counts, and a manifest of every contract with
its source hash and its Arbitrum Sepolia deployed-bytecode hash checked against the
built artifact. The manifest is content-addressed, so a reviewer re-runs the same
command and gets the identical manifest id. Keyless offline by default; the live
Arbitrum Sepolia bytecode path gates on AUDITLANE_RPC_URL.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from .agent import AuditLaneAgent
from .chain import ChainResolver
from .config import AuditLaneSettings
from .fixtures import FIXTURE_REPO, seed_fixture_resolver
from .manifest import reason_for


def _pace() -> None:
    try:
        d = float(os.getenv("AUDITLANE_PACE", "0"))
    except ValueError:
        d = 0.0
    if d > 0:
        time.sleep(d)


# --- tiny ANSI palette (the terminal is part of the demo) --------------------
_C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[36m",
      "d": "\033[2m", "bold": "\033[1m", "mag": "\033[35m", "x": "\033[0m"}


def _p(s: str = "") -> None:
    print(s)


def _kv(k: str, v: str, color: str = "b") -> None:
    print(f"  {_C['d']}{k:<14}{_C['x']} {_C[color]}{v}{_C['x']}")


def _rule(title: str = "") -> None:
    print(f"{_C['d']}{'-' * 66}{_C['x']}" + (f" {_C['bold']}{title}{_C['x']}" if title else ""))


def _card(res: Dict[str, Any]) -> None:
    if res["status"] == "blocked":
        _p(f"  {_C['y']}HELD{_C['x']}  {res['reason']} {_C['d']}(guardrail){_C['x']}")
        return
    ok = res["status"] == "reproducible"
    tag = f"{_C['g']}{_C['bold']}REPRODUCIBLE{_C['x']}" if ok else f"{_C['r']}{_C['bold']}NOT REPRODUCIBLE{_C['x']}"
    _p(f"  {tag}  {_C['d']}{res['repo']}{_C['x']}")
    _kv("manifest id", res["manifest_id"][:22] + "...")
    _kv("toolchain", f"solc {res['toolchain']}")
    _kv("sources", str(res["sources"]))
    _kv("contracts", str(res["contracts"]))
    _kv("tests", f"{res['tests_passed']} passed, {res['tests_failed']} failed",
        "g" if res["tests_failed"] == 0 else "r")
    if res["reason_codes"]:
        for c, why in zip(res["reason_codes"], res["reasons"]):
            _p(f"  {_C['r']}code {c}{_C['x']}  {why}")


def cmd_build(agent: AuditLaneAgent, repo: str) -> Dict[str, Any]:
    res = agent.build(repo)
    _card(res)
    return res


def cmd_demo() -> None:
    _p(f"{_C['bold']}AuditLane{_C['x']} — a reproducible pre-audit cleanroom for the "
       f"Arbitrum Audit Program  {_C['d']}(offline demo){_C['x']}")
    _p()
    _p(f"{_C['d']}Point it at an Arbitrum repo; it produces a content-addressed evidence")
    _p(f"package a whitelisted firm opens without reconstructing the build.{_C['x']}")
    _p()

    # 1) honest repo: the deployed bytecode matches the built artifact -> reproducible
    resolver = seed_fixture_resolver(AuditLaneSettings(offline=True))
    agent = AuditLaneAgent(resolver=resolver)

    _rule("1. A clean Arbitrum repo. AuditLane builds a reproducible package.")
    res = cmd_build(agent, FIXTURE_REPO)
    _pace()

    _p()
    _rule("contract evidence (source + on-chain bytecode)")
    for s in agent.steps():
        mark = f"{_C['g']}match{_C['x']}" if s["match"] else f"{_C['r']}MISMATCH{_C['x']}"
        dep = s["deployed"] or "(none)"
        _p(f"  {_C['b']}{s['name']:<14}{_C['x']} src {_C['d']}{s['source_path']}{_C['x']}")
        _p(f"    artifact {_C['d']}{s['artifact']}...{_C['x']}  deployed {_C['d']}{dep}...{_C['x']}  {mark}")
    _pace()

    _p()
    _rule("2. Re-run the same build. The manifest id is byte-for-byte identical.")
    resolver2 = seed_fixture_resolver(AuditLaneSettings(offline=True))
    agent2 = AuditLaneAgent(resolver=resolver2)
    res2 = agent2.build(FIXTURE_REPO)
    same = res2["manifest_id"] == res["manifest_id"]
    _kv("first run", res["manifest_id"][:26] + "...")
    _kv("second run", res2["manifest_id"][:26] + "...")
    _kv("reproducible", "yes, identical id" if same else "NO — ids differ",
        "g" if same else "r")
    _pace()

    _p()
    _rule("3. A tampered deployment. AuditLane fails the package closed.")
    bad = seed_fixture_resolver(AuditLaneSettings(offline=True))
    # simulate a deployed contract whose on-chain bytecode does not match the artifact
    bad.seed("0x00000000000000000000000000000000000ca11e", "deadbeef" * 8)
    agent3 = AuditLaneAgent(resolver=bad)
    res3 = agent3.build(FIXTURE_REPO)
    _card(res3)
    _pace()

    _p()
    _rule("what the auditor receives")
    _p(f"  {_C['d']}A normalised manifest: pinned toolchain, captured test counts,")
    _p(f"  and every contract's source hash and Arbitrum Sepolia bytecode hash,")
    _p(f"  content-addressed so the same repo state always yields the same id.{_C['x']}")
    _p()
    _p(f"{_C['g']}The firm opens a build that already works. No archaeology, no wasted subsidy.{_C['x']}")


def cmd_manifest(agent: AuditLaneAgent, repo: str) -> None:
    """Print the full canonical manifest JSON for a repo (the machine-readable package)."""
    agent.build(repo)
    _p(agent.manifest_text())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="auditlane",
                                description="Reproducible pre-audit cleanroom for Arbitrum projects.")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="scan a repo and emit a reproducible pre-audit manifest")
    b.add_argument("repo", nargs="?", default=FIXTURE_REPO, help="path to the target Arbitrum repo")
    m = sub.add_parser("manifest", help="print the full canonical manifest JSON for a repo")
    m.add_argument("repo", nargs="?", default=FIXTURE_REPO)
    sub.add_parser("demo", help="run the whole hero story (build -> reproduce -> tamper -> fail closed)")
    return p


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "demo":
        cmd_demo()
    elif args.cmd == "build":
        # keyless offline default seeds the fixture; a real repo path uses the plain resolver
        if args.repo == FIXTURE_REPO:
            agent = AuditLaneAgent(resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
        else:
            agent = AuditLaneAgent()
        cmd_build(agent, args.repo)
    elif args.cmd == "manifest":
        if args.repo == FIXTURE_REPO:
            agent = AuditLaneAgent(resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
        else:
            agent = AuditLaneAgent()
        cmd_manifest(agent, args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
