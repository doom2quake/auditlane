# AuditLane: a reproducible pre-audit cleanroom for the Arbitrum Audit Program

**Project:** AuditLane
**Repo:** `github.com/doom2quake/auditlane` (new repository, purpose-built for this application)
**Applicant:** doom2quake builder collective
**Grant target:** Arbitrum Audit Program (AAP), Arbitrum Foundation
**Status of this document:** application draft, testnet-only, no mainnet deployment

---

## 0. What we are asking for, and what this is

We are applying to the Arbitrum Audit Program for a subsidised audit of AuditLane, a
security-tooling deliverable that produces a **reproducible pre-audit cleanroom** for
Arbitrum projects entering the AAP. The cleanroom is a small, deterministic pipeline a
project runs before it reaches a whitelisted audit firm, so the firm receives a
normalised, evidence-carrying package instead of a raw repository. The subsidised audit
hardens the cleanroom itself, because a tool that whitelisted firms and the Audit
Committee lean on has to be worth trusting.

We arrive with working, tested code, not a slide. This document points at what actually
runs in this repository.

### Grant facts we verified on an official page

Verified from the Arbitrum Foundation blog and `arbitrum.foundation` (current as of the
application date):

- The Arbitrum Audit Program is **live** and accepting applications on a rolling basis.
- It allocates **$10M in ARB** worth of grants and investments over 12 months to
  subsidise third-party smart-contract audits. The Foundation's own wording is "grants
  and investments"; it does not publish the split, so **whether a given award is a grant
  or carries an investment term is an operator decision to confirm at award time.** We
  treat the non-dilutive grant path as the default and flag the investment path as a term
  to read before signing.
- Eligible projects are early-stage-yet-to-launch, migrating from another chain, or
  already operational on Arbitrum. **Only new or significantly modified codebases**
  qualify.
- Audits are performed by firms from a **pre-approved whitelist** (including
  OpenZeppelin, Certora, Nethermind, and Trail of Bits). The subsidy compensates the
  audit firm, partially or fully, depending on scope.
- A committee (Arbitrum Foundation, Offchain Labs, and a DAO-elected technical expert)
  reviews on technical maturity, team experience, likelihood of success, and ecosystem
  alignment. The Foundation tracks **milestone progress** for approved applicants.
- Approved projects agree to keep the audited code **exclusive to Arbitrum for a set
  duration.**

Not verified, and therefore not claimed: the exact grant-versus-investment split for any
award, per-project subsidy caps, and the precise milestone-reimbursement schedule. The
public pages describe these qualitatively, not numerically. We do not invent figures for
them.

---

## 1. The problem

A project that lands audit funding still hands the auditor a mess. The repository builds
on one machine and not another, the test suite needs three undocumented environment
variables, the deployment scripts point at a stale address, and the invariants the team
believes hold live in a founder's head rather than in an executable check. The
whitelisted firm spends the first days of a fixed, subsidised engagement reconstructing a
build and guessing at intent before a single line is reviewed. That reconstruction is
paid for out of a subsidy meant to buy review, and it is not reproducible: a re-audit
after fixes starts the same archaeology again.

Who suffers: the Arbitrum Audit Program pays for it, because subsidy hours burn on setup
rather than findings. The project suffers, because a shallower review ships. The next
reviewer suffers, because nothing from the first pass is captured in a form they can
re-run. With $10M in ARB flowing through a fixed whitelist of firms on fixed engagements,
every hour of avoidable setup is subsidy that bought no security.

The gap is narrow and concrete: there is no standard, reproducible, evidence-carrying
package a project produces before the whitelisted firm starts, so the firm opens a build
that already works, a test suite that already ran with its counts captured, and a
verdict anyone can recompute.

## 2. Why Arbitrum, why now

This belongs on Arbitrum specifically, not on a generic chain.

**The verdict is checkable on-chain.** AuditLane's manifest is content-addressed, and its
reproducibility verdict is computed by a pure function whose reason codes and fixed order
are mirrored byte-for-byte in `src/BuildRegistry.sol`. A project can commit a manifest id
on Arbitrum Sepolia; anyone can recompute the same id from the published package and check
the two agree, and the commitment is write-once. That makes "this build reproduced, here
is the verdict" a public, timestamped, on-chain claim on Arbitrum, not a line in a PDF the
tool asks you to believe.

