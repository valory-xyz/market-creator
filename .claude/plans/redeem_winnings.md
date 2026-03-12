# Plan: Add RedeemWinningsRound to Market-Creator FSM

> For background on the full market lifecycle (contracts, phases, token flow), see [docs/omen_lifecycle.md](../docs/omen_lifecycle.md).

## Context

The market-creator service creates Omen prediction markets, provides liquidity, answers Realitio questions, removes liquidity, and redeems Realitio bonds. However, it's missing a critical step: **redeeming conditional tokens** (winnings from trading activity).

When traders buy/sell on a market, the liquidity pool becomes imbalanced. When the LP removes liquidity, they receive proportional outcome tokens. The `RemoveFundingRound` already handles `removeFunding` + `mergePositions` + `withdraw`, but after merging, **residual outcome tokens may remain** (the imbalanced portion). Once the market resolves, these tokens can be redeemed for collateral via `ConditionalTokens.redeemPositions()`.

**Scope (v1):** Only call `redeemPositions` on already-resolved conditions. The more complex `claimWinnings` + `resolve` flow (which requires fetching Realitio answer history) is deferred to a future iteration. This means v1 handles the common case where the oracle answer has already been finalized and reported to ConditionalTokens by other participants.

## FSM Integration

**Current flow (relevant section):**
```
SyncMarkets → RemoveFunding → [TxSettlement] → PostTx(REMOVE_FUNDING_DONE) → DepositDai
```

**Proposed flow:**
```
SyncMarkets → RemoveFunding
  → [if tx (DONE)] → [TxSettlement] → PostTx(REMOVE_FUNDING_DONE) → RedeemWinnings
  → [if no tx / error] → RedeemWinnings (directly, no settlement needed)

RedeemWinnings
  → [if tx (DONE)] → [TxSettlement] → PostTx(REDEEM_WINNINGS_DONE) → DepositDai
  → [if no tx / error] → DepositDai (directly, no settlement needed)
```

This placement is logical because:
- After removing liquidity, residual conditional tokens may need redemption
- Before depositing DAI, claim any available winnings first (increases available DAI)
- Like all other rounds, errors in RedeemWinnings skip ahead to DepositDai (never blocks)
- RemoveFunding errors/no-ops also proceed to RedeemWinnings (not DepositDai), so winnings can always be checked regardless of whether liquidity was removed

## Data Source for Redeemable Markets

**Important:** `SyncMarketsRound` only queries markets where the safe still has LP shares (`amount_gt: "0"`). After `RemoveFundingRound` burns all LP shares, the market disappears from `markets_to_remove_liquidity`. Therefore, `RedeemWinningsBehaviour` needs its **own subgraph queries** to discover all markets where the safe may hold residual conditional tokens.

The behaviour uses **two separate subgraph queries**, then deduplicates by market address:
1. **LP positions** — `fpmmLiquidities(where: {funder: $safe, type: Add})`: markets where the safe ever added liquidity, regardless of who created the market. Covers the standard market-creator LP flow.
2. **Trader positions** — `fpmmTrades(where: {creator: $safe, type: Buy})`: markets where the safe bought outcome tokens as a trader. Covers trader services or any hybrid service that also trades.

For each deduplicated market, the behaviour:
1. Checks on-chain if the condition is resolved (`check_resolved`)
2. Checks if the safe holds any conditional tokens (`get_user_holdings`)
3. Builds a `redeemPositions` transaction for markets with non-zero holdings

This design is **service-agnostic**: it works for pure LPs, pure traders, or any combination.

## Files Created

### 1. `states/redeem_winnings.py`
Minimal round extending `TxPreparationRound` (same pattern as `states/redeem_bond.py`):
```python
class RedeemWinningsRound(TxPreparationRound):
    """A round for redeeming conditional tokens (market winnings)."""
```

### 2. `behaviours/redeem_winnings.py`
Core logic. Follows `RedeemBondBehaviour` pattern with `async_act()` → `get_payload()`.

**Algorithm (v1 — redeemPositions only):**

