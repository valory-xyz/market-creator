# Plan — Three single-purpose Omen recovery skills

**Status:** implemented
**Date:** 2026-04-08
**Scope:** market-creator only (market-creator FSM itself is NOT modified in this PR)

## TL;DR

Three independent single-purpose ABCI skills, each handling exactly one recovery flow for a specific actor in the Omen/CT/Realitio ecosystem:

1. **`omen_ct_redeem_tokens_abci`** — for traders holding winning `ConditionalTokens` outcome shares. Calls `ConditionalTokens.redeemPositions` (optionally preceded by `RealitioProxy.resolve` if the condition isn't yet reported on CT).
2. **`omen_realitio_withdraw_bond_abci`** — for answerers who posted Realitio bonds. Calls `Realitio.claimWinnings` per question and `Realitio.withdraw` to sweep the internal balance.
3. **`omen_fpmm_remove_liquidity_abci`** — for liquidity providers holding FPMM LP shares. Calls `FPMM.removeFunding`, with an optional follow-up `ConditionalTokens.mergePositions` when the market isn't resolved yet.

Per-skill details live in:

- [omen_redeem_tokens_skill.md](omen_redeem_tokens_skill.md)
- [omen_withdraw_bond_skill.md](omen_withdraw_bond_skill.md)
- [omen_remove_liquidity_skill.md](omen_remove_liquidity_skill.md)

## Why three skills

Three reasons, in decreasing order of importance:

1. **Three distinct actors, three distinct flows.** A trader buying outcome shares, an answerer posting Realitio bonds, and an LP providing FPMM liquidity are unrelated roles. They touch different contracts, read different subgraphs, and have different trigger conditions. Keeping the scaffolding isolated per skill makes each behaviour easy to read without cross-concern noise.

2. **True composability.** A "trader-only" service wants `omen_ct_redeem_tokens_abci` but not the other two. An "answerer-only" service wants only `omen_realitio_withdraw_bond_abci`. An LP management service wants only `omen_fpmm_remove_liquidity_abci`. Any subset is a valid composition.

3. **Per-skill cadence control.** Each skill can be composed into a parent FSM independently, so an operator can configure (for example) bond claiming to run every period but LP removal to run once per day.

## Design decisions

### 1. Naming: domain-verb, contract-anchored

Each skill is named `omen_<contract>_<verb>_<object>_abci`. The `<contract>` in the name is the *primary* contract the skill interacts with:

- `omen_ct_redeem_tokens_abci` → primary contract is `ConditionalTokens`, primary verb is `redeemPositions` on outcome-token positions
- `omen_realitio_withdraw_bond_abci` → primary contract is `Realitio`, object is "bond," verb emphasizes the user-visible outcome (`withdraw`). Internally the skill calls both `claimWinnings` and `withdraw`; the name emphasizes the second because it's the one that produces a wallet-visible balance change
- `omen_fpmm_remove_liquidity_abci` → primary contract is `FPMM`, verb is `removeFunding` (shortened to "remove" for brevity, "liquidity" is the object being removed). The secondary `ConditionalTokens.mergePositions` call is not named because it's conditional on market state

Reader contract: a new developer reading any skill name should be able to answer "which Solidity file do I read first to understand this skill?" — each name points at exactly one contract.

### 2. FSM architecture: each skill settles its own txs independently

Each skill owns its full FSM with **one consensus round** + **two final states**:

```text
omen_fpmm_remove_liquidity_abci          omen_ct_redeem_tokens_abci         omen_realitio_withdraw_bond_abci
┌─────────────────────────────┐         ┌──────────────────────┐           ┌──────────────────────────────┐
│  FpmmRemoveLiquidityRound   │         │   CtRedeemTokensRound│           │  RealitioWithdrawBondRound   │
│   ┌────┴────┐               │         │    ┌────┴────┐       │           │       ┌────┴────┐            │
│   │         │               │         │    │         │       │           │       │         │            │
│ with_tx  without_tx         │         │  with_tx  without_tx │           │    with_tx   without_tx      │
└────┬──────────┬─────────────┘         └────┬──────────┬──────┘           └───────┬──────────┬───────────┘
     │          │                            │          │                          │          │
     ▼          ▼                            ▼          ▼                          ▼          ▼
TxSettlement ──► CtRedeemTokens        TxSettlement ──► RealitioWithdrawBond  TxSettlement ──► next
                                                                                       (e.g. ResetPause
                                                                                       or MarketCreation)
```

When a skill produces a non-empty multisend, it routes to its `FinishedWith<X>TxRound`, which the parent composition maps to `TransactionSettlementAbci`. After settlement, the parent's `PostTransactionRound` router dispatches back to the *next* skill in the sequence based on `tx_submitter`.

When a skill produces no multisend (nothing to recover this period), it routes to its `FinishedWithout<X>TxRound`, which the parent composition maps directly to the next skill, skipping the settlement round-trip.

**Common-case cost**: in a quiet period with nothing to recover, all three skills route through their `Without<X>Tx` branches and the total overhead is three empty consensus rounds — no on-chain settlements at all. In a period where only one skill has work, only that skill's settlement runs. In a period where all three have work (e.g. a backlog drain after service downtime), all three settlements run sequentially.

**Explicitly rejected alternatives**:

- **Single shared accumulator round** (three collection rounds writing to a shared `funds_recovery_txs` sync-data field, drained by a fourth `BuildMultisendAbci` round): rejected because it's a cosmetic split — the "independent" skills would still depend on a shared synchronized-data field and must always be composed together, defeating the reusability goal.
- **Concurrent settlements** (each skill settles in parallel): rejected because OA composition is sequential, not parallel, and because concurrent settlements from the same safe would race on the safe nonce.

### 3. Per-skill `base.py` — no shared library skill

Each skill carries its own `behaviours/base.py` with only the helpers it actually needs. The three bases differ:

- `omen_ct_redeem_tokens_abci/behaviours/base.py` — CT subgraph helper + Omen subgraph helper + multisend helpers + type-cast properties
- `omen_realitio_withdraw_bond_abci/behaviours/base.py` — Realitio subgraph helper + multisend helpers + type-cast properties + the module-level `assemble_claim_params` helper
- `omen_fpmm_remove_liquidity_abci/behaviours/base.py` — Omen subgraph helper + multisend helpers + type-cast properties

**Duplication accepted**: the multisend helpers (`_to_multisend`, `_get_safe_tx_hash`) are identical across all three skills. Each skill gets its own copy. This is the tradeoff chosen in exchange for full skill independence — no cross-skill imports, no "library skill" to maintain.

**Explicitly rejected alternative**: a new `omen_recovery_base_abci` library skill that provides the shared helpers. Rejected because the helpers are few (~200 lines) and the per-skill copies give full reusability without coordination.

### 4. Single consensus round per skill

Each skill has exactly **one** consensus round that does query + build tx + multisend wrap + safe tx hash computation in a single behaviour, and produces a payload `{tx_submitter: Optional[str], tx_hash: Optional[str]}`.

Each skill owns its full pipeline end-to-end without any handoff through synchronized data.

**Consensus is still required.** The assumption is that agents running the same service image with the same config will reliably compute the same tx_hash (because subgraph lag is bounded, contract reads are deterministic, and the algorithm is pure), but the round is still a `CollectSameUntilThresholdRound`. The consensus step is the mechanism by which Tendermint commits the round's block and advances the FSM — it's architectural, not a sanity check. We just expect the "same" threshold to be hit reliably on the first attempt.

### 5. No shared sync-data across skills

Each skill's `SynchronizedData` exposes only:

- `tx_submitter: str` — which round submitted the latest settled tx
- `most_voted_tx_hash: str` — the latest settled tx hash

Both are standard TxSettlement fields inherited from `TxSynchronizedData`. No custom cross-skill fields.

### 6. Shared contract-address params via `kwargs.get`

`conditional_tokens_contract`, `collateral_tokens_contract`, `realitio_oracle_proxy_contract`, and `realitio_contract` are contract addresses that any subset of the three skills may need. When two skills are composed in the same `Params(MRO)`, both classes try to read the same kwargs key — but `self._ensure(...)` pops the key from kwargs, so the second class sees a KeyError.

Fix: each skill's `Params.__init__` reads these shared contract-address params via `kwargs.get("<key>")` + `enforce(not None, ...)` instead of `self._ensure(...)`. The value stays in kwargs for every class in the MRO. AEA's `SkillComponent.__init__` just logs a warning for leftover kwargs at the end of the MRO cascade — no error.

Per-skill private params (batch sizes, lead times, balance thresholds) still use `self._ensure(...)` normally.

### 7. `is_abstract: true`

All three skills are designed exclusively for composition. Their `skill.yaml` sets `is_abstract: true` so `abci_app_chain.chain(...)` accepts them as non-leaf apps. Running a sub-skill standalone is not supported.

### 8. Market-creator's `market_creation_manager_abci` FSM is NOT modified in this PR

This refactor is strictly confined to the three new recovery skills. The market-creator FSM (`packages/valory/skills/market_creation_manager_abci/`) and the composed `market_maker_abci` (`packages/valory/skills/market_maker_abci/composition.py`) are untouched. The three new skills are available for future composition but are not wired into any service in this PR.

## File structure

```text
packages/valory/skills/
├── omen_ct_redeem_tokens_abci/
│   ├── __init__.py
│   ├── skill.yaml
│   ├── fsm_specification.yaml
│   ├── rounds.py
│   ├── payloads.py
│   ├── models.py
│   ├── handlers.py
│   ├── dialogues.py
│   ├── behaviours/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── redeem_tokens.py
│   │   └── round_behaviour.py
│   └── tests/...
├── omen_fpmm_remove_liquidity_abci/
│   └── ... (same layout, behaviour file named remove_liquidity.py)
└── omen_realitio_withdraw_bond_abci/
    └── ... (same layout, behaviour file named withdraw_bond.py)
```

The per-skill plan documents give each skill's full file layout and sketch the contents of `rounds.py`, the behaviour module, and `base.py`.

## Composition impact (future work, not this PR)

Documented here so the follow-up PR has a clear target. The composition changes are NOT implemented in this PR.

Current `market_maker_abci` composition:

```text
AgentRegistrationAbci
  → MarketCreationManagerAbciApp
  → TransactionSubmissionAbciApp
  → MechInteractAbciApp
  → ResetPauseAbciApp
```

Target composition after the follow-up PR that wires in the three new skills:

```text
AgentRegistrationAbci
  → OmenFpmmRemoveLiquidityAbciApp
  ├── FinishedWithFpmmRemoveLiquidityTxRound → TransactionSubmissionAbciApp → (back to next)
  └── FinishedWithoutFpmmRemoveLiquidityTxRound → next
  → OmenCtRedeemTokensAbciApp
  ├── FinishedWithCtRedeemTokensTxRound → TransactionSubmissionAbciApp → (back to next)
  └── FinishedWithoutCtRedeemTokensTxRound → next
  → OmenRealitioWithdrawBondAbciApp
  ├── FinishedWithRealitioWithdrawBondTxRound → TransactionSubmissionAbciApp → (back to next)
  └── FinishedWithoutRealitioWithdrawBondTxRound → next
  → MarketCreationManagerAbciApp
  → TransactionSubmissionAbciApp
  → MechInteractAbciApp
  → ResetPauseAbciApp
```

The composed `abci_app_transition_mapping` gains six new entries (two final states per new skill). The `PostTransactionRound` router in market-creator's existing code learns three new `tx_submitter` tag values to route settlement-completion back to the right next skill.

Each new skill has its own `tx_submitter` tag:

- `"omen_fpmm_remove_liquidity"`
- `"omen_ct_redeem_tokens"`
- `"omen_realitio_withdraw_bond"`

These tags are set by the respective skill's behaviour before submitting the payload and read by the parent's `PostTransactionRound` to dispatch to the correct next state.

## Lint / coverage / FSM checklist per skill

```bash
tox -e isort
tox -e black
tox -e pylint
tox -e mypy
tox -e flake8
tox -e darglint
autonomy analyse docstrings --update
autonomy analyse fsm-specs --package packages/valory/skills/<skill_name>
autonomy packages lock
tox -e check-abciapp-specs
tox -e check-handlers
tox -e check-packages
tox -e unit-tests
```

Coverage target: 100% statement + branch per `.coveragerc`.

## References

- [omen_redeem_tokens_skill.md](omen_redeem_tokens_skill.md) — `omen_ct_redeem_tokens_abci` per-skill plan
- [omen_remove_liquidity_skill.md](omen_remove_liquidity_skill.md) — `omen_fpmm_remove_liquidity_abci` per-skill plan
- [omen_withdraw_bond_skill.md](omen_withdraw_bond_skill.md) — `omen_realitio_withdraw_bond_abci` per-skill plan
- [ct_omen_realitio.md](../docs/ct_omen_realitio.md) — the ecosystem primer explaining why there are three distinct actors
