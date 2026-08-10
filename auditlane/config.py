"""AuditLane configuration — extends agent-core's BaseSettings.

The load-bearing artifact is the **pre-audit cleanroom manifest**: a deterministic,
content-addressed record a project produces before it reaches a whitelisted Arbitrum
audit firm. `auditlane build` reads a target repo, runs a pinned toolchain, captures
the test-suite counts, and writes a manifest of every contract, its source hash, and
its on-chain deployment (address + bytecode hash) so the firm opens a build that
already works instead of reconstructing one.

Keyless by default: with no `AUDITLANE_RPC_URL` set, the chain seam falls back to a
deterministic in-process fixture that mirrors an Arbitrum Sepolia deployment, so the
whole build runs without an RPC, a deployed contract, or a funded key. The live path
(reading deployed bytecode from Arbitrum Sepolia) is gated on env credentials.

Arbitrum Sepolia testnet only; never mainnet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_core import BaseSettings, env_bool, env_int, env_str


@dataclass(frozen=True)
class AuditLaneSettings(BaseSettings):
    env_prefix: str = "AUDITLANE"
    app_name: str = "auditlane"

    # --- Arbitrum chain seam (live bytecode resolution gated on these) --------
    rpc_url: str = field(default_factory=lambda: env_str("AUDITLANE_RPC_URL"))
    chain_id: int = field(default_factory=lambda: env_int("AUDITLANE_CHAIN_ID", 421614))  # Arbitrum Sepolia

    offline: bool = field(default_factory=lambda: env_bool("AUDITLANE_OFFLINE", False))

    # --- manifest schema pin --------------------------------------------------
    # The manifest format version. A reviewer re-running an old build gets the same
    # schema string, so a format change is visible rather than silent.
    manifest_version: str = "auditlane/1"

    @property
    def use_chain(self) -> bool:
        """True when a live Arbitrum RPC is configured (else the deterministic
        in-process fixture stands in for on-chain bytecode resolution)."""
        return bool(self.rpc_url) and not self.offline


settings = AuditLaneSettings()
