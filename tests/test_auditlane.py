"""AuditLane tests: the Python reproducibility check mirrors the Solidity BuildRegistry
byte-for-byte, the manifest is content-addressed and deterministic, the repo scanner
reads a real fixture repo, and the agent records the build with fail-closed guardrails.

The `test_check_*` cases below are the exact analogues of the `test*Fails` cases in
`test/BuildRegistry.t.sol`, so a green pytest proves the Python core agrees with the
on-chain reference on every reason code and their fixed order. Keyless and offline.
"""

from pathlib import Path

from auditlane.agent import AuditLaneAgent
from auditlane.chain import ChainResolver, Deployment
from auditlane.config import AuditLaneSettings
from auditlane.fixtures import FIXTURE_REPO, seed_fixture_resolver
from auditlane.manifest import (
    BYTECODE_MISMATCH,
    BUILD_FAILED,
    Contract,
    MISSING_DEPLOYMENT,
    NO_TOOLCHAIN_PIN,
    REPRODUCIBLE,
    RepoSpec,
    SOURCE_HASH_MISMATCH,
    SourceFile,
    TESTS_FAILED,
    TestResult,
    Toolchain,
    Verdict,
    build,
    check,
    manifest_json,
    reason_for,
)
from auditlane.scanner import build_manifest, scan


AH = "a" * 64  # a fixed artifact bytecode hash
OTHER = "b" * 64


def _pinned() -> Toolchain:
    return Toolchain(solc="0.8.24", evm_version="cancun", optimizer_runs=200, framework="foundry")


def _good_spec() -> RepoSpec:
    src = SourceFile(path="src/SampleVault.sol", sha256="c" * 64, size=100)
    return RepoSpec(
        name="sample",
        toolchain=_pinned(),
        sources=[src],
        tests=[TestResult(suite="forge test", passed=13, failed=0, command="forge test")],
        contracts=[Contract(
            name="SampleVault", source_path="src/SampleVault.sol",
            artifact_bytecode_hash=AH, address="0xabc", deployed_bytecode_hash=AH,
        )],
    )


# ===================== reproducibility check (mirror BuildRegistry.t.sol) =====================
def test_check_reproducible_package_passes():
    assert check(_good_spec()) == []


def test_check_unpinned_toolchain_fails():
    spec = _good_spec()
    spec = RepoSpec(spec.name, Toolchain(solc="^0.8.24"), spec.sources, spec.tests, spec.contracts)
    assert NO_TOOLCHAIN_PIN in check(spec)


def test_check_no_sources_fails():
    spec = _good_spec()
    spec = RepoSpec(spec.name, spec.toolchain, [], spec.tests, spec.contracts)
    codes = check(spec)
    assert BUILD_FAILED in codes


def test_check_tests_failed_fails():
    spec = _good_spec()
    bad = [TestResult(suite="forge test", passed=12, failed=1, command="forge test")]
    spec = RepoSpec(spec.name, spec.toolchain, spec.sources, bad, spec.contracts)
    assert TESTS_FAILED in check(spec)


def test_check_zero_tests_fails():
    spec = _good_spec()
    spec = RepoSpec(spec.name, spec.toolchain, spec.sources, [], spec.contracts)
    assert TESTS_FAILED in check(spec)


def test_check_missing_source_fails():
    spec = _good_spec()
    c = spec.contracts[0]
    bad = Contract(c.name, "src/Ghost.sol", c.artifact_bytecode_hash, c.address, c.deployed_bytecode_hash)
    spec = RepoSpec(spec.name, spec.toolchain, spec.sources, spec.tests, [bad])
    assert SOURCE_HASH_MISMATCH in check(spec)


def test_check_missing_deployment_fails():
    spec = _good_spec()
    c = spec.contracts[0]
    bad = Contract(c.name, c.source_path, c.artifact_bytecode_hash, None, None)
    spec = RepoSpec(spec.name, spec.toolchain, spec.sources, spec.tests, [bad])
    assert MISSING_DEPLOYMENT in check(spec)


def test_check_bytecode_mismatch_fails():
    spec = _good_spec()
    c = spec.contracts[0]
    bad = Contract(c.name, c.source_path, AH, c.address, OTHER)
    spec = RepoSpec(spec.name, spec.toolchain, spec.sources, spec.tests, [bad])
    assert BYTECODE_MISMATCH in check(spec)


def test_check_order_first_code_is_toolchain():
    # trips toolchain (1), tests (3), and bytecode (5); the earliest code must lead.
    c = _good_spec().contracts[0]
    bad_c = Contract(c.name, c.source_path, AH, c.address, OTHER)
    spec = RepoSpec(
        "sample", Toolchain(solc="^0.8"), _good_spec().sources,
        [TestResult("forge test", 0, 1, "forge test")], [bad_c],
    )
    codes = check(spec)
    assert codes[0] == NO_TOOLCHAIN_PIN


def test_reason_strings():
    assert reason_for(BYTECODE_MISMATCH) == "deployed bytecode does not match the built artifact"
    assert reason_for(REPRODUCIBLE) == "reproducible"


