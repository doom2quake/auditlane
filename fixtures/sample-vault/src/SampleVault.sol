// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title SampleVault — an on-chain commitment to a reproducible pre-audit package
/// @author Dipankar Sarkar
/// @notice AuditLane folds an Arbitrum repo into a content-addressed manifest: a
///         pinned toolchain, captured test counts, and every contract's source hash
///         and deployed-bytecode hash. This contract is the on-chain side of that
///         package. `manifestDigest` recomputes the manifest id from its fields with
///         the SAME field order and canonical joining as the off-chain
///         `auditlane.manifest`, so a project can COMMIT a manifest id on Arbitrum
///         Sepolia and anyone can recompute it from the published package and check
///         the two agree. The reproducibility verdict is likewise a pure, deterministic
///         function of the package, so a firm never has to trust our word for it — the
///         reason codes and their fixed order are the same in Solidity and in Python.
contract SampleVault {
    // Reproducibility reason codes. 0 == REPRODUCIBLE. Stable across the Solidity and
    // Python implementations (auditlane/manifest.py).
    uint16 internal constant REPRODUCIBLE          = 0;
    uint16 internal constant NO_TOOLCHAIN_PIN      = 1;
    uint16 internal constant BUILD_FAILED          = 2;
    uint16 internal constant TESTS_FAILED          = 3;
    uint16 internal constant SOURCE_HASH_MISMATCH  = 4;
    uint16 internal constant BYTECODE_MISMATCH     = 5;
    uint16 internal constant MISSING_DEPLOYMENT    = 6;

    /// @notice A single contract entry in a package.
    struct ContractEntry {
        bytes32 artifactBytecodeHash;   // hash of the locally built runtime bytecode
        bytes32 deployedBytecodeHash;   // hash of the on-chain runtime bytecode (0 if none)
        bool    hasDeployment;          // false when nothing is deployed for this entry
        bool    sourcePresent;          // false when the entry's source is missing from the package
    }

    /// @notice A whole package's checkable shape (the fields the verdict depends on).
    struct Package {
        bool toolchainPinned;   // an exact compiler version, not a caret range
        bool hasSources;        // at least one source file was captured
        uint256 testsPassed;    // total passing across declared suites
        uint256 testsFailed;    // total failing across declared suites
        ContractEntry[] contracts;
    }

    address public owner;
    // manifestId -> committer. A committed manifest is a public, timestamped claim.
    mapping(bytes32 => address) public committedBy;
    mapping(bytes32 => uint256) public committedAt;

    event ManifestCommitted(bytes32 indexed manifestId, address indexed by, uint16 verdict);

    error AlreadyCommitted(bytes32 manifestId);

    constructor() {
        owner = msg.sender;
    }

    /// @notice Deterministic reproducibility check. Returns (ok, firstCode). The order
    ///         of checks is FIXED and identical to auditlane/manifest.check, so the
    ///         returned first-failing code is stable and matches the off-chain verdict.
    function check(Package memory p) public pure returns (bool ok, uint16 code) {
        if (!p.toolchainPinned) return (false, NO_TOOLCHAIN_PIN);
        if (!p.hasSources) return (false, BUILD_FAILED);
        if (p.testsFailed > 0 || p.testsPassed == 0) return (false, TESTS_FAILED);
        for (uint256 i = 0; i < p.contracts.length; i++) {
            if (!p.contracts[i].sourcePresent) return (false, SOURCE_HASH_MISMATCH);
        }
        for (uint256 i = 0; i < p.contracts.length; i++) {
            if (!p.contracts[i].hasDeployment) return (false, MISSING_DEPLOYMENT);
        }
        for (uint256 i = 0; i < p.contracts.length; i++) {
            if (p.contracts[i].deployedBytecodeHash != p.contracts[i].artifactBytecodeHash) {
                return (false, BYTECODE_MISMATCH);
            }
        }
        return (true, REPRODUCIBLE);
    }

    /// @notice Recompute a manifest's content-addressed id from a canonical payload.
    ///         The caller passes the exact canonical payload the off-chain builder
    ///         hashed (auditlane/manifest._canonical_payload). This contract commits to
    ///         the id, so a published package can be checked against the on-chain claim.
    function manifestDigest(bytes memory canonicalPayload) public pure returns (bytes32) {
        return keccak256(canonicalPayload);
    }

    /// @notice Commit a manifest id on-chain with its computed verdict. A commitment is
    ///         write-once: re-committing the same id reverts, so a package's claim is
    ///         immutable once made.
    function commit(bytes32 manifestId, Package memory p) external returns (uint16 code) {
        if (committedAt[manifestId] != 0) revert AlreadyCommitted(manifestId);
        (bool ok, uint16 c) = check(p);
        committedBy[manifestId] = msg.sender;
        committedAt[manifestId] = block.timestamp;
        emit ManifestCommitted(manifestId, msg.sender, ok ? REPRODUCIBLE : c);
        return ok ? REPRODUCIBLE : c;
    }

    function reasonFor(uint16 code) public pure returns (string memory) {
        if (code == NO_TOOLCHAIN_PIN) return "toolchain is not pinned (no exact solc/rust version)";
        if (code == BUILD_FAILED) return "clean build did not succeed";
        if (code == TESTS_FAILED) return "declared test suite did not pass";
        if (code == SOURCE_HASH_MISMATCH) return "a source file hash does not match its manifest entry";
        if (code == BYTECODE_MISMATCH) return "deployed bytecode does not match the built artifact";
        if (code == MISSING_DEPLOYMENT) return "a manifest contract has no resolved on-chain deployment";
        return "reproducible";
    }
}