1. Query Omen subgraph for ALL markets created by safe where `openingTimestamp` is in the past
2. For each market, call `ConditionalTokensContract.check_resolved(condition_id)` — skip unresolved
3. For resolved markets, call `ConditionalTokensContract.get_user_holdings(...)` — skip if no shares (all zeros)
4. For markets with non-zero shares, build `ConditionalTokensContract.build_redeem_positions_tx(collateral_token, ZERO_HASH, condition_id, index_sets)`
5. Bundle all into multisend via `self._to_multisend()`
6. Return `None` if nothing to redeem (FSM moves forward via `Event.NONE`)

**Contracts used** (all already synced as third-party):
- `conditional_tokens` — `check_resolved`, `get_user_holdings`, `build_redeem_positions_tx`

**Configurable parameters** (added to models.py):
- `redeem_winnings_batch_size` (default: 5) — max markets to process per cycle (avoids gas limits)
- Reuses existing: `conditional_tokens_contract`, `collateral_tokens_contract`

**Subgraph queries** (two, merged and deduplicated):
```python
# LP positions: any market where the safe added liquidity
LP_MARKETS_QUERY = Template("""{
  fpmmLiquidities(
    where: {funder: "$safe", type: Add, fpmm_: {openingTimestamp_lt: "$now"}}
    first: $batch_size
  ) {
    fpmm { id conditions { id outcomeSlotCount } }
  }
}""")

# Trader positions: any market where the safe bought outcome tokens
TRADE_MARKETS_QUERY = Template("""{
  fpmmTrades(
    where: {creator: "$safe", type: Buy, fpmm_: {openingTimestamp_lt: "$now"}}
    first: $batch_size
  ) {
    fpmm { id conditions { id outcomeSlotCount } }
  }
}""")
```

## Files Modified

### 3. `states/base.py`
Added to `Event` enum:
```python
REDEEM_WINNINGS_DONE = "redeem_winnings_done"
```

### 4. `states/final_states.py`
Added:
```python
class FinishedWithRedeemWinningsRound(DegenerateRound):
    """FinishedWithRedeemWinningsRound"""
```

### 5. `states/post_transaction.py`
Added constant `REDEEM_WINNINGS_DONE_PAYLOAD = "REDEEM_WINNINGS_DONE_PAYLOAD"` and added handling in `end_block()`:
```python
if self.most_voted_payload == self.REDEEM_WINNINGS_DONE_PAYLOAD:
    return self.synchronized_data, Event.REDEEM_WINNINGS_DONE
```