**The timing is the program.** The AAP is live now, funded for a 12-month window, routing
a fixed set of firms through rolling engagements. A tool that reduces setup waste is worth
most while that pipeline is actively running, not after it closes. The exclusivity term
(audited code stays on Arbitrum for a set duration) also lines up with a deliverable whose
whole value is Arbitrum-specific: we are not asking to subsidise chain-agnostic code that
walks to another ecosystem the next week.

## 3. Evidence we ship

We do not have users yet. What we have instead is code that runs and is tested, which is
more than the median applicant brings. Everything below is in this repository and was
reproduced in this environment.

**The cleanroom core (`auditlane/`).** `auditlane build` reads an Arbitrum repo into a
`RepoSpec` (pinned toolchain from `foundry.toml`, every `.sol` under `src/` by content
hash, each artifact's runtime bytecode hash from `out/`, the captured test counts, and an
`auditlane.deployments.json` mapping contracts to Arbitrum Sepolia addresses), resolves
each contract's deployed bytecode through the chain seam, and folds the result into a
single content-addressed manifest. The fold is pure: no I/O, no clock, no network, so the
`manifest_id` is a function of evidence and nothing else, and two runs over the same repo
state produce the identical id.

**The on-chain reference (`src/BuildRegistry.sol`).** The same reproducibility check,
with the same seven reason codes in the same fixed order, computed on-chain from a
package's checkable shape; `manifestDigest` recomputes the id from the canonical payload,
and `commit` writes it once. Verified in this environment:

- **`forge test`: 13 Solidity tests pass, 0 fail** (solc 0.8.24) on `BuildRegistry.sol`
  — every reason code, the fixed check order, the write-once commitment, and the keccak
  digest.
- **`PYTHONPATH=. pytest -q`: 24 Python tests pass, 0 fail**, keyless and offline. The
  `test_check_*` cases are the exact analogues of the Solidity `test*Fails` cases, so a
  green pytest proves the off-chain core and the on-chain reference agree on every reason
  code and its order.

**The chain seam and the agent.** The Arbitrum seam (`auditlane/chain.py`) is one
interface with two backends: an offline, keyless fixture by default (seeded from the
sample's own artifact bytes, so the honest case reproduces and a tampered artifact fails
closed) and a live `eth_getCode` path on Arbitrum Sepolia gated on `AUDITLANE_RPC_URL`
that refuses any chain id other than 421614. The build runs as a recorded action wrapped
in agent-core guardrails: the manifest write passes an `ActionLimiter`, and every step is
journalled in a `StateStore`. The agent never emits a green manifest a failing check
produced.

The independent-review discipline matters here: `docs/LIMITATIONS.md` maps, plainly, what
is proved, what is simulated, and what is not built. There is no audit, no deployment, and
no user, and the file says so.

## 4. Milestone roadmap

Four milestones. Each names a deliverable, how a reviewer verifies it without trusting us,
and what it unlocks. Dates are relative to award (T0); Web3 targets are Arbitrum Sepolia
testnet only.

**M1 — Cleanroom core and reproducible build (T0 + 4 weeks). BUILT.**
Deliverable: `auditlane build` produces a normalised package from an Arbitrum repo —
pinned toolchain, the full test suite's captured counts, and a content-addressed manifest
of every contract with its source hash and Arbitrum Sepolia deployed-bytecode hash checked
against the built artifact, plus the byte-for-byte on-chain reference `BuildRegistry.sol`.
Verify: a reviewer clones this repo, runs `PYTHONPATH=. python -m auditlane.main demo` and
`forge test`, and gets the identical manifest id and the test counts published here (24
Python, 13 Solidity). **Status: complete and green.** Unlocks: a package a whitelisted
firm can open without reconstruction, with a verdict anyone can recompute.

**M2 — Testnet deployment + on-chain commit path (T0 + 9 weeks).**
Deliverable: `BuildRegistry.sol` deployed to Arbitrum Sepolia with a published address and
explorer link, and `auditlane` extended to commit a manifest id on the live testnet
contract and read it back, with the live `eth_getCode` bytecode path pointed at the
deployed address returning real chain-tagged data. Verify: a reviewer opens the explorer
link, recomputes a committed manifest id from the published package, and confirms it
matches the on-chain commitment. Unlocks: the first end-to-end, on-chain-verifiable
reproducibility claim on Arbitrum.

