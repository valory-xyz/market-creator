# Plan: Add RedeemWinningsRound to Market-Creator FSM

> For background on the full market lifecycle (contracts, phases, token flow), see [docs/omen_lifecycle.md](../docs/omen_lifecycle.md).

## Context

The market-creator service creates Omen prediction markets, provides liquidity, answers Realitio questions, removes liquidity, and redeems Realitio bonds. However, it's missing a critical step: **redeeming conditional tokens** (winnings from trading activity).

When traders buy/sell on a market, the liquidity pool becomes imbalanced. When the LP removes liquidity, they receive proportional outcome tokens. The `RemoveFundingRound` already handles `removeFunding` + `mergePositions` + `withdraw`, but after merging, **residual outcome tokens may remain** (the imbalanced portion). Once the market resolves, these tokens can be redeemed for collateral via `ConditionalTokens.redeemPositions()`.

**Scope (v1):** Only call `redeemPositions` on already-resolved conditions. The more complex `claimWinnings` + `resolve` flow (which requires fetching Realitio answer history) is deferred to a future iteration. This means v1 handles the common case where the oracle answer has already been finalized and reported to ConditionalTokens by other participants.

## FSM Integration

**Current flow (relevant section):**
```
SyncMarkets -> RemoveFunding -> [TxSettlement] -> PostTx(REMOVE_FUNDING_DONE) -> DepositDai
```

**Implemented flow:**
```
SyncMarkets -> RemoveFunding
  -> [if tx (DONE)] -> [TxSettlement] -> PostTx(REMOVE_FUNDING_DONE) -> RedeemWinnings
  -> [if no tx / error] -> RedeemWinnings (directly, no settlement needed)

RedeemWinnings
  -> [if tx (DONE)] -> [TxSettlement] -> PostTx(REDEEM_WINNINGS_DONE) -> DepositDai
  -> [if no tx / error] -> DepositDai (directly, no settlement needed)
```

This placement is logical because:
- After removing liquidity, residual conditional tokens may need redemption
- Before depositing DAI, claim any available winnings first (increases available DAI)
- Like all other rounds, errors in RedeemWinnings skip ahead to DepositDai (never blocks)
- RemoveFunding errors/no-ops also proceed to RedeemWinnings (not DepositDai), so winnings can always be checked regardless of whether liquidity was removed

## Data Source — Two-Subgraph Strategy

The behaviour uses **two subgraphs** to determine what to redeem, eliminating unnecessary on-chain calls:

### Step 1: ConditionalTokens subgraph — held positions

Query `userPositions(balance_gt: "0")` to find ALL conditions where the safe holds non-zero conditional token balances. This returns:
- `conditionIds` — which condition the position belongs to
- `indexSets` — which outcome side the tokens are on (e.g., `1` = outcome 0, `2` = outcome 1)

Result: `Dict[condition_id → Set[held_index_sets]]`

### Step 2: Omen subgraph — finalized markets matching held conditions

Query `fixedProductMarketMakers` filtered by `conditions_: {id_in: [...]}` using the condition IDs from Step 1. This uses a **targeted join** — the Omen subgraph only returns markets where the safe actually holds tokens. No cursor or pagination through all markets needed.

Additional filters: `answerFinalizedTimestamp_not: null` (market is resolved).

Result: list of `{address, condition_id, payouts, outcome_slot_count}`

### Step 3: Local cross-reference — winning positions only

For each market from Step 2, check if the held index sets contain a **winning** outcome:
- `payouts = ["1", "0"]` and `held_index_sets = {1}` → index set 1 = outcome 0, payout[0] = "1" → **winning**
- `payouts = ["1", "0"]` and `held_index_sets = {2}` → index set 2 = outcome 1, payout[1] = "0" → **losing, skip**

### Step 4: Build redeem transactions

For each winning market (up to `batch_size`), call `ConditionalTokensContract.build_redeem_positions_tx(...)` and bundle into a multisend.

### Why this design

| Check | Method | Why |
|-------|--------|-----|
| Safe holds tokens? | **CT subgraph** (`balance_gt: "0"`) | Automatically excludes already-redeemed positions |
| Is market resolved? | **Omen subgraph** (`answerFinalizedTimestamp_not: null`) | Subgraph filter, no on-chain call |
| Which outcome won? | **Omen subgraph** (`payouts` field) | Subgraph data, no on-chain call |
| Which side does safe hold? | **CT subgraph** (`indexSets`) | Subgraph data, no on-chain call |
| Build redeem tx | **On-chain** (`build_redeem_positions_tx`) | Only for winning positions |

