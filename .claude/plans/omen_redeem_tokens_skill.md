# Plan — `omen_ct_redeem_tokens_abci` skill

**Part of:** [omen_funds_recoverer_split.md](omen_funds_recoverer_split.md) (read the overview first for shared design decisions)
**Baseline reference:** [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py) — the tx-building logic of the new skill is equivalent to this file's `RedeemPositionsBehaviour`

## Purpose

Call `ConditionalTokens.redeemPositions(...)` for the safe's winning outcome positions on finalized prediction markets. Optionally prepend `RealitioProxy.resolve(...)` to the multisend if the market's condition has not yet been reported on the Conditional Tokens contract.

This is the skill for **traders** — actors who bought outcome shares on an FPMM and want to convert their winning shares back into wxDAI after the market resolves.

## Who calls what in this flow

```text
trader safe buys YES shares on FPMM
                  │
                  ▼
    [market's Realitio question finalizes]
                  │
                  ▼
    [someone calls RealitioProxy.resolve(questionId)]
                  │   (can be this skill or anyone else)
                  ▼
    [ConditionalTokens.reportPayouts is called by RealitioProxy]
                  │
                  ▼
   trader safe calls ConditionalTokens.redeemPositions(
       collateralToken, parentCollectionId, conditionId, indexSets)
                  │
                  ▼
    wxDAI returned to the trader safe's wallet
```

The skill's job is to detect winning positions, ensure the `reportPayouts` step has happened (calling `resolve` if not), and submit the `redeemPositions` tx for the winning index sets.

## What this skill does NOT do

- Does NOT call `Realitio.claimWinnings` or `Realitio.withdraw`. That's the **answerer** flow, handled by [omen_realitio_withdraw_bond_abci](omen_realitio_bond_withdraw_skill.md). `redeemPositions` and `claimWinnings` are independent contract flows on independent contracts — a trader never needs to claim Realitio bonds because a trader never posts Realitio answers.
- Does NOT call `FPMM.removeFunding` or `ConditionalTokens.mergePositions`. That's the **LP** flow, handled by [omen_fpmm_remove_liquidity_abci](omen_fpmm_liquidity_remove_skill.md).

## Trigger conditions

The skill produces a multisend when **at least one** of the safe's outstanding ConditionalTokens positions meets all of:

1. `userPosition.balance > 0` — the safe currently holds outcome tokens
2. The position belongs to a condition whose Omen FPMM has `answerFinalizedTimestamp != null` — the market has resolved on Realitio
3. The held index set corresponds to a winning outcome, determined by `fpmm.payouts[idx] > 0` for at least one `idx` in `held_index_sets`

If no position meets all three, the skill emits an empty payload (`tx_hash=None`) and routes to `FinishedWithoutCtRedeemTokensTxRound`.

## Subgraphs used

Two subgraphs, same as the current baseline behaviour:

1. **Conditional Tokens subgraph** (`https://conditional-tokens.subgraph.autonolas.tech`) — fetches `user($safe).userPositions(balance_gt: "0")` to discover which positions the safe holds
2. **Omen subgraph** (`9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz` on TheGraph decentralized network) — fetches `fixedProductMarketMakers` filtered by `conditions_.id_in: [...]` to check which of those conditions have finalized and with what payout vector

The two queries are cross-referenced in Python to produce the set of (condition_id, winning_index_sets) pairs the safe can redeem.

## Contracts used

| Contract | Role | Methods called |
|---|---|---|
| `ConditionalTokens` | Primary | `check_resolved` (read), `build_redeem_positions_tx` (write), `get_partitions` (local helper) |
| `RealitioProxy` | Secondary | `build_resolve_tx` (write, only when `check_resolved` returns False) |
| `Multisend` | Wrapping | `get_tx_data` to bundle the per-market txs |
| `GnosisSafe` | Settlement | `get_raw_safe_transaction_hash` to produce the hash for TxSettlement |

## File structure

