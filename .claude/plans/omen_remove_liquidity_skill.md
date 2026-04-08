# Plan — `omen_fpmm_remove_liquidity_abci` skill

**Part of:** [omen_funds_recoverer_split.md](omen_funds_recoverer_split.md) (read the overview first for shared design decisions)
**Baseline reference:** [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/remove_liquidity.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/remove_liquidity.py) — the tx-building logic of the new skill is equivalent to this file's `RemoveLiquidityBehaviour`, **plus** an expanded trigger matrix described below

## Purpose

Call `FPMM.removeFunding(sharesToBurn)` on FPMMs where the safe holds LP shares and the market is either (a) approaching its close window, or (b) already closed — regardless of whether the oracle has resolved it yet. Optionally prepend `ConditionalTokens.mergePositions(...)` when the market has not yet resolved, to extract the "equal part" of the returned outcome tokens as wxDAI.

This is the skill for **liquidity providers** — actors who provided funding to an FPMM and want to withdraw their LP shares. The flow is distinct from both the trader flow (`omen_ct_redeem_tokens_abci`) and the answerer flow (`omen_realitio_withdraw_bond_abci`).

## Why the skill is named `omen_fpmm_*` and not `omen_ct_*`

The primary contract interaction is `FPMM.removeFunding`. The follow-up `ConditionalTokens.mergePositions` is secondary and conditional. If a reader asks "which Solidity file do I read first to understand this skill," the answer is the FPMM contract, not Conditional Tokens. Naming the skill after CT would collide with `omen_ct_redeem_tokens_abci` (both skills would target CT) and would hide the primary action.

The skill **does** touch Conditional Tokens as a secondary action, but it does so in service of the primary `removeFunding` call. The primary verb wins the naming rights.

## The four-state matrix — expanded from the baseline behaviour

This is the **only intentional behavioural difference** between this skill and the current monolith. The baseline `RemoveLiquidityBehaviour` only handles the pre-close state. The new skill handles all four states of an FPMM's lifecycle.

| # | Market state | Detection | Action | Rationale |
|---|---|---|---|---|
| 1 | Open, trading, far from close | `now < openingTimestamp - lead_time` | **skip** | Don't interfere with an actively traded market — LP is still earning fees and the pool is still useful |
| 2 | Open, approaching close | `openingTimestamp - lead_time <= now < openingTimestamp` | `removeFunding` + `mergePositions` | Market is about to stop trading. LP is no longer useful and the oracle hasn't decided yet, so the returned outcome tokens can be merged back to wxDAI via the "equal part" trick |
| 3 | Closed, not yet resolved | `now >= openingTimestamp` AND `answerFinalizedTimestamp_gt: 0` is false (i.e. null / 0) | `removeFunding` + `mergePositions` | Same economics as state 2 — the oracle hasn't decided yet, so the merge trick still works. Market is past close but pre-resolution. Matches the baseline plus adds post-close pre-resolution coverage |
| 4 | Closed, resolved | `now >= openingTimestamp` AND `answerFinalizedTimestamp_gt: 0` | `removeFunding` only — no merge | Merging post-resolution doesn't work because losing-outcome tokens can't merge with anything. The returned outcome tokens sit in the safe for one period, then [`omen_ct_redeem_tokens_abci`](omen_ct_redeem_skill.md) picks them up via its CT-subgraph query and redeems the winning ones |

The baseline behaviour only handles state 2 (its trigger is exactly `removal_timestamp < now` where `removal_timestamp = openingTimestamp - lead_time`). States 3 and 4 are **new capabilities** in this skill.

### Closing the gap

This matrix closes a gap in the current monolith that was discovered while designing the split: LP shares left in already-closed markets (either pre-resolution or post-resolution) are currently **unrecoverable** in the monolith. The `RemoveLiquidityBehaviour` skips them because its trigger condition doesn't match. This could cause real capital lockup if a service stops running for a few days and several of its markets resolve in the meantime.