**M3 — Subsidised audit of AuditLane itself, by a whitelisted firm (T0 + 16 weeks).**
Deliverable: AuditLane is submitted through the AAP application and audited by a firm from
the Arbitrum whitelist; findings are fixed and each fix is pinned by a regression test.
Verify: the published audit report and a diff showing each finding closed by a named test.
Unlocks: a security tool the Audit Committee and whitelisted firms can lean on, because it
has itself been through the pipeline.

**M4 — Auditor-facing report format and open handoff spec (T0 + 22 weeks).**
Deliverable: a documented, machine-readable pre-audit package format (build manifest,
test-count evidence, contract evidence lines, on-chain commitment) plus a short
integration note for whitelisted firms. Verify: a reviewer generates a package on a sample
Arbitrum repo and reads it against the published spec. Unlocks: reuse by any Arbitrum
project and any whitelisted firm, independent of us.

**After the grant.** The cleanroom format and the on-chain reference are open source and
self-serve; a project runs `auditlane build` with no dependency on our involvement. We
continue to maintain the format against Arbitrum toolchain changes and to fold new
evidence patterns back into the open harness as ecosystem projects use it.

## 5. Ecosystem impact

Everything durable here is open-sourced under MIT, owned by doom2quake, and
Arbitrum-specific:

- The **reproducible-build and evidence-package format** — reusable by any Arbitrum
  project entering the AAP, and readable by any whitelisted firm.
- The **on-chain manifest commitment** (`BuildRegistry.sol`) — a pattern for turning "this
  build reproduced" into a write-once, publicly recomputable claim on Arbitrum.
- The **fixed-order, fail-closed reproducibility check**, mirrored between an off-chain
  pure function and an on-chain contract, documented so other builders copy the method,
  not just the code.
- A **worked, published audit of a security tool through the AAP itself**, a concrete
  reference for other applicants on what the pipeline produces.

The AAP funds audits of many projects; AuditLane makes each of those audits start from a
better place, so the ecosystem impact compounds across the program rather than sitting in
one codebase.

## 6. Sustainability and honest limits

**What keeps it alive after the money ends.** The deliverable is a self-serve,
open-source format and a small on-chain reference, not a hosted service with a bill. A
project runs it locally with no ongoing cost to us or to them. Maintenance is folding new
evidence and toolchain patterns back into the open harness as the ecosystem uses it; that
is bounded work, not a subscription we have to fund.

**What is NOT built, deployed, or measured — stated plainly:**

- **No users.** Nobody outside this repo has run AuditLane on their own project. No pilot,
  no design partner, no waitlist.
- **No mainnet deployment, ever, in this proposal.** All Web3 targets are Arbitrum Sepolia
  testnet only. As of today `BuildRegistry.sol` is not deployed anywhere; the testnet
  deployment is milestone 2.
- **No live-chain test.** The live `eth_getCode` path is wired and gated on
  `AUDITLANE_RPC_URL`, but the test suite runs the offline fixture, not a real Arbitrum
  endpoint.
- **No revenue, no partnerships, no prior audit.** We have not been audited, are not
  partnered with any audit firm, and are not endorsed by the Arbitrum Foundation.
  Milestone M3 is a request to be audited, not a claim that we have been.
- **Test-count honesty.** 24 Python tests and 13 Solidity tests pass in this environment.
  These are the numbers we stand on.
- **Grant-versus-investment terms are unresolved.** The AAP is "grants and investments"
  and the Foundation does not publish the split. If an award carries an investment or
  token term rather than a non-dilutive grant, that is an operator decision to read and
  sign, not something this document can pre-commit.

We would rather have these caught here than in diligence.

---

## Operator actions before submission

- Confirm on the live AAP application whether the award we would receive is a
  non-dilutive grant or carries an investment/token term, and decide accordingly.
- Confirm the current application form, committee contact, and any per-project subsidy cap
  directly on the official page before applying.
- Confirm eligibility framing: AuditLane is a new codebase, which fits the "new or
  significantly modified" rule.

## Citation

```bibtex
@software{sarkar_auditlane_2026,
  author  = {Dipankar Sarkar},
  title   = {AuditLane: A Reproducible Pre-Audit Cleanroom for the Arbitrum Audit Program},
  year    = {2026},
  url     = {https://github.com/doom2quake/auditlane},
  license = {MIT}
}
```

License: MIT, held by doom2quake. Testnet only; no mainnet, no real funds.