```text
packages/valory/skills/omen_ct_redeem_tokens_abci/
├── __init__.py                    # PUBLIC_ID definition
├── skill.yaml                     # dependencies, params, subgraph models, round_behaviour
├── fsm_specification.yaml         # regenerated from rounds.py by autonomy analyse fsm-specs
├── rounds.py                      # ~80 lines: Event, SynchronizedData, CtRedeemTokensRound, 2 final states, AbciApp
├── payloads.py                    # ~15 lines: CtRedeemTokensPayload(tx_submitter, tx_hash)
├── models.py                      # ~80 lines: CtRedeemTokensParams, SharedState, CtSubgraph, OmenSubgraph
├── handlers.py                    # boilerplate
├── dialogues.py                   # boilerplate
├── behaviours/
│   ├── __init__.py
│   ├── base.py                    # ~150 lines: CtRedeemTokensBaseBehaviour with only the helpers this skill uses
│   ├── behaviour.py               # ~300 lines: CtRedeemTokensBehaviour with _prepare_multisend + helpers
│   └── round_behaviour.py         # ~20 lines: CtRedeemTokensRoundBehaviour wiring
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_payloads.py
    ├── test_rounds.py
    ├── test_handlers.py
    ├── test_dialogues.py
    └── behaviours/
        ├── __init__.py
        ├── conftest.py
        ├── test_base.py
        ├── test_behaviour.py
        └── test_round_behaviour.py
```

## FSM

### Rounds

```python
class Event(Enum):
    DONE = "done"
    NONE = "none"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(TxSynchronizedData):
    # No custom fields. Only the inherited tx_submitter and most_voted_tx_hash.
    ...


class CtRedeemTokensRound(CollectSameUntilThresholdRound):
    payload_class = CtRedeemTokensPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = "participant_to_ct_redeem_tokens_tx"


class FinishedWithCtRedeemTokensTxRound(DegenerateRound):
    """Routed to TxSettlement in the parent composition."""


class FinishedWithoutCtRedeemTokensTxRound(DegenerateRound):
    """Routed to the next skill in the parent composition, skipping TxSettlement."""


class OmenCtRedeemTokensAbciApp(AbciApp[Event]):
    initial_round_cls = CtRedeemTokensRound
    initial_states = {CtRedeemTokensRound}
    transition_function = {
        CtRedeemTokensRound: {
            Event.DONE: FinishedWithCtRedeemTokensTxRound,
            Event.NONE: FinishedWithoutCtRedeemTokensTxRound,
            Event.NO_MAJORITY: FinishedWithoutCtRedeemTokensTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutCtRedeemTokensTxRound,
        },
        FinishedWithCtRedeemTokensTxRound: {},
        FinishedWithoutCtRedeemTokensTxRound: {},
    }
    final_states = {FinishedWithCtRedeemTokensTxRound, FinishedWithoutCtRedeemTokensTxRound}
    event_to_timeout = {Event.ROUND_TIMEOUT: 120.0}
    db_post_conditions = {
        FinishedWithCtRedeemTokensTxRound: {get_name(SynchronizedData.most_voted_tx_hash)},
        FinishedWithoutCtRedeemTokensTxRound: set(),
    }
```

### Payload

```python
@dataclass(frozen=True)
class CtRedeemTokensPayload(BaseTxPayload):
    tx_submitter: Optional[str] = None  # "omen_ct_redeem" when tx_hash is set
    tx_hash: Optional[str] = None       # None when there's nothing to redeem
```

### Transition summary

One round, two exits. When the behaviour produces a non-None `tx_hash`, the round's consensus value is `(tx_submitter="omen_ct_redeem", tx_hash="0x...")` and the round emits `DONE` → `FinishedWithCtRedeemTokensTxRound`. When the behaviour produces `None`, the consensus value is `(None, None)` and the round emits `NONE` → `FinishedWithoutCtRedeemTokensTxRound`. `NO_MAJORITY` and `ROUND_TIMEOUT` both route to `FinishedWithoutCtRedeemTokensTxRound` (fail-safe: skip this period, try again next).

## Behaviour structure

### Entry point (identical shape across all three skills)