Per the user's guidance, the new skill's responsibility is "what can be done at that point and is the responsibility of the skill." States 2 and 3 are algorithmically identical (both do `removeFunding + mergePositions`) so they collapse into one action. State 4 drops the merge step because it would be a no-op.

### State detection in code

```python
def _classify_market(self, fpmm: Dict[str, Any], now: int) -> str:
    """Return one of 'skip', 'remove_and_merge', 'remove_only'."""
    opening_ts = int(fpmm["openingTimestamp"])
    answer_finalized_ts = fpmm.get("answerFinalizedTimestamp")
    lead_time = self.params.liquidity_removal_lead_time

    if now < opening_ts - lead_time:
        # State 1: open and trading, far from close
        return "skip"

    if not answer_finalized_ts or int(answer_finalized_ts) == 0:
        # States 2 and 3: oracle hasn't decided yet
        return "remove_and_merge"

    # State 4: resolved, merge no longer useful
    return "remove_only"
```

This three-way dispatch replaces the baseline's single `removal_timestamp < now` filter.

## Who calls what in this flow

```text
LP provider safe added funding to FPMM via FPMM.addFunding(amount, distributionHint)
                  │
                  ▼
    [market trades, pool accumulates trading fees]
                  │
                  ▼
    [market approaches close OR closes OR resolves]
                  │
                  ▼
    LP safe calls FPMM.removeFunding(sharesToBurn)
                  │   (burns LP shares, returns pro-rata collateral
                  │    + imbalanced outcome tokens)
                  ▼
    IF (market not resolved): LP safe calls
      ConditionalTokens.mergePositions(
          collateralToken, parentCollectionId, conditionId,
          partition, amount)
                  │   (takes min() of outcome tokens as "equal part"
                  │    and converts back to wxDAI)
                  ▼
    Residual outcome tokens (if any) stay in safe, waiting for
    omen_ct_redeem_tokens_abci to handle them in a later period
                  │
                  ▼
    wxDAI returned to safe wallet
```

## Trigger conditions

The skill produces a multisend when **at least one** FPMM meets all of:

1. `fpmmPoolMembership.amount > 0` — the safe currently holds LP shares in the FPMM (from the Omen subgraph query)
2. The market is in state 2, 3, or 4 from the matrix above (not state 1)
3. On-chain verification that `FPMM.balanceOf(safe) > 0` (the subgraph can lag; the on-chain read is authoritative)

If no FPMM meets all three, the skill emits `tx_hash=None` and routes to `FinishedWithoutFpmmRemoveLiquidityTxRound`.

## Subgraphs used

One subgraph:

1. **Omen subgraph** (`9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz` on TheGraph decentralized network) — fetches `fpmmPoolMemberships(funder: $safe, amount_gt: "0")` with nested `pool { id openingTimestamp answerFinalizedTimestamp conditions { id question { id } outcomeSlotCount } liquidityMeasure outcomeTokenAmounts }`

The `answerFinalizedTimestamp` field in the nested `pool` selection is what drives the four-state classification.

## Contracts used

| Contract | Role | Methods called |
|---|---|---|
| `FPMM` | Primary | `get_markets_with_funds` (read — on-chain verification of subgraph results), `get_balance` (read), `get_total_supply` (read), `build_remove_funding_tx` (write) |
| `ConditionalTokens` | Secondary (states 2 + 3 only) | `get_user_holdings` (read), `build_merge_positions_tx` (write) |
| `Multisend` | Wrapping | `get_tx_data` |
| `GnosisSafe` | Settlement | `get_raw_safe_transaction_hash` |

## File structure

```text
packages/valory/skills/omen_fpmm_remove_liquidity_abci/
├── __init__.py                    # PUBLIC_ID definition
├── skill.yaml                     # dependencies, params, omen_subgraph model, round_behaviour
├── fsm_specification.yaml
├── rounds.py                      # ~80 lines: Event, SynchronizedData, FpmmRemoveLiquidityRound, 2 final states, AbciApp
├── payloads.py                    # ~15 lines: FpmmRemoveLiquidityPayload
├── models.py                      # ~80 lines: FpmmRemoveLiquidityParams, SharedState, OmenSubgraph
├── handlers.py
├── dialogues.py
├── behaviours/
│   ├── __init__.py
│   ├── base.py                    # ~150 lines: base behaviour
│   ├── behaviour.py               # ~400 lines: FpmmRemoveLiquidityBehaviour (largest of the three due to the state classification + two action paths)
│   └── round_behaviour.py
└── tests/...
```