# ===================== manifest is content-addressed and deterministic =====================
def test_manifest_id_is_deterministic():
    m1 = build(_good_spec())
    m2 = build(_good_spec())
    assert m1.manifest_id == m2.manifest_id
    assert m1.manifest_id.startswith("0x")


def test_manifest_verdict_reproducible():
    m = build(_good_spec())
    assert m.verdict == Verdict.OK and m.reason_codes == []


def test_manifest_id_changes_when_source_changes():
    m1 = build(_good_spec())
    spec = _good_spec()
    tampered = SourceFile(path="src/SampleVault.sol", sha256="f" * 64, size=100)
    spec = RepoSpec(spec.name, spec.toolchain, [tampered], spec.tests, spec.contracts)
    m2 = build(spec)
    assert m1.manifest_id != m2.manifest_id


def test_manifest_json_is_stable():
    m = build(_good_spec())
    assert manifest_json(m) == manifest_json(build(_good_spec()))


def test_manifest_id_independent_of_source_order():
    a = SourceFile("src/A.sol", "1" * 64, 1)
    b = SourceFile("src/B.sol", "2" * 64, 2)
    spec1 = RepoSpec("r", _pinned(), [a, b],
                     [TestResult("forge test", 1, 0, "forge test")], [])
    spec2 = RepoSpec("r", _pinned(), [b, a],
                     [TestResult("forge test", 1, 0, "forge test")], [])
    assert build(spec1).manifest_id == build(spec2).manifest_id


# ===================== chain seam (offline resolver) =====================
def test_resolver_unknown_address_is_empty():
    r = ChainResolver(AuditLaneSettings(offline=True))
    dep = r.resolve("0xdeadbeef")
    assert isinstance(dep, Deployment) and dep.deployed_bytecode_hash == ""


def test_resolver_seed_roundtrips_case_insensitively():
    r = ChainResolver(AuditLaneSettings(offline=True))
    r.seed("0xABCDEF", "hash123")
    assert r.resolve("0xabcdef").deployed_bytecode_hash == "hash123"


# ===================== scanner reads the real fixture repo =====================
def test_scan_reads_fixture_repo():
    spec = scan(FIXTURE_REPO, resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
    assert spec.name == "sample-vault"
    assert spec.toolchain.solc == "0.8.24"
    assert spec.toolchain.is_pinned
    assert any(s.path.endswith("SampleVault.sol") for s in spec.sources)
    assert spec.tests and spec.tests[0].passed == 13
    assert spec.contracts and spec.contracts[0].name == "SampleVault"


def test_fixture_build_is_reproducible():
    m = build_manifest(FIXTURE_REPO, resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
    # honest case: deployed bytecode hash == built artifact hash -> reproducible
    assert m.verdict == Verdict.OK
    assert m.reason_codes == []
    c = m.contracts[0]
    assert c.deployed_bytecode_hash == c.artifact_bytecode_hash


def test_fixture_tampered_deployment_fails_closed():
    # a resolver that returns the WRONG deployed bytecode for the sample's address
    bad = ChainResolver(AuditLaneSettings(offline=True))
    bad.seed("0x00000000000000000000000000000000000ca11e", "dead" * 16)
    m = build_manifest(FIXTURE_REPO, resolver=bad)
    assert m.verdict == Verdict.NOT_REPRODUCIBLE
    assert BYTECODE_MISMATCH in m.reason_codes


# ===================== agent records the build with guardrails =====================
def test_agent_build_reproducible_and_recorded():
    agent = AuditLaneAgent(resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
    res = agent.build(FIXTURE_REPO)
    assert res["status"] == "reproducible"
    assert res["reason_codes"] == []
    assert res["tests_passed"] == 13 and res["tests_failed"] == 0
    assert res["manifest_id"].startswith("0x")
    assert res["contracts"] == 1


def test_agent_build_tampered_is_not_reproducible():
    bad = ChainResolver(AuditLaneSettings(offline=True))
    bad.seed("0x00000000000000000000000000000000000ca11e", "dead" * 16)
    agent = AuditLaneAgent(resolver=bad)
    res = agent.build(FIXTURE_REPO)
    assert res["status"] == "not_reproducible"
    assert BYTECODE_MISMATCH in res["reason_codes"]


def test_agent_steps_expose_contract_evidence():
    agent = AuditLaneAgent(resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
    agent.build(FIXTURE_REPO)
    steps = agent.steps()
    assert steps and steps[0]["name"] == "SampleVault"
    assert steps[0]["match"] is True
    assert steps[0]["address"] == "0x00000000000000000000000000000000000ca11e"


def test_agent_manifest_text_is_json():
    agent = AuditLaneAgent(resolver=seed_fixture_resolver(AuditLaneSettings(offline=True)))
    agent.build(FIXTURE_REPO)
    txt = agent.manifest_text()
    assert '"version": "auditlane/1"' in txt
    assert '"manifest_id"' in txt
