"""AuditLane agent — the cleanroom builder, wrapped in agent-core guardrails + audit.

The agent runs the pre-audit build as a recorded action: it scans the target repo,
resolves each contract's on-chain deployment through the Arbitrum seam, folds the
result into a content-addressed manifest, and journals every step (scan -> resolve ->
reproducibility check -> manifest) in the StateStore so the UI can replay the build's
activity log. The manifest write passes agent-core's ActionLimiter, so a runaway build
loop is rate-limited like any other outbound action.

The agent NEVER emits a green manifest the reproducibility check did not clear. That is
the trust primitive: an evidence package is only as good as the checks it survived, and
every failing check is recorded, not swallowed.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agent_core import ActionLimiter, ActionPolicy, StateStore, signature_of

from .chain import ChainResolver
from .config import settings
from .manifest import Manifest, manifest_json, reason_for
from .scanner import scan
from .manifest import build as _fold


_limiter = ActionLimiter(ActionPolicy.from_env("AUDITLANE"))


class AuditLaneAgent:
    def __init__(self, resolver: ChainResolver | None = None) -> None:
        self.resolver = resolver or ChainResolver()
        self._last: Manifest | None = None

    def build(self, repo_path: str) -> Dict[str, Any]:
        """Run the cleanroom build over `repo_path`. Returns the build card: verdict,
        reason codes, test counts, and the manifest id."""
        store = StateStore.create(settings)
        run_id = store.start_run(trigger={"build": {"repo": repo_path}})

        # 1) scan the repo into a spec (sources, toolchain, tests, on-chain resolution)
        spec = scan(repo_path, resolver=self.resolver)
        store.record_guardrail(
            run_id, "SCAN", "ok",
            f"sources={len(spec.sources)} contracts={len(spec.contracts)} suites={len(spec.tests)}",
        )

        # 2) guardrail: is the agent allowed to emit a manifest this cycle?
        allowed, why = _limiter.check(run_id, "manifest")
        if not allowed:
            store.record_guardrail(run_id, "ACTION_LIMITER", "blocked", f"manifest: {why}")
            store.set_status(run_id, "blocked")
            return {"status": "blocked", "reason": why, "run_id": run_id}

        # 3) fold into a content-addressed manifest + run the reproducibility check
        manifest = _fold(spec)
        self._last = manifest
        codes = manifest.reason_codes
        if codes:
            for c in codes:
                store.record_guardrail(run_id, "REPRODUCIBILITY", "fail", f"code={c} {reason_for(c)}")
        else:
            store.record_guardrail(run_id, "REPRODUCIBILITY", "pass", "reproducible")

        total_pass = sum(t.passed for t in spec.tests)
        total_fail = sum(t.failed for t in spec.tests)

        store.set_data(run_id, "manifest", {
            "id": manifest.manifest_id, "verdict": int(manifest.verdict),
            "reason_codes": codes,
        })
        store.detect_recurrence(run_id, signature_of("manifest", manifest.manifest_id))
        store.set_status(run_id, "reproducible" if not codes else "not_reproducible")

        return {
            "status": "reproducible" if not codes else "not_reproducible",
            "run_id": run_id,
            "repo": manifest.repo,
            "manifest_id": manifest.manifest_id,
            "verdict": int(manifest.verdict),
            "reason_codes": codes,
            "reasons": [reason_for(c) for c in codes],
            "sources": len(manifest.sources),
            "contracts": len(manifest.contracts),
            "tests_passed": total_pass,
            "tests_failed": total_fail,
            "toolchain": manifest.toolchain.solc,
        }

    def manifest(self) -> Manifest | None:
        return self._last

    def manifest_text(self) -> str:
        return manifest_json(self._last) if self._last else ""

    def steps(self) -> List[Dict[str, Any]]:
        """The manifest's contract-level evidence lines, for the UI artifacts panel."""
        if not self._last:
            return []
        out: List[Dict[str, Any]] = []
        for c in self._last.contracts:
            match = (
                c.deployed_bytecode_hash is not None
                and c.deployed_bytecode_hash == c.artifact_bytecode_hash
            )
            out.append({
                "name": c.name,
                "source_path": c.source_path,
                "artifact": (c.artifact_bytecode_hash or "")[:16],
                "deployed": (c.deployed_bytecode_hash or "")[:16] if c.deployed_bytecode_hash else None,
                "address": c.address,
                "match": match,
            })
        return out