**On-chain calls per cycle:** `batch_size` × 2 (check_resolved + build_redeem_positions_tx), plus 1 extra (build_resolve_tx) for each unresolved condition. Typically ~10-15 calls at default batch_size=5. Well under the round timeout.

### Why not cursor-based pagination

Earlier iterations used cursor-based pagination through all Omen markets, but this had problems:
1. The service would check the same markets every cycle (cursor reset issues)
2. With 2500+ markets, iterating through all and making on-chain calls caused round timeouts
3. The `conditions_: {id_in: [...]}` filter eliminates the need for pagination entirely — it returns only markets where the safe has tokens

## Algorithm

1. Query CT subgraph for all positions with `balance_gt: "0"` (paginated by `id_gt`)
2. Build lookup: `{condition_id: Set[index_sets]}`
3. Batch condition IDs into chunks of 100 (avoids subgraph query size limits)
4. For each batch, query Omen subgraph: `conditions_: {id_in: [...]}, answerFinalizedTimestamp_not: null`
   - Also fetches `question { id data }` and `templateId` for the resolve call
5. Filter locally: skip markets with null/zero payouts, skip if held index sets are all on losing side
6. For each winning market (up to `batch_size`):
   a. Call `ConditionalTokensContract.check_resolved(condition_id)` — check if already resolved on-chain
   b. If **not resolved**: build `RealitioProxyContract.build_resolve_tx(question_id, template_id, question, num_outcomes)` and prepend to multisend
   c. Build `ConditionalTokensContract.build_redeem_positions_tx(collateral, ZERO_HASH, condition_id, index_sets)`
7. Bundle all txs (resolve + redeem pairs) into multisend via `_to_multisend()`
8. Return `None` if nothing to redeem (FSM emits `Event.NONE`)

### Lazy resolution

The v1 assumption was that conditions are already resolved by traders. This holds for ~99% of markets, but the remaining ~1% would silently get 0 payout.

The behaviour now checks `payoutDenominator` on-chain for each redeemable market. If the condition is not yet resolved, it prepends a `RealitioProxy.resolve()` call in the same multisend. This ensures the condition is resolved and redeemed atomically in a single Safe transaction.

The `resolve` call reads the finalized Realitio answer and reports it to ConditionalTokens (`reportPayouts`). Parameters come from the Omen subgraph: `question.id`, `question.data`, `templateId`, and `outcomeSlotCount`.

## Configurable Parameters

- `redeem_winnings_batch_size` (default: 5) — max redeem transactions per cycle

Promoted through the full config chain:
- `models.py` → `self._ensure("redeem_winnings_batch_size", kwargs, type_=int)`
- `market_creation_manager_abci/skill.yaml` → `redeem_winnings_batch_size: 5`
- `market_maker_abci/skill.yaml` → `redeem_winnings_batch_size: 5`
- `aea-config.yaml` → `redeem_winnings_batch_size: ${int:5}`
- `service.yaml` → `redeem_winnings_batch_size: ${REDEEM_WINNINGS_BATCH_SIZE:int:5}`

Reuses existing params: `conditional_tokens_contract`, `collateral_tokens_contract`

## Subgraph Queries

```python
# ConditionalTokens subgraph: positions the safe holds with non-zero balance
USER_POSITIONS_QUERY = Template("""{
    user(id: "$safe") {
      userPositions(
        first: $page_size
        where: { balance_gt: "0", id_gt: "$cursor" }
        orderBy: id
      ) {
        id
        balance
        position { conditionIds indexSets }
      }
    }
  }""")

# Omen subgraph: finalized markets filtered by specific condition IDs
MARKETS_BY_CONDITIONS_QUERY = Template("""{
    fixedProductMarketMakers(
      where: {
        conditions_: {id_in: [$condition_ids]}
        answerFinalizedTimestamp_not: null
        answerFinalizedTimestamp_lt: "$now"
      }
      first: $page_size
      orderBy: id
      orderDirection: asc
    ) {
      id
      payouts
      conditions { id outcomeSlotCount }
    }
  }""")
```

**Contracts used** (all already synced as third-party):
- `conditional_tokens` — `check_resolved`, `build_redeem_positions_tx`
- `realitio_proxy` — `build_resolve_tx` (for lazy resolution of unresolved conditions)

## Files Created

### 1. `states/redeem_winnings.py`
Minimal round extending `TxPreparationRound` (same pattern as `states/redeem_bond.py`):
```python
class RedeemWinningsRound(TxPreparationRound):
    """A round for redeeming conditional tokens (market winnings)."""
```

### 2. `behaviours/redeem_winnings.py`
Core logic. Follows `RedeemBondBehaviour` pattern with `async_act()` -> `get_payload()`.

### 3. `models.py` — `ConditionalTokensSubgraph`
New `ApiSpecs` model for the ConditionalTokens subgraph, configured via `conditional_tokens_subgraph_url`.