## FSM

Same shape as the CT redeem skill. One consensus round, two final states:

```python
class FpmmRemoveLiquidityRound(CollectSameUntilThresholdRound):
    payload_class = FpmmRemoveLiquidityPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = "participant_to_fpmm_remove_liquidity_tx"


class FinishedWithFpmmRemoveLiquidityTxRound(DegenerateRound): ...
class FinishedWithoutFpmmRemoveLiquidityTxRound(DegenerateRound): ...


class OmenFpmmRemoveLiquidityAbciApp(AbciApp[Event]):
    initial_round_cls = FpmmRemoveLiquidityRound
    initial_states = {FpmmRemoveLiquidityRound}
    transition_function = {
        FpmmRemoveLiquidityRound: {
            Event.DONE: FinishedWithFpmmRemoveLiquidityTxRound,
            Event.NONE: FinishedWithoutFpmmRemoveLiquidityTxRound,
            Event.NO_MAJORITY: FinishedWithoutFpmmRemoveLiquidityTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutFpmmRemoveLiquidityTxRound,
        },
        FinishedWithFpmmRemoveLiquidityTxRound: {},
        FinishedWithoutFpmmRemoveLiquidityTxRound: {},
    }
    final_states = {FinishedWithFpmmRemoveLiquidityTxRound, FinishedWithoutFpmmRemoveLiquidityTxRound}
    event_to_timeout = {Event.ROUND_TIMEOUT: 120.0}
```

## Behaviour structure

### Entry point

Identical shape to the other two skills — differs only in `_prepare_multisend`.

```python
class FpmmRemoveLiquidityBehaviour(FpmmRemoveLiquidityBaseBehaviour):
    """Build a multisend that removes the safe's LP from closing/closed FPMMs."""

    matching_round = FpmmRemoveLiquidityRound

    def async_act(self) -> Generator:
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash = yield from self._prepare_multisend()
            tx_submitter = "omen_fpmm_liquidity_remove" if tx_hash is not None else None
            payload = FpmmRemoveLiquidityPayload(
                sender=self.context.agent_address,
                tx_submitter=tx_submitter,
                tx_hash=tx_hash,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()
```

### Pipeline recipe

```python
def _prepare_multisend(self) -> Generator[None, None, Optional[str]]:
    """Query FPMMs held by safe + classify + build per-market txs + wrap."""
    # Step 1: fetch FPMMs the safe has LP in
    markets = yield from self._get_markets()
    if not markets:
        self.context.logger.info(f"{LOG_PREFIX} no FPMM LP positions held by safe")
        return None

    # Step 2: classify each into skip / remove_and_merge / remove_only
    now = self.last_synced_timestamp
    actionable = [
        (m, self._classify_market(m, now))
        for m in markets
    ]
    actionable = [(m, action) for m, action in actionable if action != "skip"]
    if not actionable:
        self.context.logger.info(
            f"{LOG_PREFIX} safe holds {len(markets)} LP positions, "
            f"none are actionable this period"
        )
        return None

    # Step 3: build txs per actionable market, up to batch size
    batch_size = self.params.remove_liquidity_batch_size
    txs: List[Dict[str, Any]] = []
    for market, action in actionable[:batch_size]:
        market_txs = yield from self._build_market_txs(market, action)
        txs.extend(market_txs)

    if not txs:
        return None

    # Step 4: wrap in a multisend and compute the safe tx hash
    tx_hash = yield from self._to_multisend(txs)
    if tx_hash is None:
        self.context.logger.warning(f"{LOG_PREFIX} multisend build failed")
        return None

    self.context.logger.info(
        f"{LOG_PREFIX} prepared multisend: {len(txs)} tx(s) "
        f"for {len(actionable[:batch_size])} market(s)"
    )
    return tx_hash


def _build_market_txs(
    self, market: Dict[str, Any], action: str
) -> Generator[None, None, List[Dict[str, Any]]]:
    """Build the per-market tx list based on the classification action."""
    amounts = yield from self._calculate_amounts(
        market=market["address"],
        condition_id=market["condition_id"],
        outcome_slot_count=market["outcome_slot_count"],
    )
    if amounts is None:
        return []

    amount_to_remove, amount_to_merge = amounts

    remove_funding_tx = yield from self._get_remove_funding_tx(
        address=market["address"], amount_to_remove=amount_to_remove
    )
    if remove_funding_tx is None:
        return []

    txs: List[Dict[str, Any]] = [remove_funding_tx]

    if action == "remove_and_merge":
        merge_tx = yield from self._get_merge_positions_tx(
            collateral_token=self.params.collateral_tokens_contract,
            parent_collection_id=ZERO_HASH,
            condition_id=market["condition_id"],
            outcome_slot_count=market["outcome_slot_count"],
            amount=amount_to_merge,
        )
        if merge_tx is not None:
            txs.append(merge_tx)

    return txs
```