```python
class CtRedeemTokensBehaviour(CtRedeemTokensBaseBehaviour):
    """Build a multisend that redeems the next batch of winning CT positions."""

    matching_round = CtRedeemTokensRound

    def async_act(self) -> Generator:
        """Single-round act: query → build → wrap → settle-or-skip."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash = yield from self._prepare_multisend()
            tx_submitter = "omen_ct_redeem" if tx_hash is not None else None
            payload = CtRedeemTokensPayload(
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
    """The full CT redemption pipeline as a linear recipe."""
    # Step 1: find what the safe holds
    held_positions = yield from self._get_held_positions()
    if not held_positions:
        self.context.logger.info(f"{LOG_PREFIX} no CT positions held by safe")
        return None

    # Step 2: find which conditions those positions belong to that have resolved
    redeemable = yield from self._get_redeemable_markets(held_positions)
    if not redeemable:
        self.context.logger.info(
            f"{LOG_PREFIX} safe holds {len(held_positions)} positions but "
            f"none have resolved to a winning payout"
        )
        return None

    # Step 3: build the individual per-market txs (with optional resolve prepended)
    txs = yield from self._build_redeem_txs(redeemable)
    if not txs:
        return None

    # Step 4: wrap in a multisend and compute the safe tx hash
    tx_hash = yield from self._to_multisend(txs)
    if tx_hash is None:
        self.context.logger.warning(f"{LOG_PREFIX} multisend build failed")
        return None

    self.context.logger.info(
        f"{LOG_PREFIX} prepared multisend with {len(txs)} tx(s) "
        f"for {len(redeemable)} market(s)"
    )
    return tx_hash
```

### Helpers (each ≤~40 lines)

- `_get_held_positions()` — paginated CT subgraph query, returns `Dict[condition_id, Set[index_set]]`. Lifted verbatim from baseline `redeem_positions.py::_get_held_positions`.
- `_get_redeemable_markets(held)` — Omen subgraph query for finalized markets matching the held condition IDs, filters by winning payout, returns `List[market_dict]`. Lifted from baseline `_get_markets_for_conditions` + `_has_winning_position`.
- `_build_redeem_txs(markets)` — iterates markets up to `redeem_positions_batch_size`, for each: calls `_check_resolved`; if not resolved, prepends `_get_resolve_tx`; then calls `_get_redeem_positions_tx`. Lifted from baseline `_build_redeem_positions_txs`.
- `_check_resolved(condition_id)` — contract read. Lifted verbatim.
- `_get_resolve_tx(market)` — contract build tx. Lifted verbatim.
- `_get_redeem_positions_tx(condition_id, index_sets)` — contract build tx. Lifted verbatim.