### 6. `rounds.py` (FSM transition function)
- Imported `RedeemWinningsRound` and `FinishedWithRedeemWinningsRound`
- Added `RedeemWinningsRound` to `initial_states` (it's an entry from PostTransactionRound)
- **Changed** `PostTransactionRound` routing: `REMOVE_FUNDING_DONE → RedeemWinningsRound` (was DepositDaiRound)
- **Added** `PostTransactionRound` routing: `REDEEM_WINNINGS_DONE → DepositDaiRound`
- **Added** `RedeemWinningsRound` transitions:
  ```python
  RedeemWinningsRound: {
      Event.DONE: FinishedWithRedeemWinningsRound,
      Event.NO_MAJORITY: DepositDaiRound,
      Event.NONE: DepositDaiRound,
      Event.ROUND_TIMEOUT: DepositDaiRound,
  },
  ```
- Added `FinishedWithRedeemWinningsRound: {}` to transition_function
- Added to `final_states`, `db_pre_conditions`, `db_post_conditions` (with `most_voted_tx_hash`)

### 7. `behaviours/post_transaction.py`
Imported `RedeemWinningsRound`. Added routing in `get_payload()`:
```python
if self.synchronized_data.tx_submitter == RedeemWinningsRound.auto_round_id():
    return PostTransactionRound.REDEEM_WINNINGS_DONE_PAYLOAD
```

### 8. `behaviours/round_behaviour.py`
Imported and added `RedeemWinningsBehaviour` to the `behaviours` set.

### 9. `market_maker_abci/composition.py`
Added composition mapping:
```python
MarketCreationManagerAbci.FinishedWithRedeemWinningsRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
```

### 10. `models.py` (market_creation_manager_abci)
Added `redeem_winnings_batch_size` parameter.

### 11. `fsm_specification.yaml`
Regenerated via `autonomy analyse fsm-specs --update`. Changes:
- Added `redeem_winnings_done` to `alphabet_in`
- Added `RedeemWinningsRound` and `FinishedWithRedeemWinningsRound` to `states`
- Added `RedeemWinningsRound` to `start_states`
- Added `FinishedWithRedeemWinningsRound` to `final_states`
- Added transition entries for `RedeemWinningsRound` and updated `PostTransactionRound`

### 12. `market_maker_abci/fsm_specification.yaml`
Regenerated via `autonomy analyse fsm-specs --update --package packages/valory/skills/market_maker_abci`

## Verification

After implementation:
```bash
# 1. Validate FSM specs
autonomy analyse fsm-specs --package packages/valory/skills/market_creation_manager_abci
autonomy analyse fsm-specs --package packages/valory/skills/market_maker_abci

# 2. Lock packages
autonomy packages lock

# 3. Run tests
tox -e unit-tests

# 4. Run mypy
tox -e mypy

# 5. Run formatting
tox -e black && tox -e isort
```

## Resolved Decisions

1. **Scope**: v1 is `redeemPositions` only (no `claimWinnings`/`resolve`). This simplifies the behaviour and avoids needing `realitio`/`realitio_proxy` contracts.
2. **Subgraph query scope**: Query ALL historical markets created by the safe. Use `redeem_winnings_batch_size` to limit on-chain calls per cycle.
3. **realitio_proxy**: Not needed for v1 (confirmed not in params). Can be added in a future iteration when `claimWinnings`/`resolve` is implemented.
4. **wxDAI handling**: After `redeemPositions`, the collateral (wxDAI) stays in the safe. No unwrap step needed — wxDAI is directly usable for market creation. The existing `DepositDaiRound` wraps additional xDAI when needed.

## Key Findings from On-Chain Investigation

### LP residual tokens mechanics

After `removeFunding` + `mergePositions`, the safe holds residual conditional tokens on exactly **one** outcome side — whichever outcome traders bought more of (the "heavier" side). The min-based merge consumes equal amounts from both sides, leaving excess only on the heavier one.

This means:

- If the heavier side **won** → tokens are redeemable (`numerator > 0`)
- If the heavier side **lost** → tokens exist but are worthless (`numerator = 0`, payout = 0)

Empirically, ~38% of resolved markets have redeemable tokens (the heavier side won). This is expected — LPs don't choose sides; it depends on trader behaviour vs actual outcomes.

### v1 viability confirmed

- **Conditions ARE resolved on-chain** for the vast majority of old markets. Traders and other participants call `reportPayouts` via the Realitio proxy as part of their own redemption flow. The v1 assumption (conditions already resolved by others) holds well in practice.
- **Calling `redeemPositions` with losing tokens is safe** — it returns 0 collateral, doesn't revert. No need to pre-filter by winning side; the contract handles it gracefully.
- **`check_resolved` correctly gates redemption** — it checks `payoutDenominator > 0`.

### ConditionalTokens contract address

The canonical address on Gnosis chain is `0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce`. Note: the `skill.yaml` defaults to `0x000...000` (overridden at deployment via service/agent config). Be careful not to confuse with similar-looking addresses.

### Potential v2 enhancements

1. **Add `check_redeemed`**: The ConditionalTokens contract has a `PayoutRedemption` event. Filtering for already-redeemed positions would avoid repeated (harmless but gas-wasting) `redeemPositions` calls on positions that were already claimed.
2. **Add lazy resolution**: Like the trader, call `realitio_proxy.resolve()` before `redeemPositions` for conditions not yet resolved. This would capture the ~small percentage of markets where no one has resolved the condition yet.
3. **Batch optimization**: With ~4,780+ redeemable markets accumulated over time, the `redeem_winnings_batch_size` parameter (default: 5) means it will take many cycles to clear the backlog. Consider a one-time cleanup script or increasing the batch size for initial catch-up.

## Utility Scripts

- `scripts/check_redeemable_positions.py` — Queries subgraph + on-chain (via Multicall3) to report how many markets are redeemable and the total xDAI recoverable for a given safe address. Uses batched multicall for performance (~12k markets checked in seconds). Requires `OMEN_SUBGRAPH_URL` in `.env`; `GNOSIS_RPC` defaults to `https://rpc.gnosischain.com`.