### Helpers (lifted from baseline + one new classifier)

- `_get_markets()` — Omen subgraph query + on-chain verification via `FPMM.get_markets_with_funds`. Verbatim from baseline `remove_liquidity.py::_get_markets`, except the Python-side filter is removed (classification moves to `_classify_market`).
- `_classify_market(market, now)` — **new**, the four-state classifier. Returns `"skip"`, `"remove_and_merge"`, or `"remove_only"`.
- `_build_market_txs(market, action)` — refactored from baseline's inline logic in `_build_remove_liquidity_txs`. Dispatches to `_get_remove_funding_tx` always, and `_get_merge_positions_tx` conditionally on `action == "remove_and_merge"`.
- `_calculate_amounts(market, condition_id, outcome_slot_count)` — verbatim from baseline. Computes shares to burn and amount to merge.
- `_get_remove_funding_tx(address, amount_to_remove)` — verbatim from baseline.
- `_get_merge_positions_tx(...)` — verbatim from baseline.
- `_get_markets_with_funds(market_addresses, safe_address)` — verbatim from baseline (on-chain FPMM verification).

## Parameters

Subset of the current `OmenFundsRecovererParams`:

```yaml
liquidity_removal_lead_time: 86400            # unchanged from baseline
remove_liquidity_batch_size: 1                # unchanged
conditional_tokens_contract: "0x..."          # unchanged (needed for mergePositions and get_user_holdings)
collateral_tokens_contract: "0x..."           # unchanged (wxDAI address, needed for mergePositions)
multisend_address: "0x..."                    # inherited from BaseParams
```

**Parameters NOT carried over**: `redeem_positions_batch_size`, `claim_bonds_batch_size`, `min_realitio_withdraw_balance`, `realitio_start_block`, `realitio_contract`, `realitio_oracle_proxy_contract`.

## Base behaviour helpers

`FpmmRemoveLiquidityBaseBehaviour`:

```python
class FpmmRemoveLiquidityBaseBehaviour(BaseBehaviour, ABC):
    # Type-cast properties
    @property
    def synchronized_data(self) -> SynchronizedData: ...
    @property
    def params(self) -> FpmmRemoveLiquidityParams: ...
    @property
    def last_synced_timestamp(self) -> int: ...
    @property
    def shared_state(self) -> SharedState: ...

    # Subgraph helper (only Omen for this skill)
    def get_omen_subgraph_result(self, query: str) -> Generator[None, None, Optional[Dict[str, Any]]]: ...

    # Multisend helpers
    def _get_safe_tx_hash(self, to_address, data, value=0, operation=CALL) -> Generator[None, None, Optional[str]]: ...
    def _to_multisend(self, transactions: List[Dict]) -> Generator[None, None, Optional[str]]: ...
```

## Tests to port