## Files Modified

### 4. `states/base.py`
Added to `Event` enum:
```python
REDEEM_WINNINGS_DONE = "redeem_winnings_done"
```

### 5. `states/final_states.py`
Added:
```python
class FinishedWithRedeemWinningsRound(DegenerateRound):
    """FinishedWithRedeemWinningsRound"""
```

### 6. `states/post_transaction.py`
Added constant `REDEEM_WINNINGS_DONE_PAYLOAD = "REDEEM_WINNINGS_DONE_PAYLOAD"` and added handling in `end_block()`:
```python
if self.most_voted_payload == self.REDEEM_WINNINGS_DONE_PAYLOAD:
    return self.synchronized_data, Event.REDEEM_WINNINGS_DONE
```

### 7. `rounds.py` (FSM transition function)
- Imported `RedeemWinningsRound` and `FinishedWithRedeemWinningsRound`
- Added `RedeemWinningsRound` to `initial_states` (it's an entry from PostTransactionRound)
- **Changed** `PostTransactionRound` routing: `REMOVE_FUNDING_DONE -> RedeemWinningsRound` (was DepositDaiRound)
- **Added** `PostTransactionRound` routing: `REDEEM_WINNINGS_DONE -> DepositDaiRound`
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

### 8. `behaviours/post_transaction.py`
Imported `RedeemWinningsRound`. Added routing in `get_payload()`:
```python
if self.synchronized_data.tx_submitter == RedeemWinningsRound.auto_round_id():
    return PostTransactionRound.REDEEM_WINNINGS_DONE_PAYLOAD
```

### 9. `behaviours/round_behaviour.py`
Imported and added `RedeemWinningsBehaviour` to the `behaviours` set.

### 10. `behaviours/base.py`
Added `get_conditional_tokens_subgraph_result()` method for querying the CT subgraph.

### 11. `market_maker_abci/composition.py`
Added composition mapping:
```python
MarketCreationManagerAbci.FinishedWithRedeemWinningsRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
```

### 12. `models.py` (market_creation_manager_abci)
- Added `redeem_winnings_batch_size` parameter
- Added `ConditionalTokensSubgraph` model

### 13. Config files
- `market_creation_manager_abci/skill.yaml` — added `redeem_winnings_batch_size`, `ConditionalTokensSubgraph` model, `realitio_proxy` contract dependency
- `market_maker_abci/skill.yaml` — added `redeem_winnings_batch_size`, `ConditionalTokensSubgraph` model
- `agents/market_maker/aea-config.yaml` — added `redeem_winnings_batch_size: ${int:5}`
- `services/market_maker/service.yaml` — added `redeem_winnings_batch_size: ${REDEEM_WINNINGS_BATCH_SIZE:int:5}`

### 14. FSM specifications
Regenerated via `autonomy analyse fsm-specs --update`. Changes:
- Added `redeem_winnings_done` to `alphabet_in`
- Added `RedeemWinningsRound` and `FinishedWithRedeemWinningsRound` to `states`
- Added `RedeemWinningsRound` to `start_states`
- Added `FinishedWithRedeemWinningsRound` to `final_states`
- Added transition entries for `RedeemWinningsRound` and updated `PostTransactionRound`

Both `market_creation_manager_abci/fsm_specification.yaml` and `market_maker_abci/fsm_specification.yaml` updated.

### 15. `contracts/fpmm/contract.py`
Added `get_payout_numerators()` method with inline ConditionalTokens ABI (`CT_PAYOUT_NUMERATORS_ABI`). Used by analysis scripts; the behaviour uses subgraph `payouts` instead.

## Verification

After implementation:
```bash
# 1. Validate FSM specs
autonomy analyse fsm-specs --package packages/valory/skills/market_creation_manager_abci
autonomy analyse fsm-specs --package packages/valory/skills/market_maker_abci

# 2. Run linter pipeline
/oa-linters

# 3. Run tests with coverage
tox -e unit-tests
```

## Resolved Decisions

1. **Scope**: `redeemPositions` with lazy `resolve`. The behaviour calls `RealitioProxy.resolve()` when a condition hasn't been resolved on-chain yet, then `redeemPositions` — both in the same multisend. The more complex `claimWinnings` flow (claiming Realitio bonds from answer history) is handled by the separate `RedeemBondRound`.
2. **Two-subgraph approach**: CT subgraph for held positions + Omen subgraph filtered by `conditions_: {id_in: [...]}`. No cursor needed — the CT subgraph naturally excludes redeemed positions (`balance_gt: "0"`), and the Omen query is targeted, not paginated.
3. **Losing-side filtering**: Cross-reference held `indexSets` (CT subgraph) with `payouts` (Omen subgraph) to skip markets where the safe only holds losing tokens. Saves gas by not including worthless redemptions in the multisend.
4. **No cursor persistence needed**: Unlike the earlier designs that paginated through all markets, the `conditions_: {id_in: [...]}` approach queries exactly the relevant markets. Already-redeemed positions disappear from the CT subgraph automatically.
5. **realitio_proxy**: Used for lazy resolution via `build_resolve_tx`. The contract was already synced as a third-party dependency; only needed to add it to the skill's contract dependencies.
6. **wxDAI handling**: After `redeemPositions`, the collateral (wxDAI) stays in the safe. No unwrap step needed — wxDAI is directly usable for market creation. The existing `DepositDaiRound` wraps additional xDAI when needed.
7. **Condition ID batching**: The `conditions_: {id_in: [...]}` query is batched into chunks of 100 IDs to avoid subgraph query size limits. With 1400 held conditions, this means ~14 subgraph queries — all fast and cacheable.

## Key Findings from On-Chain Investigation

### LP residual tokens mechanics

After `removeFunding` + `mergePositions`, the safe holds residual conditional tokens on exactly **one** outcome side — whichever outcome traders bought more of (the "heavier" side). The min-based merge consumes equal amounts from both sides, leaving excess only on the heavier one.

This means:

- If the heavier side **won** -> tokens are redeemable (`numerator > 0`)
- If the heavier side **lost** -> tokens exist but are worthless (`numerator = 0`, payout = 0)

Empirically, ~38% of resolved markets have redeemable tokens (the heavier side won). This is expected — LPs don't choose sides; it depends on trader behaviour vs actual outcomes.

### v1 viability confirmed

- **Conditions ARE resolved on-chain** for the vast majority of old markets. Traders and other participants call `reportPayouts` via the Realitio proxy as part of their own redemption flow. The v1 assumption (conditions already resolved by others) holds well in practice.
- **Calling `redeemPositions` with losing tokens is safe** — it returns 0 collateral, doesn't revert. But it wastes gas, which is why we filter using subgraph `payouts` data.
- **`answerFinalizedTimestamp` is a reliable proxy for resolution** — once the Realitio answer is finalized, someone will almost certainly have called `resolve` by the time our service checks.

### ConditionalTokens contract address

The canonical address on Gnosis chain is `0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce`. Note: the `skill.yaml` defaults to `0x000...000` (overridden at deployment via service/agent config). Be careful not to confuse with similar-looking addresses.

### Production bugs found and fixed

1. **Wrong subgraph query for LP positions**: The original `fpmmLiquidities(funder: $safe)` query returned 0 results because the factory contract (not the safe) is the `funder` during market creation. Fixed by using `fixedProductMarketMakers(creator: $safe)` as the primary LP query, with `fpmmLiquidities` as a secondary query for direct (non-factory) funding.
2. **Pagination stuck on same markets**: The original design used `batch_size` as the subgraph `first:` limit with `orderBy: creationTimestamp`. This returned the same N markets every cycle. Eliminated by switching to the two-subgraph approach.
3. **Round timeout with 1000+ markets**: Making on-chain calls per market caused timeouts. Eliminated by moving all filtering to subgraph queries — zero on-chain calls for discovery.

## Potential v2 Enhancements

1. **Multicall3 batching**: Like the utility scripts, use Multicall3 to batch `check_resolved` and `build_redeem_positions_tx` calls into a single RPC round-trip. This would allow larger batch sizes per cycle.
2. **Notebook integration**: The `get_redeemable_positions()` function in `notebooks/subgraph_omen.py` exposes redeemable data as a DataFrame, merged into the market dashboard with a `redeemable_xdai` column.

## Utility Scripts

- `analysis/check_redeemable_positions.py` — (v1) Queries subgraph for ALL markets + on-chain checks via Multicall3 (payoutDenominator, getCollectionId, balanceOf, payoutNumerators). Reports total redeemable xDAI. Serves as a ground-truth checkpoint.
- `analysis/check_redeemable_positions2.py` — (v2, efficient) Uses the subgraph-first approach: filters for finalized markets with `answerFinalizedTimestamp`, gets `payouts` from subgraph, only checks `balanceOf` on-chain for winning outcomes. Fewer RPC calls, includes timing comparison.
- `analysis/check_redeemable_positions3.py` — (v3, behaviour simulation) Mirrors the exact two-subgraph strategy used by the behaviour. Logs each step (CT subgraph → Omen subgraph → cross-reference → build txs). Useful for debugging the service without deploying.

All scripts accept a safe address CLI argument and read subgraph URLs from `.env`.
