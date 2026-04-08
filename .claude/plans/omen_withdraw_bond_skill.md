# Plan — `omen_realitio_withdraw_bond_abci` skill

**Part of:** [omen_funds_recoverer_split.md](omen_funds_recoverer_split.md) (read the overview first for shared design decisions)
**Baseline reference:** [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/claim_bonds.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/claim_bonds.py) — the tx-building logic of the new skill is equivalent to this file's `ClaimBondsBehaviour`, which itself is the result of a six-fix cascade documented in [claim_bonds_fix.md](claim_bonds_fix.md)

## Purpose

Call `Realitio.claimWinnings(...)` for the safe's unclaimed bond positions on finalized Realitio questions, followed by `Realitio.withdraw()` to sweep the safe's internal Realitio balance into its wallet as xDAI.

This is the skill for **answerers** — actors who posted answers to Realitio questions and posted bonds defending those answers. When their answer wins, the bond and any takeover fees accrued during the answering process are owed to them. The recovery path involves two contract calls:

1. `claimWinnings` credits the owed amount to `Realitio.balanceOf(safe)` (an internal accounting ledger inside the Realitio contract, **not** the safe's actual xDAI balance)
2. `withdraw` transfers `balanceOf(safe)` from the internal ledger to the safe's wallet as actual xDAI

A single period of this skill may do one, the other, or both, depending on the current state of the backlog and the internal balance.

## Why the skill is named "bond_withdraw" and not "bond_claim"

The ecosystem vocabulary has both verbs and they mean different things. "Claiming" a bond credits the internal Realitio balance; "withdrawing" moves that balance to the wallet. From an operator's perspective, the user-visible outcome is the withdrawal — the xDAI landing in the safe. The claim is an intermediate step that happens inside the Realitio contract.

The name emphasizes the user-visible outcome. The skill still calls both `claimWinnings` and `withdraw` internally.

## Who calls what in this flow

```text
answerer safe posts answer + bond to Realitio.submitAnswer(questionId, ...)
                  │
                  ▼
    [question finalizes on Realitio]
                  │
                  ▼
    [no automatic crediting happens — the bonds sit in the question's
     history until someone calls claimWinnings]
                  │
                  ▼
   answerer safe calls Realitio.claimWinnings(
       questionId, history_hashes, addrs, bonds, answers)
                  │   (requires reverse-chronological 4-tuple, see
                  │    baseline _assemble_claim_params)
                  ▼
    Realitio.balanceOf(safe) credited with the owed amount
                  │
                  ▼
   answerer safe calls Realitio.withdraw()
                  │
                  ▼
    xDAI transferred from Realitio.balanceOf(safe) to safe's wallet
```

The key complication — and the reason this skill has a long history of bug fixes — is that reconstructing the `(history_hashes, addrs, bonds, answers)` 4-tuple for `claimWinnings` is non-trivial. The Realitio contract walks this in reverse chronological order and verifies a running hash chain, so the input has to be constructed in exactly the right shape or the call reverts. See [claim_bonds_failure_analysis.md](../docs/claim_bonds_failure_analysis.md) for the full forensic investigation.

## Prior work this skill inherits verbatim

This skill has the most history of the three. Every non-obvious fix from the earlier sessions must be preserved:

### From [claim_bonds_fix.md](claim_bonds_fix.md)

1. **Fix A — decouple withdraw from claim**: the behaviour builds the optional `withdraw` tx *first*, then appends claim txs, so the withdraw step runs every period regardless of whether the claim loop has anything to do. This preserves the ability to sweep a non-zero `Realitio.balanceOf` even on periods where no new bonds are claimable.

2. **Fix B — `first: $realitio_withdraw_bond_batch_size` subgraph query ordered `id desc`**: the subgraph query never paginates; it always returns at most `realitio_withdraw_bond_batch_size` entries ordered newest-first. Dramatically reduces per-round work and avoids the "stuck on the same broken item at the head of the id space" failure mode. (The baseline monolith calls this parameter `claim_bonds_batch_size`; renamed in the new skill to match the skill name.)

3. **Fix C — per-question `from_block = createdBlock - 1`**: the `eth_getLogs` window for reconstructing `LogNewAnswer` events is bounded to each question's individual lifetime instead of scanning from block 0. Reduces RPC cost by ~1000×.

4. **Fix D — `realitio_start_block` removed entirely**: formerly a parameter at the global level with default 17000000. No longer needed after Fix C. Will be deleted from `models.py` and `skill.yaml` in the new skill.

5. **Fix E — `historyHash_not` filter in the subgraph query**: excludes already-claimed questions at query time so a just-claimed batch doesn't re-appear in the next period's query and dead-cycle the skill.

6. **Fix F — dedup by question id**: the same question may appear in multiple response rows; dedup prevents building N-1 useless claim txs per question (all but one of which would revert on-chain because the first one clears the history hash).

### From [realitio_contract_upstream_fix.md](realitio_contract_upstream_fix.md)

- **The `_assemble_claim_params` helper** in the current `claim_bonds.py` converts the contract wrapper's raw `LogNewAnswer` event list into the reverse-chronological 4-tuple the contract expects. This is the calldata-shape bug fix that originally made the skill work in production. It moves verbatim into the new skill's `base.py` (promoted from the behaviour file to the base for testability).

All six fixes transfer verbatim. **None of them can be accidentally regressed during the refactor** — the equivalence-to-baseline tests from the overview plan are specifically the check for this.

## Trigger conditions

The skill produces a multisend when either:

1. **`Realitio.balanceOf(safe) >= min_realitio_withdraw_balance`** → the safe has enough internal balance to be worth withdrawing. This produces a `withdraw()` tx.
2. **At least one unclaimed, finalized response from the safe exists in the Realitio subgraph** → produces up to `realitio_withdraw_bond_batch_size` `claimWinnings(...)` txs.

These two conditions are independent. A given period may trigger:

- Both: balance is above threshold AND there are new claimable questions → produces `[withdraw, claim_1, claim_2, ..., claim_N]`
- Only withdraw: balance is above threshold, no new claimables → produces `[withdraw]`
- Only claim: balance is below threshold, new claimables exist → produces `[claim_1, ..., claim_N]` (the claims will push the balance up; the next period's withdraw sweeps it)
- Neither: no tx, skill emits `tx_hash=None` and routes to `FinishedWithoutRealitioWithdrawBondTxRound`

## Subgraphs used

One subgraph only:

1. **Realitio subgraph** (`https://realitio.subgraph.autonolas.tech` or the decentralized network equivalent `E7ymrCnNcQdAAgLbdFWzGE5mvr5Mb5T9VfT43FqA7bNh`) — fetches `responses(user: $safe, question_.answerFinalizedTimestamp_gt: 0, question_.historyHash_not: "0x00...")` ordered by `id` descending, limited to `realitio_withdraw_bond_batch_size`

The question's `createdBlock` is read from the subgraph result and used as the per-question `from_block` lower bound for the contract's `eth_getLogs` window (Fix C above).

## Contracts used

| Contract | Role | Methods called |
|---|---|---|
| `Realitio` | Primary | `balance_of` (read), `get_claim_params` (read), `simulate_claim_winnings` (read), `build_claim_winnings` (write), `build_withdraw_tx` (write) |
| `Multisend` | Wrapping | `get_tx_data` |
| `GnosisSafe` | Settlement | `get_raw_safe_transaction_hash` |

Note that `Realitio.get_claim_params` is the contract wrapper's name for what is internally an `eth_getLogs` call on `LogNewAnswer` events. It does not map to a Solidity method; it's a Python-side helper on the contract wrapper. The new skill calls it through the same API as the current monolith, with the per-question `from_block` plumbed through.

## File structure

```text
packages/valory/skills/omen_realitio_withdraw_bond_abci/
├── __init__.py                    # PUBLIC_ID definition
├── skill.yaml                     # dependencies, params, realitio_subgraph model, round_behaviour
├── fsm_specification.yaml
├── rounds.py                      # ~80 lines: Event, SynchronizedData, RealitioWithdrawBondRound, 2 final states, AbciApp
├── payloads.py                    # ~15 lines: RealitioWithdrawBondPayload
├── models.py                      # ~80 lines: RealitioWithdrawBondParams, SharedState, RealitioSubgraph
├── handlers.py
├── dialogues.py
├── behaviours/
│   ├── __init__.py
│   ├── base.py                    # ~200 lines: base behaviour + the promoted _assemble_claim_params helper
│   ├── behaviour.py               # ~350 lines: RealitioWithdrawBondBehaviour with _prepare_multisend + helpers
│   └── round_behaviour.py         # boilerplate
└── tests/...
```

This skill's `behaviours/base.py` is the largest of the three because it hosts `_assemble_claim_params`, which was previously in the behaviour file. Promoting it to the base has two benefits:

1. **Testability**: unit-testing `_assemble_claim_params` doesn't require instantiating a full behaviour with mocked round context. It's a pure function and can be tested as one.
2. **Future reuse**: if we ever extract a library skill or upstream this to the trader repo (per [realitio_contract_upstream_fix.md](realitio_contract_upstream_fix.md)), the helper is in a more natural location.

## FSM

Same shape as the CT redeem skill. One consensus round, two final states:

```python
class RealitioWithdrawBondRound(CollectSameUntilThresholdRound):
    payload_class = RealitioWithdrawBondPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    selection_key = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = "participant_to_realitio_withdraw_bond_tx"


class FinishedWithRealitioWithdrawBondTxRound(DegenerateRound): ...
class FinishedWithoutRealitioWithdrawBondTxRound(DegenerateRound): ...


class OmenRealitioWithdrawBondAbciApp(AbciApp[Event]):
    initial_round_cls = RealitioWithdrawBondRound
    initial_states = {RealitioWithdrawBondRound}
    transition_function = {
        RealitioWithdrawBondRound: {
            Event.DONE: FinishedWithRealitioWithdrawBondTxRound,
            Event.NONE: FinishedWithoutRealitioWithdrawBondTxRound,
            Event.NO_MAJORITY: FinishedWithoutRealitioWithdrawBondTxRound,
            Event.ROUND_TIMEOUT: FinishedWithoutRealitioWithdrawBondTxRound,
        },
        FinishedWithRealitioWithdrawBondTxRound: {},
        FinishedWithoutRealitioWithdrawBondTxRound: {},
    }
    final_states = {FinishedWithRealitioWithdrawBondTxRound, FinishedWithoutRealitioWithdrawBondTxRound}
    event_to_timeout = {Event.ROUND_TIMEOUT: 120.0}
```

## Behaviour structure

### Entry point

Identical shape to the CT redeem skill — the differences are only in `_prepare_multisend`.

```python
class RealitioWithdrawBondBehaviour(RealitioWithdrawBondBaseBehaviour):
    """Build a multisend that claims Realitio bonds and/or withdraws internal balance."""

    matching_round = RealitioWithdrawBondRound

    def async_act(self) -> Generator:
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash = yield from self._prepare_multisend()
            tx_submitter = "omen_realitio_bond_withdraw" if tx_hash is not None else None
            payload = RealitioWithdrawBondPayload(
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

Note the important ordering: **withdraw first, claims second**. This is Fix A from the history.

```python
def _prepare_multisend(self) -> Generator[None, None, Optional[str]]:
    """Query + build optional withdraw + build claims + wrap in multisend."""
    txs: List[Dict[str, Any]] = []

    # Step 1 (Fix A): check balanceOf and optionally build withdraw FIRST
    # so a broken or empty claim loop doesn't starve the withdraw.
    withdraw_tx = yield from self._maybe_build_withdraw_tx()
    if withdraw_tx is not None:
        txs.append(withdraw_tx)

    # Step 2: build claim txs for unclaimed finalized responses
    claim_txs = yield from self._build_claim_txs()
    txs.extend(claim_txs)

    if not txs:
        self.context.logger.info(f"{LOG_PREFIX} nothing to withdraw or claim this period")
        return None

    # Step 3: wrap in a multisend and compute the safe tx hash
    tx_hash = yield from self._to_multisend(txs)
    if tx_hash is None:
        self.context.logger.warning(f"{LOG_PREFIX} multisend build failed")
        return None

    n_claims = len(claim_txs)
    has_withdraw = withdraw_tx is not None
    self.context.logger.info(
        f"{LOG_PREFIX} prepared multisend: withdraw={has_withdraw}, claims={n_claims}"
    )
    return tx_hash
```

### Helpers (all lifted from baseline `claim_bonds.py`, with minor adjustments)

- `_maybe_build_withdraw_tx()` — reads `balance_of(safe)`, builds `build_withdraw_tx` if above `min_realitio_withdraw_balance`, otherwise returns None. Verbatim from baseline.
- `_get_claimable_responses()` — single Realitio subgraph query with Fix E filter. Verbatim from baseline.
- `_build_claim_txs()` — iterates responses up to `realitio_withdraw_bond_batch_size`, dedups by question id (Fix F), calls `_try_build_single_claim` per unique question. Verbatim.
- `_try_build_single_claim(response)` — extracts `question_id_hex` + `createdBlock`, calls `_get_claim_params(from_block=created_block - 1)`, then `_simulate_claim`, then `_build_claim_tx`. Verbatim except for the fact that `_assemble_claim_params` now lives in `base.py` instead of being a module-level helper.
- `_get_claim_params(question_id, from_block)` — calls the contract wrapper and applies `_assemble_claim_params` to the result. Verbatim.
- `_simulate_claim(question_id, claim_params)` — eth_call against `claimWinnings` to validate the calldata before building the tx. Verbatim.
- `_build_claim_tx(question_id, claim_params)` — builds the calldata. Verbatim.

The base helper (promoted from behaviour file to `base.py`):

- `_assemble_claim_params(answered: List[Dict]) -> ClaimParamsType` — the calldata-shape fix from [realitio_contract_upstream_fix.md](realitio_contract_upstream_fix.md). Takes the raw `LogNewAnswer` event list (chronological, as returned by the contract wrapper) and returns the reverse-chronological 4-tuple `(history_hashes, addresses, bonds, answers)` that `Realitio.claimWinnings` expects. Pure function, no I/O.

## Parameters

Subset of the current `OmenFundsRecovererParams`, only what this skill uses:

```yaml
realitio_withdraw_bond_batch_size: 10         # renamed from claim_bonds_batch_size
min_realitio_withdraw_balance: 10000000000000000000  # 10 xDAI, unchanged
realitio_contract: "0x..."                    # unchanged
multisend_address: "0x..."                    # inherited from BaseParams
```

**Renamed from baseline**: `claim_bonds_batch_size` → `realitio_withdraw_bond_batch_size`. The rename aligns the parameter name with the new skill name (`omen_realitio_withdraw_bond_abci`). The semantics are unchanged — it still caps the number of `claimWinnings` calls bundled into a single multisend per period. The rename happens during migration step 2 and requires updating the default in `skill.yaml`, the `_ensure` call in `models.py`, and any operator env var overrides (`CLAIM_BONDS_BATCH_SIZE` → `REALITIO_BOND_WITHDRAW_BATCH_SIZE`) in downstream service configs.

**Parameters NOT carried over**: `liquidity_removal_lead_time`, `remove_liquidity_batch_size` (→ `fpmm_remove_liquidity_batch_size` in the LP skill), `redeem_positions_batch_size` (→ `ct_redeem_tokens_batch_size` in the CT skill), `conditional_tokens_contract`, `realitio_oracle_proxy_contract`, `collateral_tokens_contract`. Those belong to the other two skills.

**`realitio_start_block` is deleted.** Fix C ([claim_bonds_fix.md](claim_bonds_fix.md)) made it redundant. The per-question `from_block = createdBlock - 1` is computed from the subgraph query result, not from a global parameter. Keeping the param would be misleading.

## Base behaviour helpers

`RealitioWithdrawBondBaseBehaviour` provides:

```python
class RealitioWithdrawBondBaseBehaviour(BaseBehaviour, ABC):
    # Type-cast properties
    @property
    def synchronized_data(self) -> SynchronizedData: ...
    @property
    def params(self) -> RealitioWithdrawBondParams: ...
    @property
    def last_synced_timestamp(self) -> int: ...
    @property
    def shared_state(self) -> SharedState: ...

    # Subgraph helper (only the one this skill uses)
    def get_realitio_subgraph_result(self, query: str) -> Generator[None, None, Optional[Dict[str, Any]]]: ...

    # Multisend helpers
    def _get_safe_tx_hash(self, to_address, data, value=0, operation=CALL) -> Generator[None, None, Optional[str]]: ...
    def _to_multisend(self, transactions: List[Dict]) -> Generator[None, None, Optional[str]]: ...
```

Plus the promoted module-level function:

```python
def _assemble_claim_params(answered: List[Dict[str, Any]]) -> ClaimParamsType:
    """Reshape a chronological LogNewAnswer event list into the reverse-chronological
    4-tuple expected by Realitio.claimWinnings."""
    ...
```

The helper is at module level (not a method on the base class) because it's a pure function with no access to `self` and unit-testing it directly is easier when it's a free function.

## Tests to port

| Current location | New location |
|---|---|
| `tests/behaviours/test_claim_bonds.py` | `omen_realitio_withdraw_bond_abci/tests/behaviours/test_behaviour.py` |
| `tests/behaviours/test_base.py` (relevant portions + `_assemble_claim_params` tests) | `omen_realitio_withdraw_bond_abci/tests/behaviours/test_base.py` |
| `tests/behaviours/conftest.py` | `omen_realitio_withdraw_bond_abci/tests/behaviours/conftest.py` (Realitio subgraph fixtures only) |
| `tests/test_rounds.py` (the `ClaimBondsRound` portion) | `omen_realitio_withdraw_bond_abci/tests/test_rounds.py` |
| `tests/test_models.py` (the `claim_bonds_batch_size` + `min_realitio_withdraw_balance` assertions) | `omen_realitio_withdraw_bond_abci/tests/test_models.py` (update the assertions to use the renamed `realitio_withdraw_bond_batch_size`) |
| `tests/test_payloads.py` | `omen_realitio_withdraw_bond_abci/tests/test_payloads.py` |

The `_assemble_claim_params` tests (there are ~10 in the current test suite covering the 1-entry, 2-entry, 3-entry, bond-coerced-to-int cases) are particularly important to port verbatim because they encode the fix for the calldata-shape bug.

**Equivalence assertion**: add `test_tx_output_matches_baseline` that compares the new skill's multisend output against the baseline `ClaimBondsBehaviour + BuildMultisendBehaviour` output for a known fixed input.

**Intentional behavioural differences from baseline**: none. This skill's tx-production is a straight lift, with the only change being the physical location of `_assemble_claim_params` (module-level → base module).

## Handling `min_realitio_withdraw_balance`

The current monolith sets this to `10 xDAI = 10e18 wei` as the default. The earlier session also experimented with `1 xDAI = 1e18 wei` for the market-resolver deployment. The new skill preserves the current monolith's default (`10e18`) and leaves the operator to override it via env vars per deployment.

The param name is verbose but matches convention. Not renaming.

## Round timeout

120 seconds, same as the CT redeem skill. The Realitio contract's `get_claim_params` call is the slowest step in this skill (it's an `eth_getLogs` call) and 120s is generous enough to handle a batch of `realitio_withdraw_bond_batch_size=10` questions even on a slow public RPC. Can be tuned down after the first production deployment.

## Open questions specific to this skill

1. **Should `_assemble_claim_params` become a method on `RealitioWithdrawBondBaseBehaviour` instead of a module-level function?** I recommend module-level because it's a pure function and method-ifying it pulls in `self` for no reason. But the convention in the existing monolith is to have everything as behaviour methods. Decision: module-level, because it improves testability.

2. **Should the subgraph URL be sourced from a param or hardcoded in `skill.yaml`?** Current monolith has it as a param with a default in `skill.yaml`. Keep it as a param for operator override flexibility. No change.

3. **Log format**: suggested prefix `[OmenRealitioWithdrawBond]`. The prefix is long but matches the skill name exactly, which helps log filtering.

## References

- Baseline file: [`packages/valory/skills/omen_funds_recoverer_abci/behaviours/claim_bonds.py`](../../packages/valory/skills/omen_funds_recoverer_abci/behaviours/claim_bonds.py)
- The bug-fix history: [claim_bonds_fix.md](claim_bonds_fix.md)
- Forensic analysis: [claim_bonds_failure_analysis.md](../docs/claim_bonds_failure_analysis.md)
- Upstream contract context: [realitio_contract_upstream_fix.md](realitio_contract_upstream_fix.md)
- Overview plan: [omen_funds_recoverer_split.md](omen_funds_recoverer_split.md)
