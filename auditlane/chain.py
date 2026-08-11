"""Arbitrum chain adapter seam — deployed-bytecode resolution.

The pre-audit cleanroom's on-chain claim is: "the contract deployed at this Arbitrum
Sepolia address is the contract in this repo." To check that without trusting us, the
manifest carries the hash of the deployed runtime bytecode next to the hash of the
locally built artifact, and the reproducibility check fails closed if they diverge.

One interface, two backends:

  * OFFLINE (default, keyless): a deterministic in-process fixture that returns the
    same runtime bytecode a matching Arbitrum Sepolia deployment would return. It is
    seeded from the built artifact hashes so the honest case reproduces exactly and a
    tampered artifact is flagged. Not a stub: it is the executable spec of the live
    path's shape (an address maps to runtime code, absence maps to empty).

  * LIVE (gated on `AUDITLANE_RPC_URL`): calls `eth_getCode` on Arbitrum Sepolia via
    web3.py to read the real deployed runtime bytecode. Wired behind the same
    interface so nothing above this seam changes.

Read-only either way: this seam never sends a transaction and never needs a key.
Arbitrum Sepolia testnet only; never mainnet.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, Optional

from .config import AuditLaneSettings, settings


def _hash_bytecode(code: bytes) -> str:
    """Hash of runtime bytecode. Empty code (no contract at address) hashes to a
    sentinel so 'nothing deployed' is a distinct, checkable value, not a collision."""
    if not code:
        return ""
    return hashlib.sha256(code).hexdigest()


@dataclass
class Deployment:
    """The resolved on-chain state of one address, in the shape the manifest wants."""

    address: str
    deployed_bytecode_hash: str  # "" when nothing is deployed at the address


class ChainResolver:
    """The seam. `resolve()` returns the deployed bytecode hash for an Arbitrum
    Sepolia address, offline or live, with no side effects and no key."""

    def __init__(self, cfg: AuditLaneSettings | None = None) -> None:
        self.cfg = cfg or settings
        # --- offline fixture state ------------------------------------------
        # address -> runtime bytecode hash. Seeded so honest builds reproduce.
        self._fixture: Dict[str, str] = {}
        self._live = None
        if self.cfg.use_chain:
            self._live = _LiveResolver(self.cfg)

    def seed(self, address: str, bytecode_hash: str) -> None:
        """Register the deployed bytecode hash the offline fixture will return for an
        address. In a real build this is what a prior verified deployment recorded;
        for the demo/tests it lets the honest and tampered cases both be exact."""
        self._fixture[address.lower()] = bytecode_hash

    def resolve(self, address: str) -> Deployment:
        """Return the deployed runtime-bytecode hash at `address` on Arbitrum Sepolia.
        Offline: from the seeded fixture. Live: via eth_getCode. An unknown address
        resolves to an empty hash ('nothing deployed'), never an exception."""
        if self._live is not None:
            return self._live.resolve(address)
        return Deployment(address=address, deployed_bytecode_hash=self._fixture.get(address.lower(), ""))


class _LiveResolver:  # pragma: no cover - needs a live Arbitrum Sepolia RPC
    """Live Arbitrum Sepolia backend via web3.py. Instantiated only when
    AUDITLANE_RPC_URL is set. Read-only: it only calls eth_getCode."""

    def __init__(self, cfg: AuditLaneSettings) -> None:
        from web3 import Web3  # lazy import: only needed for the live path

        self.cfg = cfg
        if not cfg.rpc_url:
            raise ValueError(
                "live mode needs AUDITLANE_RPC_URL (an Arbitrum Sepolia RPC); "
                "set AUDITLANE_OFFLINE=1 for the deterministic keyless build"
            )
        self.w3 = Web3(Web3.HTTPProvider(cfg.rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"cannot reach the Arbitrum Sepolia RPC at {cfg.rpc_url}")
        # Guardrail: refuse anything that is not the Arbitrum Sepolia testnet.
        actual = self.w3.eth.chain_id
        if actual != cfg.chain_id:
            raise ValueError(
                f"connected chain id {actual} is not Arbitrum Sepolia ({cfg.chain_id}); "
                "AuditLane is testnet only and refuses to resolve against other chains"
            )

    def resolve(self, address: str) -> Deployment:
        from web3 import Web3

        code = self.w3.eth.get_code(Web3.to_checksum_address(address))
        return Deployment(address=address, deployed_bytecode_hash=_hash_bytecode(bytes(code)))