| Current location | New location |
|---|---|
| `tests/behaviours/test_remove_liquidity.py` | `omen_fpmm_remove_liquidity_abci/tests/behaviours/test_behaviour.py` |
| `tests/behaviours/test_base.py` (relevant portions) | `omen_fpmm_remove_liquidity_abci/tests/behaviours/test_base.py` |
| `tests/behaviours/conftest.py` | `omen_fpmm_remove_liquidity_abci/tests/behaviours/conftest.py` (Omen subgraph fixtures only) |
| `tests/test_rounds.py` (the `RemoveLiquidityRound` portion) | `omen_fpmm_remove_liquidity_abci/tests/test_rounds.py` |
| `tests/test_models.py` (the `liquidity_removal_lead_time` + `remove_liquidity_batch_size` assertions) | `omen_fpmm_remove_liquidity_abci/tests/test_models.py` |
| `tests/test_payloads.py` | `omen_fpmm_remove_liquidity_abci/tests/test_payloads.py` |

**Equivalence assertion**: add `test_tx_output_matches_baseline_for_state_2` — for a fixed input where the market is in state 2 (pre-close, approaching), assert the new skill produces the same multisend hash as the baseline. This covers the non-new behaviour path.

**New tests for the expanded matrix**:

- `test_state_1_open_far_from_close_produces_no_tx` — classify-as-skip, empty payload
- `test_state_2_open_approaching_close_produces_remove_and_merge` — baseline-equivalent behaviour
- `test_state_3_closed_not_yet_resolved_produces_remove_and_merge` — **new capability**
- `test_state_4_closed_and_resolved_produces_remove_only` — **new capability**, merge tx absent from the output list
- `test_classify_market_boundary_at_exactly_opening_minus_lead_time` — exact-equality case for the classifier boundary
- `test_classify_market_with_missing_answer_finalized_timestamp` — null/zero handling

**Intentional behavioural differences from baseline** (per the equivalence invariant in the overview):

- **States 3 and 4 are new.** The baseline skips them entirely because its filter is `removal_timestamp < now`. The new skill handles them.
- **State 2 is preserved verbatim.** The tx output in state 2 is byte-identical to the baseline's output (modulo the equivalence relaxation from the overview — "same on-chain effect" rather than "same bytes").
- **No other changes.** The `_calculate_amounts` math, the `_get_remove_funding_tx` calldata construction, and the `_get_merge_positions_tx` calldata construction are all verbatim from baseline.

## Cross-skill interaction — the post-resolution outcome tokens

In state 4 (closed and resolved), the skill burns LP shares via `removeFunding` and does NOT call `mergePositions`. This leaves the returned outcome tokens (a mix of winning and losing tokens) in the safe's wallet.

The **winning tokens** from that residual are then picked up in a later period by [`omen_ct_redeem_tokens_abci`](omen_ct_redeem_skill.md), which queries the CT subgraph for the safe's `userPositions` and detects the new tokens. Its `redeemPositions` call redeems them for wxDAI.

