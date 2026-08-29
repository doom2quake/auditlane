# LIMITATIONS: what is proved, what is simulated, what is not built

AuditLane is milestone 1 of an application to the Arbitrum Audit Program. This file
states plainly what exists today so no reader has to infer it. Nothing elsewhere in the
repo contradicts it.

## What is proved (tested)

- `auditlane/manifest.py` folds a repo spec into a single content-addressed manifest.
  The `manifest_id` is a pure function of the evidence: the same spec yields a
  byte-for-byte identical manifest and id, and changing any source byte changes the id.
  Ordering of sources and contracts in the repo cannot change the digest.
- The reproducibility `check` returns the seven reason codes in a **fixed order**; an
  empty list is `REPRODUCIBLE`. A deployed bytecode hash that does not match the built
  artifact is reason code 5 (`BYTECODE_MISMATCH`) and a `NOT REPRODUCIBLE` verdict. The
  suite has a test that goes red for each code when its check is removed.
- `src/BuildRegistry.sol` computes the same verdict on-chain from a package's checkable
  shape, with the identical reason codes and order, recomputes the manifest id with
  `manifestDigest`, and writes a manifest id once (`commit` reverts on a re-commit). 13
  Solidity tests pin these.
- The Python `test_check_*` cases are the exact analogues of the Solidity `test*Fails`
  cases, so a green `pytest` proves the off-chain core agrees with the on-chain
  reference on every reason code and its order. 24 Python tests, keyless and offline.

## What is simulated (a model, labelled as one)

- The offline chain adapter (`auditlane/chain.py`) is an **in-process fixture** that
  returns, for an address, the deployed runtime bytecode hash a matching Arbitrum
  Sepolia deployment would return. It is seeded from the sample repo's own built
  artifact bytes, so the honest case reproduces and a tampered artifact fails closed. It
  produces no transaction hashes and no block numbers.
- `ui/index.html` is a **browser demo** that runs the real reproducibility check over
  the bundled sample repo. It shows the real manifest fields, reason codes, and the
  `BuildRegistry` event signature, and invents no transaction hashes.

## What is NOT built, deployed, or measured (state plainly)

- **No mainnet deployment, and none planned under this grant.** All Web3 targets are
  Arbitrum Sepolia testnet only. As of today `BuildRegistry.sol` is not deployed
  anywhere; the testnet deployment and the live commit path are milestone 2, not done
  here.
- **No live-chain test.** The live bytecode path (`eth_getCode` on Arbitrum Sepolia) is
  wired behind the same interface and gated on `AUDITLANE_RPC_URL`, but the tests run the
  offline fixture; they do not hit a real Arbitrum endpoint.
- **No users.** Nobody outside this repo has run AuditLane on their own project. No
  pilot, no design partner, no waitlist.
- **No revenue** and no business model beyond the grant.
- **No audit.** No third-party security review has been performed on any of this code.
  Milestone 3 is a request to be audited through the Arbitrum Audit Program, not a claim
  that we have been.
- **No partnership with the Arbitrum Foundation or any whitelisted firm**, and no
  endorsement. This is grant-application work.
