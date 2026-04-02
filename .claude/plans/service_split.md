# Plan: Split Market Creator into Market Creator + Market Resolver

## Context

The `market_creation_manager_abci` skill currently handles the entire lifecycle of Omen prediction markets: creating markets, answering questions (via Mech), collecting LP tokens, redeeming conditional tokens, claiming bonds, and wrapping xDAI. This monolithic design makes the FSM large (14 active rounds, 9 final states, 17 events), hard to reason about, and impossible to run answering/challenging logic independently of market creation.

The goal is to split into **two independent services** on separate safes:

1. **Market Creator** (this repo) — creates prediction markets, manages LP positions
2. **Market Resolver** ([market-resolver repo](https://github.com/valory-xyz/market-resolver)) — watchdog that answers questions, challenges incorrect answers, manages Realitio bonds

Plus a **shared `omen_funds_recoverer_abci` skill** (IMPLEMENTED) that both services compose for fund recovery.

---

## Architecture Overview

```
┌─────────────────────────────────────────┐    ┌─────────────────────────────────────────┐
│         MARKET CREATOR SERVICE           │    │         MARKET RESOLVER SERVICE           │
│         (this repo, own safe)            │    │         (market-resolver repo, own safe)  │
│                                          │    │                                          │
│  Registration                            │    │  Registration                            │
│       ↓                                  │    │       ↓                                  │
│  IdentifyServiceOwner                    │    │  IdentifyServiceOwner                    │
│       ↓                                  │    │       ↓                                  │
│  FundsForwarder                          │    │  FundsForwarder                          │
│       ↓                                  │    │       ↓                                  │
│  ┌─────────────────────────────────┐     │    │  ┌─────────────────────────────────┐     │
│  │  omen_funds_recoverer_abci      │     │    │  │  omen_funds_recoverer_abci      │     │
│  │  (shared skill — IMPLEMENTED)   │     │    │  │  (shared skill — same code)     │     │
│  │  RemoveLP → RedeemCT → Claim    │     │    │  │  RemoveLP → RedeemCT → Claim    │     │
│  │  → BuildMultisend               │     │    │  │  → BuildMultisend               │     │
│  └─────────────────────────────────┘     │    │  └─────────────────────────────────┘     │
│       ↓                                  │    │       ↓                                  │
│  ┌─────────────────────────────────┐     │    │  ┌─────────────────────────────────┐     │
│  │  market_creation_manager_abci   │     │    │  │  market_resolution_manager_abci │     │
│  │  (slimmed — creation only)      │     │    │  │  (watchdog — scan + challenge)  │     │
│  │  Randomness → Keeper → Propose  │     │    │  │  Scan → Evaluate → [Mech]      │     │
│  │  → Approve → Retrieve → Create  │     │    │  │  → BuildChallenges → Cleanup   │     │
│  └─────────────────────────────────┘     │    │  └─────────────────────────────────┘     │
│       ↓                                  │    │       ↓                                  │
│  TxSettlement → ResetPause               │    │  TxSettlement + MechInteract             │
│  + Termination (background)              │    │  → ResetPause + Termination              │
└─────────────────────────────────────────┘    └─────────────────────────────────────────┘
```

---

## Current Monolith (what exists today)

| Domain | Rounds | Destination after split |
|--------|--------|------------------------|
| **Market Creation** | CollectRandomness, SelectKeeper, CollectProposedMarkets, ApproveMarkets, RetrieveApprovedMarket, PrepareTransaction | Stays in `market_creation_manager_abci` |
| **Question Answering** | GetPendingQuestions, [MechInteract], AnswerQuestions | → `market_resolution_manager_abci` (resolver repo) |
| **LP Fund Recovery** | SyncMarkets, RemoveFunding | → `omen_funds_recoverer_abci` (RemoveLiquidityRound) |
| **CT Redemption** | RedeemWinnings | → `omen_funds_recoverer_abci` (RedeemPositionsRound) |
| **Bond Recovery** | RedeemBond | → `omen_funds_recoverer_abci` (ClaimBondsRound + withdraw) |
| **Capital Management** | DepositDai | Removed (each service manages its own capital) |
| **Post-tx Routing** | PostTransaction | Simplified to PostCreationRound (creator) / CleanupTrackingRound (resolver) |

---

## Detailed Plans

Each component has its own detailed plan:

| Component | Plan location | Status |
|-----------|--------------|--------|
| **omen_funds_recoverer_abci** | [`.claude/plans/omen_funds_recoverer.md`](omen_funds_recoverer.md) | **IMPLEMENTED** — 152 tests, all linters pass |
| **Market Resolver (watchdog)** | [`market-resolver/.claude/plans/market_resolver.md`](https://github.com/valory-xyz/market-resolver/blob/main/.claude/plans/market_resolver.md) | Planned |
| **Slimmed Market Creator** | Section below | Planned |

---

## Slimmed Market Creator: `market_creation_manager_abci` (v2)

### What stays

| Round | Purpose |
|-------|---------|
| `CollectRandomnessRound` | Keeper selection seed |
| `SelectKeeperRound` | Pick keeper agent |
| `CollectProposedMarketsRound` | Fetch market proposals from approval server |
| `ApproveMarketsRound` | Validate proposals via Mech/LLM (keeper-only) |
| `RetrieveApprovedMarketRound` | Fetch approved market details (keeper-only) |
| `PrepareTransactionRound` | Build market creation multisend |
| `PostCreationRound` | Handle post-tx: extract FPMM address, update server |

### What is removed

| Round | Where it went |
|-------|--------------|
| `SyncMarketsRound` | `omen_funds_recoverer_abci` → RemoveLiquidityRound (self-contained query) |
| `RemoveFundingRound` | `omen_funds_recoverer_abci` → RemoveLiquidityRound |
| `RedeemWinningsRound` | `omen_funds_recoverer_abci` → RedeemPositionsRound |
| `DepositDaiRound` | Removed (capital management, not recovery) |
| `GetPendingQuestionsRound` | `market_resolution_manager_abci` → ScanMarketsRound |
| `AnswerQuestionsRound` | `market_resolution_manager_abci` → BuildChallengesTxRound |
| `RedeemBondRound` | `omen_funds_recoverer_abci` → ClaimBondsRound (includes withdraw) |

### Composed app: `market_maker_abci` (v2)

```
Composition chain:
  AgentRegistrationAbciApp
  → IdentifyServiceOwnerAbciApp
  → FundsForwarderAbciApp
  → OmenFundsRecovererAbciApp              # shared skill
  → MarketCreationManagerAbciApp           # slimmed
  → TransactionSettlementAbciApp
  → ResetPauseAbciApp
  + TerminationAbciApp (background)

Key transition mappings:
  FinishedWithRecoveryTxRound      → TxSettlement
  FinishedWithoutRecoveryTxRound   → CollectRandomnessRound
  FinishedMarketCreationRound      → TxSettlement
  FinishedWithoutTxRound           → ResetAndPauseRound
```

Note: MechInteract removed from composition (moves to resolver).

### FSM specification (slimmed creator)

```
Rounds:
  0. CollectRandomnessRound
  1. SelectKeeperRound
  2. CollectProposedMarketsRound
  3. ApproveMarketsRound
  4. RetrieveApprovedMarketRound
  5. PrepareTransactionRound
  6. PostCreationRound
  7. FinishedMarketCreationRound     (degenerate → TxSettlement)
  8. FinishedWithoutTxRound          (degenerate → ResetPause)

Transition function:
  CollectRandomnessRound:     DONE → SelectKeeper,            else → CollectRandomness
  SelectKeeperRound:          DONE → CollectProposedMarkets,   else → CollectRandomness
  CollectProposedMarketsRound: DONE → ApproveMarkets,          SKIP/ERROR → RetrieveApprovedMarket
  ApproveMarketsRound:        DONE → RetrieveApprovedMarket,   else → RetrieveApprovedMarket
  RetrieveApprovedMarketRound: DONE → PrepareTransaction,      NO_MARKETS → FinishedWithoutTx
  PrepareTransactionRound:    DONE → FinishedMarketCreation,   else → FinishedWithoutTx
  PostCreationRound:          DONE → FinishedWithoutTx,        else → FinishedWithoutTx
```

### Removed dependencies

- **MechInteract** skill — no longer needed (market creator doesn't answer questions)
- Realitio `submitAnswer` calls — removed
- `mech_tool_resolve_market`, `answer_retry_intervals`, `questions_to_close_batch_size` params — removed

### Kept dependencies

- FPMMDeterministicFactory (market creation)
- Realitio (`askQuestion` — asking a question is part of market creation, NOT answering)
- ConditionalTokens (`prepareCondition` for market creation)
- ERC20/wxDAI (collateral for market creation)
- Market Approval Server (market proposals)
- All `omen_funds_recoverer_abci` contract dependencies (via composed skill)

---

## Phased Implementation Plan

### Phase 1: `omen_funds_recoverer_abci` — DONE

Standalone skill implemented with tx accumulation pattern. See [omen_funds_recoverer.md](omen_funds_recoverer.md).

### Phase 2: Integrate `omen_funds_recoverer_abci` into Market Creator — DONE

Removed recovery rounds from `market_creation_manager_abci`, composed with `omen_funds_recoverer_abci`. Agent tested on Tenderly — full cycle works correctly.

**What was done:**

- Removed 5 recovery rounds: SyncMarkets, RemoveFunding, RedeemWinnings, RedeemBond (+ their behaviours, states, tests)
- Kept DepositDai (wraps xDAI→wxDAI for market creation collateral)
- Kept answering logic (GetPendingQuestions, AnswerQuestions, MechInteract)
- Added `OmenFundsRecovererAbciApp` to composition chain
- Added `OmenFundsRecovererRoundBehaviour` to composed behaviours
- Added `OmenFundsRecovererParams` to composed Params MRO
- Added `RealitioSubgraph` model to composed skill
- Added `RECOVERY_DONE` event for PostTransaction routing
- Shared contract address params (`realitio_contract`, etc.) declared as class attributes in `OmenFundsRecovererParams` to avoid MRO double-consumption
- Fixed Realitio subgraph composite question ID format (`{contract}-{question_id}`)
- Updated all configs (skill.yaml, agent aea-config.yaml, service.yaml)
- All linters pass (pylint 10.00, mypy 0 issues, flake8 OK, darglint OK)
- All structural checks pass (check-abciapp-specs, check-handlers, check-packages, analyse-service)
- 569 tests pass

**New composed FSM flow:**

```
Registration → IdentifyOwner → FundsForwarder
  → RemoveLiquidity → RedeemPositions → ClaimBonds → BuildMultisend (omen_funds_recoverer)
  → [TxSettlement if recovery tx]
  → DepositDai → GetPendingQuestions → [MechInteract] → AnswerQuestions
  → CollectRandomness → SelectKeeper → CollectProposed → Approve → Retrieve → Prepare
  → [TxSettlement] → PostTransaction → ResetPause → (loop)
```

### Phase 3 (future): Remove answering logic + MechInteract

Done when the market-resolver service is ready:
- Remove `GetPendingQuestionsRound`, `AnswerQuestionsRound`
- Remove MechInteract from composition
- Remove mech-related params and events

### Phase 4: Deployment

1. Deploy Market Creator (v2) to production
2. Verify fund recovery + market creation work correctly
3. When market-resolver is ready, deploy both simultaneously

> **Note:** Market Resolver is developed in the [market-resolver repo](https://github.com/valory-xyz/market-resolver). See [market_resolver.md](https://github.com/valory-xyz/market-resolver/blob/main/.claude/plans/market_resolver.md).

---

## Migration Strategy

**Big-bang deployment.** Deploy both services simultaneously to avoid a gap where questions go unanswered.

1. Complete all phases before any deployment
2. Deploy Market Creator (v2) + Market Resolver simultaneously
3. Stop old monolithic service
4. Market Creator's safe keeps existing LP positions (`omen_funds_recoverer_abci` handles them)
5. Market Resolver's safe gets funded with xDAI for bonds

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Bond management bugs** | Incorrect challenges could lose funds | Mech confidence threshold, max_challenge_bond cap, simulation before submit |
| **Shared state conflicts** | Both services on same markets could interfere | Separate safes, Realitio's 2x bond prevents accidental double-answering |
| **TxSettlement routing** | Composition must route correctly after settlement | Recovery uses tx accumulation (one multisend) — only one `tx_submitter` string to check |
| **Test coverage regression** | Extracting code requires rewriting tests | Each phase includes full test suite at 100% coverage |

---

## Open Questions

1. **Should the resolver resolve ALL Omen markets or only markets created by our creator?**
   - Config flag `resolution_scope` allows both modes

2. **Should the resolver request arbitration when bond escalation exceeds the max?**
   - Defer to future phase

3. ~~**Should discovery be centralized or per-round?**~~ **RESOLVED**: Each round does its own discovery.

4. ~~**How to handle TxSettlement routing?**~~ **RESOLVED**: Tx accumulation pattern eliminates the problem.

---

## Reference Documentation

- [CT / Omen / Realitio tutorial](../docs/ct_omen_realitio.md) — how the contracts interact, fund recovery paths
- [Omen market lifecycle](../docs/omen_lifecycle.md) — full lifecycle with contract calls at each step
- [Tenderly simulations](../../simulate_redemption.py) — proves `redeemPositions` ≠ `claimWinnings`