All six helpers exist in the current baseline at [`redeem_positions.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py) and move verbatim except for import path updates.

## Parameters

Subset of the current `OmenFundsRecovererParams`, only what this skill uses:

```yaml
redeem_positions_batch_size: 5                # unchanged from baseline
conditional_tokens_contract: "0x..."          # unchanged
realitio_oracle_proxy_contract: "0x..."       # unchanged (needed for resolve path)
collateral_tokens_contract: "0x..."           # unchanged (wxDAI address)
multisend_address: "0x..."                    # inherited from BaseParams
```

**Parameters NOT carried over**: `liquidity_removal_lead_time`, `remove_liquidity_batch_size`, `claim_bonds_batch_size`, `min_realitio_withdraw_balance`, `realitio_start_block`, `realitio_contract`. Those belong to the other two skills.

## Base behaviour helpers

`CtRedeemTokensBaseBehaviour` provides only what this skill uses:

```python
class CtRedeemTokensBaseBehaviour(BaseBehaviour, ABC):
    # Type-cast properties
    @property
    def synchronized_data(self) -> SynchronizedData: ...
    @property
    def params(self) -> CtRedeemTokensParams: ...
    @property
    def last_synced_timestamp(self) -> int: ...
    @property
    def shared_state(self) -> SharedState: ...

    # Subgraph helpers (only the two this skill uses)
    def get_conditional_tokens_subgraph_result(self, query: str) -> Generator[None, None, Optional[Dict[str, Any]]]: ...
    def get_omen_subgraph_result(self, query: str) -> Generator[None, None, Optional[Dict[str, Any]]]: ...

    # Multisend helpers
    def _get_safe_tx_hash(self, to_address, data, value=0, operation=CALL) -> Generator[None, None, Optional[str]]: ...
    def _to_multisend(self, transactions: List[Dict]) -> Generator[None, None, Optional[str]]: ...
```

Helpers it does NOT carry (which are in the monolith base.py):

- `get_realitio_subgraph_result` — only used by `omen_realitio_withdraw_bond_abci`

This is per design decision 3 of the overview — accept duplication across skills in exchange for full independence.

## Tests to port

From the current monolith's test suite:

| Current location | New location |
|---|---|
| `tests/behaviours/test_redeem_positions.py` | `omen_ct_redeem_tokens_abci/tests/behaviours/test_behaviour.py` |
| `tests/behaviours/test_base.py` (relevant portions) | `omen_ct_redeem_tokens_abci/tests/behaviours/test_base.py` |
| `tests/behaviours/conftest.py` | `omen_ct_redeem_tokens_abci/tests/behaviours/conftest.py` (CT + Omen subgraph fixtures only) |
| `tests/test_rounds.py` (the `RedeemPositionsRound` portion) | `omen_ct_redeem_tokens_abci/tests/test_rounds.py` |
| `tests/test_models.py` (the `redeem_positions_batch_size` assertions) | `omen_ct_redeem_tokens_abci/tests/test_models.py` |
| `tests/test_payloads.py` | `omen_ct_redeem_tokens_abci/tests/test_payloads.py` (adapted to the new payload shape) |

**Equivalence assertion**: add a new test `test_tx_output_matches_baseline` that takes a fixed mocked-subgraph + mocked-contract-read input, runs both `CtRedeemTokensBehaviour._prepare_multisend` and a copy of the baseline `RedeemPositionsBehaviour._build_redeem_positions_txs + BuildMultisendBehaviour._build_multisend`, and asserts the produced safe tx hash (or None) is equal. This is the operational check for the equivalence invariant from the overview.

**Intentional behavioural differences from baseline**: none. This skill's tx-production is a straight lift of the current `RedeemPositionsBehaviour` + `BuildMultisendBehaviour`, fused into one round.

## Handling the safe tx hash computation

In the current monolith, the safe tx hash is computed in `BuildMultisendBehaviour` after all three recovery flows have appended their txs to `funds_recovery_txs`. The hash is computed over the *combined* multisend.

In the new skill, the safe tx hash is computed over this skill's **own** multisend (which contains only CT redeem txs, optionally preceded by resolve calls). The hash value is therefore *different* from what the monolith would produce for the same inputs — because the monolith's hash covers all three flows' txs, not just this one.

This is an **expected** difference and doesn't violate the equivalence invariant. The equivalence invariant is about tx *dicts* (`[{"to", "data", "value"}, ...]`), not about the wrapped multisend hash. Each new skill produces a *subset* of the monolith's tx dicts, wraps that subset in its own multisend, and gets its own hash.

## Round timeout

120 seconds, inherited from the current monolith's `round_timeout_seconds: 120.0` default (set in an earlier session to handle slow RPC responses from Gnosis public nodes). Can be tuned down after the first production deployment of the split version shows it's unnecessary.

## Open questions specific to this skill

1. **Should `redeem_positions_batch_size` be renamed to `ct_redeem_tokens_batch_size`?** The current name has `redeem_positions` because it was the behaviour name in the monolith. In the new skill the name would be more consistent as `ct_redeem_tokens_batch_size`. Decision: rename it during step 1 of the migration. Low risk because the param is only consumed inside this skill.

2. **Should the skill retry on `NO_MAJORITY`?** Current plan is to route `NO_MAJORITY` to `FinishedWithoutCtRedeemTokensTxRound`, which means "skip this period, try again next." Alternative is to retry in the same period with a slight delay. I'd stick with the current plan because OA's standard pattern for `NO_MAJORITY` is to advance and retry on the next period; in-round retries are rare and add complexity.

3. **Log format**: the current monolith prefixes all logs with `[OmenFundsRecoverer]`. The new skill should use a distinct prefix. Suggested: `[OmenCtRedeem]`. The per-skill prefix makes it easy to filter propel logs for just this skill's activity.

## References

- Baseline file: [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/redeem_positions.py)
- Overview plan: [omen_funds_recoverer_split.md](omen_funds_recoverer_split.md)
- Ecosystem primer: [ct_omen_realitio.md](../docs/ct_omen_realitio.md)
