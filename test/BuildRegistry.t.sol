// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {BuildRegistry} from "../src/BuildRegistry.sol";

/// Minimal inline Vm cheatcode interface (no forge-std dependency).
interface Vm {
    function expectPartialRevert(bytes4 selector) external;
    function prank(address) external;
    function expectEmit(bool, bool, bool, bool) external;
}

/// Tests that pin the M1 reproducibility verdict: the on-chain check agrees with the
/// off-chain (Python) manifest check on every reason code, in the same fixed order,
/// and a committed manifest id is write-once. The verdict codes here are the exact
/// analogues of the test_check_* cases in tests/test_auditlane.py, so a green forge run
/// proves the Solidity and Python implementations agree byte-for-byte on the verdict.
contract BuildRegistryTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    BuildRegistry reg;

    bytes32 constant AH = keccak256("artifact-bytecode");
    bytes32 constant OTHER = keccak256("other-bytecode");

    function setUp() public {
        reg = new BuildRegistry();
    }

    // --- helpers ------------------------------------------------------------
    function _entry(bytes32 dep, bool hasDep, bool srcPresent)
        internal
        pure
        returns (BuildRegistry.ContractEntry memory e)
    {
        e.artifactBytecodeHash = AH;
        e.deployedBytecodeHash = dep;
        e.hasDeployment = hasDep;
        e.sourcePresent = srcPresent;
    }

    function _goodPackage() internal pure returns (BuildRegistry.Package memory p) {
        p.toolchainPinned = true;
        p.hasSources = true;
        p.testsPassed = 22;
        p.testsFailed = 0;
        p.contracts = new BuildRegistry.ContractEntry[](1);
        // deployed bytecode == artifact bytecode -> match
        p.contracts[0] = _entry(AH, true, true);
    }

    // --- the reproducible case ---------------------------------------------
    function testReproduciblePackagePasses() public view {
        (bool ok, uint16 code) = reg.check(_goodPackage());
        assertTrue(ok);
        assertEq(uint256(code), 0);
    }

    // --- each failing code, in the fixed check order ------------------------
    function testUnpinnedToolchainFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.toolchainPinned = false;
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 1);
    }

    function testNoSourcesFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.hasSources = false;
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 2);
    }

    function testTestsFailedFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.testsFailed = 1;
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 3);
    }

    function testZeroTestsFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.testsPassed = 0;
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 3);
    }

    function testMissingSourceFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.contracts[0] = _entry(AH, true, false);
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 4);
    }

    function testMissingDeploymentFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.contracts[0] = _entry(bytes32(0), false, true);
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 6);
    }

    function testBytecodeMismatchFails() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.contracts[0] = _entry(OTHER, true, true);
        (bool ok, uint16 code) = reg.check(p);
        assertTrue(!ok);
        assertEq(uint256(code), 5);
    }

    // --- check order is stable: earliest failing code wins ------------------
    function testCheckOrderIsStable() public view {
        BuildRegistry.Package memory p = _goodPackage();
        p.toolchainPinned = false; // code 1
        p.testsFailed = 1;         // code 3
        p.contracts[0] = _entry(OTHER, false, false); // codes 4/5/6
        (, uint16 code) = reg.check(p);
        assertEq(uint256(code), 1); // toolchain checked first
    }

    // --- commitment is write-once ------------------------------------------
    function testCommitRecordsVerdict() public {
        bytes32 id = keccak256("manifest-1");
        uint16 code = reg.commit(id, _goodPackage());
        assertEq(uint256(code), 0);
        assertEq(reg.committedBy(id), address(this));
        assertTrue(reg.committedAt(id) != 0);
    }

    function testCommitTwiceReverts() public {
        bytes32 id = keccak256("manifest-2");
        reg.commit(id, _goodPackage());
        vm.expectPartialRevert(BuildRegistry.AlreadyCommitted.selector);
        reg.commit(id, _goodPackage());
    }

    // --- digest is deterministic -------------------------------------------
    function testManifestDigestIsKeccak() public view {
        bytes memory payload = bytes("auditlane/1\nsample");
        assertEq(reg.manifestDigest(payload), keccak256(payload));
    }

    function testReasonStrings() public view {
        assertEq(
            keccak256(bytes(reg.reasonFor(5))),
            keccak256(bytes("deployed bytecode does not match the built artifact"))
        );
        assertEq(keccak256(bytes(reg.reasonFor(0))), keccak256(bytes("reproducible")));
    }

    // --- tiny asserts (no forge-std) ---------------------------------------
    function assertTrue(bool c) internal pure {
        require(c, "assertTrue");
    }

    function assertEq(uint256 a, uint256 b) internal pure {
        require(a == b, "assertEq");
    }

    function assertEq(bytes32 a, bytes32 b) internal pure {
        require(a == b, "assertEq32");
    }

    function assertEq(address a, address b) internal pure {
        require(a == b, "assertEqAddr");
    }
}
