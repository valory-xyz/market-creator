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

### C3.1: Unused Events in Event Enum

- **File:** `states/base.py:55,64`
- **Issue:** Two events are defined in the `Event` enum but never appear as keys in any round's `transition_function`:
  ```python
  MAX_PROPOSED_MARKETS_REACHED = "max_markets_reached"
  SKIP_MARKET_PROPOSAL = "skip_market_proposal"
  ```
- **Risk:** If any `end_block()` were to return these events, the transition would silently fail and hang the round.
- **Fix:** Remove these events if they are truly unused, or add corresponding transitions to the appropriate rounds.

### C3.2: SyncMarketsRound Placeholder Keys

- **File:** `states/sync_markets.py:50-51`
- **Issue:** `SyncMarketsRound` extends `CollectSameUntilThresholdRound` but has empty placeholder values:
  ```python
  selection_key: Tuple[str, ...] = ()  # TODO placeholder
  collection_key = ""  # TODO placeholder
  ```
- **Risk:** The round's collection mechanism relies on these keys. Empty values mean the framework's automatic data collection does not store results under meaningful DB keys.
- **Fix:** Define proper `selection_key` and `collection_key` values matching the `SynchronizedData` properties, or verify that the custom `end_block()` handles data storage manually (bypassing the framework's default).

## High Findings

### H2.1: Missing Final States in Composition Mapping

- **File:** `market_maker_abci/composition.py:51-72`
- **Issue:** Two `MechInteractAbciApp` final states are not mapped in `abci_app_transition_mapping`:
  - `FinishedMarketplaceLegacyDetectedRound`
  - `FinishedMechPurchaseSubscriptionRound`
- **Risk:** If the FSM reaches these states, there is no transition target defined, potentially causing the service to hang.
- **Fix:** Add entries to the mapping:
  ```python
  MechFinalStates.FinishedMarketplaceLegacyDetectedRound: MechRequestStates.MechRequestRound,
  MechFinalStates.FinishedMechPurchaseSubscriptionRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
  ```
  Verify the correct targets based on business logic.

### H3.1: Unsafe Array Indexing in Contract

- **File:** `contracts/fpmm_deterministic_factory/contract.py:251`
- **Issue:** Direct access to `logs[0]` without bounds check:
  ```python
  logs = contract.events.FixedProductMarketMakerCreation().process_receipt(receipt)
  event = logs[0]  # No bounds check
  ```
- **Risk:** `IndexError` crash if the receipt contains no matching events.
- **Fix:**
  ```python
  if not logs:
      raise ValueError(f"No FixedProductMarketMakerCreation events found in tx {tx_hash}")
  event = logs[0]
  ```

## Medium Findings

### M1.1: ApproveMarketsRound Multi-Element payload_key

- **File:** `states/approve_markets.py:49-53`
- **Issue:** `payload_key` is a 3-element tuple for an `OnlyKeeperSendsRound`. Verify the framework correctly handles multi-element `payload_key` tuples.
  ```python
  payload_key = (
      get_name(SynchronizedData.approved_markets_data),
      get_name(SynchronizedData.approved_markets_count),
      get_name(SynchronizedData.approved_markets_timestamp),
  )
  ```

### M1.2: RetrieveApprovedMarketRound Empty payload_key

- **File:** `states/retrieve_approved_market.py:48`
- **Issue:** Empty string placeholder for `payload_key`:
  ```python
  payload_key = ""  # TODO placeholder
  ```
- **Fix:** Define the proper key or document why manual handling in `end_block()` is required.

### M2.1: Unused Event Definitions

- **File:** `states/base.py:52,55,64`
- **Issue:** Three events defined but never used in `transition_function` or returned from `end_block()`:
  ```python
  MARKET_PROPOSAL_ROUND_TIMEOUT = "market_proposal_round_timeout"
  MAX_PROPOSED_MARKETS_REACHED = "max_markets_reached"
  SKIP_MARKET_PROPOSAL = "skip_market_proposal"
  ```
- **Fix:** Remove if truly unused, or implement corresponding logic.

### M5.1: selection_key Type Mismatch (Multiple Rounds)

- **Files:**
  - `states/select_keeper.py:44`
  - `states/collect_proposed_markets.py:52`
  - `states/get_pending_questions.py:49`
- **Issue:** `selection_key` is assigned a bare string instead of a tuple. `CollectSameUntilThresholdRound` expects `Tuple[str, ...]`:
  ```python
  # Current (bare string):
  selection_key = get_name(SynchronizedData.most_voted_keeper_address)

  # Expected (tuple):
  selection_key = (get_name(SynchronizedData.most_voted_keeper_address),)
  ```
- **Note:** Verify whether the framework coerces strings to tuples internally. If it does, this is cosmetic; if not, the data extraction may silently fail.

### H3.2: Missing Transaction Receipt Null Check

- **File:** `contracts/fpmm_deterministic_factory/contract.py:247`
- **Issue:** No null check on `get_transaction_receipt()` result before calling `.process_receipt()`.
- **Fix:** Add `if receipt is None: raise ValueError(...)` before processing.

### G2: Non-Cryptographic Random for Salt Nonce

- **File:** `contracts/fpmm_deterministic_factory/contract.py:137,178`
- **Issue:** Uses `random.randint(0, 1000000)` (marked `# nosec`) for salt nonce. Low entropy (~20 bits).
- **Risk:** Predictable nonces in a blockchain context. Acceptable if matching Omen's reference implementation.
- **Fix:** Consider `secrets.randbelow()` or document the security rationale.

## Low Findings

### L1.1: Unreachable Duplicate None Check

- **File:** `states/retrieve_approved_market.py:60-65`
- **Issue:** Duplicate `if self.keeper_payload is None:` check — the second is unreachable:
  ```python
  if self.keeper_payload is None:
      return None

  # Keeper did not send
  if self.keeper_payload is None:  # pragma: no cover
      return self.synchronized_data, Event.DID_NOT_SEND
  ```
- **Fix:** Remove the second check. If `DID_NOT_SEND` is a valid state, differentiate it from the first check.

### L1.2: Hardcoded Retry Always Hits MAX_RETRIES

- **File:** `behaviours/retrieve_approved_market.py:115`
- **Issue:** `retries = 3` is hardcoded and immediately compared to `MAX_RETRIES = 3`, so `if retries >= MAX_RETRIES:` is always True:
  ```python
  retries = 3  # TODO: Make params
  if retries >= MAX_RETRIES:
  ```
- **Fix:** Implement actual retry tracking or remove the dead logic.

### G1: Improper Logging Format

- **File:** `contracts/fpmm/contract.py:204`
- **Issue:** Logger call passes exception as a separate argument instead of formatting:
  ```python
  _logger.error("An exception occurred in get_markets_with_funds():", str(e))
  ```
- **Fix:**
  ```python
  _logger.error(f"An exception occurred in get_markets_with_funds(): {e}")
  ```

## Test Findings

No findings. All T1-T6 checks passed:
- T1: No `@classmethod @pytest.fixture` anti-pattern
- T2: Correct base test classes for round types
- T3: All required test class attributes set
- T4: `mock_a2a_transaction()` properly used
- T5: All round events have test coverage
- T6: No `_MetaPayload.registry` corruption

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 2 |
| Medium | 6 |
| Low | 3 |
| Test | 0 |

## Notes

- **False positives excluded:** Standard `ROUND_TIMEOUT` event usage follows library skill conventions and is not flagged.
- **Scope limitation:** Third-party synced packages (e.g., `mech_interact_abci`, `transaction_settlement_abci`) were not audited beyond their composition interfaces.
- **H2.1 requires verification:** The two missing final states (`FinishedMarketplaceLegacyDetectedRound`, `FinishedMechPurchaseSubscriptionRound`) may have been added to `MechInteractAbciApp` after the composition was written. Confirm whether these states are reachable in the current Mech version before fixing.
- **M5.1 requires verification:** Check if `CollectSameUntilThresholdRound` coerces bare strings to tuples internally. If so, the finding is cosmetic.
