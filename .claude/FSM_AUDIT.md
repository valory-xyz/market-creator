# FSM Audit Report

**Scope:** `packages/valory/skills/market_creation_manager_abci`, `packages/valory/skills/market_maker_abci`, `packages/valory/contracts/fpmm`, `packages/valory/contracts/fpmm_deterministic_factory`
**Date:** 2026-03-10
**Skill:** [audit-fsm](https://github.com/valory-xyz/open-autonomy/tree/main/claude-skills/audit-fsm)

## CLI Tool Results

| Tool | Result |
|---|---|
| `autonomy analyse fsm-specs --package .../market_creation_manager_abci` | PASS |
| `autonomy analyse fsm-specs --package .../market_maker_abci` | PASS |
| `autonomy analyse docstrings` | PASS |
| `autonomy analyse handlers` | PASS (skipped `market_maker_abci` due to missing `openapi_core` — not a finding) |

## Critical Findings

### C3.1: Unused Events in Event Enum — FIXED

- **File:** `states/base.py`
- **Issue:** Four events were defined in the `Event` enum but never used in any round's `transition_function` or `end_block()`:
  - `MARKET_PROPOSAL_ROUND_TIMEOUT`
  - `MAX_PROPOSED_MARKETS_REACHED`
  - `SKIP_MARKET_PROPOSAL`
  - `DID_NOT_SEND` (was only reachable via unreachable code — see L1.1)
- **Fix applied:** Removed all four unused events from the enum. Removed `DID_NOT_SEND` from `RetrieveApprovedMarketRound` transition function, `fsm_specification.yaml`, and test parametrization.

### ~~C3.2: SyncMarketsRound Placeholder Keys~~ — FALSE POSITIVE

- **Verified:** `SyncMarketsRound.end_block()` completely overrides the base class logic without calling `super()`. The placeholder `selection_key` and `collection_key` values are never used.

## High Findings

### H2.1: Missing Final States in Composition Mapping — FIXED

- **File:** `market_maker_abci/composition.py`
- **Issue:** Two `MechInteractAbciApp` final states were not mapped in `abci_app_transition_mapping`:
  - `FinishedMarketplaceLegacyDetectedRound`
  - `FinishedMechPurchaseSubscriptionRound`
- **Fix applied:** Added both mappings (following trader repo patterns):
  - `FinishedMarketplaceLegacyDetectedRound` → `MechRequestRound`
  - `FinishedMechPurchaseSubscriptionRound` → `RandomnessTransactionSubmissionRound`
- Regenerated `market_maker_abci/fsm_specification.yaml`.

### H3.1: Unsafe Array Indexing in Contract — FIXED

- **File:** `contracts/fpmm_deterministic_factory/contract.py`
- **Issue:** Direct access to `logs[0]` without bounds check; no null check on transaction receipt.
- **Fix applied:** Added `if receipt is None: raise ValueError(...)` and `if not logs: raise ValueError(...)` guards before accessing the event data.

## Medium Findings

### M1.1: ApproveMarketsRound Multi-Element payload_key — DEFERRED

- **File:** `states/approve_markets.py:49-53`
- **Status:** Low risk. The `end_block()` override handles data manually. Requires framework investigation to determine if this is a concern.

### M1.2: RetrieveApprovedMarketRound Empty payload_key — DEFERRED

- **File:** `states/retrieve_approved_market.py:48`
- **Status:** Low risk. The `end_block()` override handles all data flow manually, making the placeholder harmless (same pattern as C3.2).

### M2.1: Unused Event Definitions — FIXED (merged into C3.1)

- Covered by C3.1 fix above.

### ~~M5.1: selection_key Type Mismatch~~ — FALSE POSITIVE

- **Verified:** The framework declares `selection_key: Union[str, Tuple[str, ...]]` and uses `isinstance()` to handle both cases correctly.

### H3.2: Missing Transaction Receipt Null Check — FIXED (merged into H3.1)

- Covered by H3.1 fix above.

### G2: Non-Cryptographic Random for Salt Nonce — DEFERRED

- **File:** `contracts/fpmm_deterministic_factory/contract.py:137,178`
- **Status:** Matches Omen's reference implementation (`# nosec` annotated). Acceptable as-is.

## Low Findings

### L1.1: Unreachable Duplicate None Check — FIXED

- **File:** `states/retrieve_approved_market.py`
- **Fix applied:** Removed the unreachable duplicate `if self.keeper_payload is None:` check and the dead `DID_NOT_SEND` event path.

### L1.2: Hardcoded Retry Always Hits MAX_RETRIES — FIXED

- **File:** `behaviours/retrieve_approved_market.py`
- **Fix applied:** Removed the dead retry logic (`retries = 3` always hit `MAX_RETRIES = 3`). On HTTP error, the behaviour now returns `ERROR_PAYLOAD` directly. Removed unused `MAX_RETRIES` import.

### G1: Improper Logging Format — FIXED

- **File:** `contracts/fpmm/contract.py`
- **Fix applied:** Changed `_logger.error("...", str(e))` to `_logger.error(f"...: {e}")`.

## Test Findings

No findings. All T1-T6 checks passed.

## Summary

| Severity | Found | Fixed | False Positive | Deferred |
|----------|-------|-------|----------------|----------|
| Critical | 2 | 1 | 1 | 0 |
| High | 2 | 2 | 0 | 0 |
| Medium | 6 | 2 | 1 | 3 |
| Low | 3 | 3 | 0 | 0 |
| Test | 0 | 0 | 0 | 0 |

## Verification

All fixes verified:
- `autonomy analyse fsm-specs` — PASS for both skills
- `autonomy analyse docstrings` — PASS
- Python imports — OK for both `MarketCreationManagerAbciApp` and `MarketCreatorAbciApp`

## Notes

- **False positives excluded:** Standard `ROUND_TIMEOUT` event usage follows library skill conventions and is not flagged.
- **Scope limitation:** Third-party synced packages (e.g., `mech_interact_abci`, `transaction_settlement_abci`) were not audited beyond their composition interfaces.
- **Deferred items** (M1.1, M1.2, G2) are low-risk patterns where custom `end_block()` overrides bypass the framework defaults, or where the implementation intentionally matches an external reference (Omen).