The **losing tokens** from that residual are unrecoverable — they're worth zero after resolution. This is a natural cost of leaving LP in a market past resolution, and it's why state 2 and 3 handling matters (merging before resolution captures more value than state 4's remove-only path).

The two-skill handoff (LP remove → CT redeem) happens across composition cycles. If the composition runs all three recovery skills every period in sequence (FpmmRemoveLiquidity → CtRedeemTokens → RealitioWithdrawBond), then:

- Period N, state 4 market: `FpmmRemoveLiquidity` does `removeFunding`, tx settles, outcome tokens land in safe. `CtRedeemTokens`'s subgraph query in the same period **will not** see them yet because the subgraph hasn't indexed the settlement tx. So the winning tokens sit until period N+1.
- Period N+1: `CtRedeemTokens`'s subgraph query now sees the residual winning tokens, builds `redeemPositions` tx, settles.

One-period latency on state 4 markets. Acceptable.

## Open questions specific to this skill

1. **What counts as "resolved" for state 3 / 4 detection?** The Omen subgraph exposes `answerFinalizedTimestamp` which is the Realitio finalization time. But the actual resolution on Conditional Tokens requires `RealitioProxy.resolve` to be called, which reports payouts to CT. There's a window where Realitio is finalized but CT is not yet resolved. In that window, is the market "state 3" or "state 4"?

    **Decision**: treat it as **state 3** (remove_and_merge), because merging only depends on the oracle's *decision* being available (which is what `answerFinalizedTimestamp` indicates) and doesn't care whether CT has been notified yet. The `mergePositions` call doesn't require CT to know the resolution — it just requires the outcome tokens to be mergeable, which they are until `reportPayouts` is called.

    Actually wait — this needs to be more careful. Let me reread the baseline behaviour.

    Looking at the baseline `remove_liquidity.py::_calculate_amounts`, the merge math uses `FPMM.get_balance` and `FPMM.get_total_supply` which are FPMM-only reads, plus `ConditionalTokens.get_user_holdings` for the outcome tokens already in the safe. **None of these depend on whether CT has been resolved.** The merge tx itself is `mergePositions(collateralToken, parentCollectionId, conditionId, partition, amount)` — this requires the condition to **not** be resolved on CT, because a resolved condition can't have its positions merged (only redeemed).

    So the correct state 3 / 4 boundary is based on `ConditionalTokens.payoutNumerators(conditionId)`, not on `answerFinalizedTimestamp`. If `payoutNumerators` is all zeros, merge is allowed; if any slot is non-zero, merge is not allowed and we need the remove-only path.

    **Revised decision**: state 3 / 4 boundary is determined by an on-chain read of `ConditionalTokens.check_resolved(conditionId)`. If the condition is resolved on CT, we're in state 4 (remove only). If the Realitio question is finalized but the CT condition is not yet resolved, we're in state 3 (remove and merge — the merge still works because CT hasn't been told yet).

    This is an additional on-chain read per market but it's the correct way to distinguish the two states. Add to the plan: the `_classify_market` helper needs to be a generator that can `yield from` the `check_resolved` call, not a pure function. This is fine — behaviours are generators throughout.

    ```python
    def _classify_market(
        self, fpmm: Dict[str, Any], now: int
    ) -> Generator[None, None, str]:
        opening_ts = int(fpmm["openingTimestamp"])
        lead_time = self.params.liquidity_removal_lead_time

        if now < opening_ts - lead_time:
            return "skip"

        # We're in state 2, 3, or 4. Distinguish 4 from 2/3 via on-chain read.
        condition_id = fpmm["condition_id"]
        resolved = yield from self._check_resolved(condition_id)
        if resolved:
            return "remove_only"
        return "remove_and_merge"
    ```

    This adds a `_check_resolved` helper (verbatim from baseline `redeem_positions.py`) that this skill needs. It's a CT contract read. This skill's `base.py` therefore also needs the `conditional_tokens_subgraph`? No — `check_resolved` is a contract read, not a subgraph query. It uses `get_contract_api_response` which any behaviour has access to. So `base.py` does NOT need a CT subgraph helper, just the existing contract-call plumbing.

2. **Should `remove_liquidity_batch_size` be renamed to `fpmm_remove_liquidity_batch_size`?** Per the consistency reasoning in [omen_ct_redeem_skill.md](omen_ct_redeem_skill.md), yes. The current name is a baseline artifact. Rename during step 3 of the migration.

3. **Log format**: suggested prefix `[OmenFpmmRemoveLiquidity]`.

4. **Is the one-period latency on state 4 markets an issue?** Only if the composition runs LP remove and CT redeem in the same period AND the subgraph lag matters. In practice the latency is ~5 minutes (one period) and is invisible to operators. Not a concern for production.

## References

- Baseline file: [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/remove_liquidity.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/remove_liquidity.py)
- Helper borrowed from: [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py::_check_resolved`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py)
- Overview plan: [omen_funds_recoverer_split.md](omen_funds_recoverer_split.md)
- Ecosystem primer: [ct_omen_realitio.md](../docs/ct_omen_realitio.md)
