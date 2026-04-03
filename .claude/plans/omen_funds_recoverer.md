# Plan: `omen_funds_recoverer_abci` Skill (v3 — IMPLEMENTED)

## Context

A standalone, reusable ABCI skill that recovers all locked funds from Omen prediction markets. Designed based on learnings from Tenderly simulations (`simulate_redemption.py`, `simulate_redeem_no_merge.py`) that proved:

- `redeemPositions` does NOT require `claimWinnings` — they're independent contract flows
- After resolution, `mergePositions` is redundant — `redeemPositions` handles everything
- Before resolution, `mergePositions` is the ONLY way to recover the "equal part" of LP tokens as wxDAI

Previous iterations moved to `tmp/fund_recovery_abci_v1/`.

---

## Architecture: Tx Accumulation Pattern

Instead of each round producing its own tx and going through TxSettlement separately (which requires a PostTx router and fights the OA framework's single-target `FinishedTransactionSubmissionRound` mapping), the skill accumulates all recovery txs into a shared list and builds ONE multisend at the end.

```
RemoveLiquidity → RedeemPositions → ClaimBonds → BuildMultisend ──DONE──► FinishedWithRecoveryTx
                                                                ──NO_TX──► FinishedWithoutRecoveryTx
```

Each recovery round:
1. Queries its own subgraph (self-contained)
2. Builds raw tx dicts `[{"to": "0x...", "data": "0x...", "value": 0}]`
3. Appends to `recovery_txs` in SynchronizedData
4. Always moves to the next round (DONE event)

BuildMultisend reads the accumulated `recovery_txs`, bundles into one safe multisend, and exits.

**Why this pattern:**
- No PostRecovery router needed
- One TxSettlement round trip per cycle (not 3)
- Single initial state, 2 final states — trivial composition
- No `tx_submitter` string coupling with the parent app's PostTransaction

---

## FSM

### Rounds

| Round | Type | Purpose |
|-------|------|---------|
| `RemoveLiquidityRound` | `RecoveryTxsRound` | Remove LP from markets approaching close, merge equal tokens |
| `RedeemPositionsRound` | `RecoveryTxsRound` | Resolve conditions + redeem CT positions from finalized markets |
| `ClaimBondsRound` | `RecoveryTxsRound` | Claim Realitio bonds + withdraw internal balance |
| `BuildMultisendRound` | `CollectSameUntilThresholdRound` | Bundle all `recovery_txs` into one safe multisend |
| `FinishedWithRecoveryTxRound` | `DegenerateRound` | → TxSettlement in composition |
| `FinishedWithoutRecoveryTxRound` | `DegenerateRound` | → next skill in composition |

### Events

```python
class Event(Enum):
    DONE = "done"
    NO_TX = "no_tx"
    NO_MAJORITY = "no_majority"
    NONE = "none"
    ROUND_TIMEOUT = "round_timeout"
```

5 events only — no per-round routing events needed.

### Transition Function

```python
RemoveLiquidityRound:  DONE → RedeemPositions,  NO_MAJORITY/TIMEOUT → RedeemPositions
RedeemPositionsRound:  DONE → ClaimBonds,        NO_MAJORITY/TIMEOUT → ClaimBonds
ClaimBondsRound:       DONE → BuildMultisend,    NO_MAJORITY/TIMEOUT → BuildMultisend
BuildMultisendRound:   DONE → FinishedWithTx,    NO_TX/NO_MAJORITY/TIMEOUT → FinishedNoTx
```

### Key types

- `RecoveryTxsRound` — base class for the 3 recovery rounds. Uses `RecoveryTxsPayload(content=json_list_of_tx_dicts)`. Its `end_block()` accumulates txs into `SynchronizedData.recovery_txs`.
- `BuildMultisendRound` — uses `BuildMultisendPayload(tx_submitter, tx_hash)`. Reads accumulated `recovery_txs`, builds one multisend.

---

## Round Details

### RemoveLiquidityRound

**Query** (Omen subgraph): `fpmmPoolMemberships(funder: $safe, amount_gt: "0")`
**Filter:** `openingTimestamp - liquidity_removal_lead_time < now`
**On-chain verify:** `FPMM.get_markets_with_funds(addresses, safe)`
**Batch:** `remove_liquidity_batch_size` (default: 1)
**Txs per market:** `removeFunding` + `mergePositions`
**No unwrap** — wxDAI stays in safe.

### RedeemPositionsRound

**Queries:** CT subgraph `user($safe).userPositions(balance_gt: 0)` + Omen subgraph for finalized markets
**Filter:** Cross-reference held positions with finalized payouts
**Batch:** `redeem_positions_batch_size` (default: 5)
**Txs per market:** `RealitioProxy.resolve` (if needed) + `CT.redeemPositions`

### ClaimBondsRound

**Query** (Realitio subgraph): `responses(user: $safe, finalized)`
**On-chain filter:** `getHistoryHash != bytes32(0)` (unclaimed)
**Batch:** `claim_bonds_batch_size` (default: 10)
**Txs:** `claimWinnings` per question + one `withdraw()` at end if balance > threshold

### BuildMultisendRound

**Reads:** `SynchronizedData.recovery_txs`
**If empty:** NO_TX → FinishedWithoutRecoveryTx
**If non-empty:** converts hex data strings back to bytes, calls `_to_multisend()` → DONE → FinishedWithRecoveryTx

---

## Configuration Parameters

All integers. Defined in `OmenFundsRecovererParams`.

```yaml
liquidity_removal_lead_time: 86400          # seconds before market opening to remove LP
remove_liquidity_batch_size: 1              # LP markets per cycle
redeem_positions_batch_size: 5              # CT redemptions per cycle
claim_bonds_batch_size: 10                  # claimWinnings per cycle
min_balance_withdraw_realitio: 10000000000000000000  # 10 xDAI in wei
realitio_start_block: 0                     # first block for LogNewAnswer event scan
realitio_contract: "0x..."
realitio_oracle_proxy_contract: "0x..."
conditional_tokens_contract: "0x..."
collateral_tokens_contract: "0x..."         # wxDAI
```

---

## File Structure

```
packages/valory/skills/omen_funds_recoverer_abci/
├── __init__.py
├── skill.yaml
├── fsm_specification.yaml
├── rounds.py                     # Event, SynchronizedData, RecoveryTxsRound, BuildMultisendRound, AbciApp
├── payloads.py                   # RecoveryTxsPayload, BuildMultisendPayload
├── models.py                     # OmenFundsRecovererParams, SharedState, 3 subgraph models
├── handlers.py
├── dialogues.py
├── behaviours/
│   ├── __init__.py
│   ├── base.py                   # OmenFundsRecovererBaseBehaviour (subgraph helpers, multisend)
│   ├── remove_liquidity.py       # Self-contained: query + removeFunding + merge → tx dicts
│   ├── redeem_positions.py       # Self-contained: query + resolve + redeem → tx dicts
│   ├── claim_bonds.py            # Self-contained: query + claimWinnings + withdraw → tx dicts
│   ├── build_multisend.py        # Reads recovery_txs, builds one safe multisend
│   └── round_behaviour.py        # OmenFundsRecovererRoundBehaviour
└── tests/                        # 174 tests
```

---

## Composition

The skill provides to the composed app:

```python
initial_states = {RemoveLiquidityRound}      # one entry point
final_states = {
    FinishedWithRecoveryTxRound,              # → TxSettlement
    FinishedWithoutRecoveryTxRound,           # → next skill (e.g., MarketCreation)
}
```

No PostRecovery router. No `tx_submitter` coupling. The parent app maps:
```python
FinishedWithRecoveryTxRound → TransactionSettlement
FinishedWithoutRecoveryTxRound → NextSkillInitialRound
FinishedTransactionSubmissionRound → PostTransactionRound  # parent's existing router
```

The parent's PostTransaction only needs one string check for this skill's `tx_submitter` to route back to the next skill after settlement.

---

## Status

**IMPLEMENTED.** 29 files, 174 tests passing, formatted with isort + black.
