# Plan: Split Market Creator into Market Creator + Market Resolver

## Context

The `market_creation_manager_abci` skill currently handles the entire lifecycle of Omen prediction markets: creating markets, answering questions (via Mech), collecting LP tokens, redeeming conditional tokens, claiming bonds, and wrapping xDAI. This monolithic design makes the FSM large (14 active rounds, 9 final states, 17 events), hard to reason about, and impossible to run answering/challenging logic independently of market creation.

The goal is to split into **two independent services** that can run on separate safes:

1. **Market Creator** -- creates prediction markets, manages LP positions
2. **Market Resolver** -- answers questions, challenges incorrect answers, manages Realitio bonds

Plus a **shared `fund_recovery_abci` skill** that both services use to recover ALL types of locked funds (LP tokens, conditional tokens, Realitio bonds, xDAI wrapping). Fund recovery runs FIRST in each cycle, so services always operate with maximum available capital.

---

## 1. Current Responsibility Map

### Rounds by responsibility domain

| Domain | Rounds | Key Contracts | Locked Funds |
|--------|--------|---------------|-------------|
| **Market Creation** | CollectRandomness, SelectKeeper, CollectProposedMarkets, ApproveMarkets, RetrieveApprovedMarket, PrepareTransaction | FPMMDeterministicFactory, Realitio (askQuestion), ConditionalTokens (prepareCondition), ERC20 | wxDAI (initial liquidity) |
| **Question Answering** | GetPendingQuestions, [MechInteract], AnswerQuestions | Realitio (submitAnswer), ERC20 (unwrap wxDAI for bond) | native xDAI (bonds posted) |
| **LP Fund Recovery** | SyncMarkets, RemoveFunding | FPMM (removeFunding), ConditionalTokens (mergePositions), ERC20 (withdraw) | LP pool shares, excess conditional tokens |
| **CT Position Redemption** | RedeemWinnings | RealitioProxy (resolve), ConditionalTokens (redeemPositions) | Residual conditional tokens |
| **Bond Recovery** | RedeemBond, [ClaimWinnings -- not yet implemented] | Realitio (claimWinnings, withdraw) | Realitio internal balance |
| **Capital Management** | DepositDai | wxDAI (deposit) | native xDAI -> wxDAI |
| **Post-tx Routing** | PostTransaction | FPMMDeterministicFactory (event parsing), Market Approval Server | N/A |

### Current FSM cycle order

```
SyncMarkets -> RemoveFunding -> [Tx] -> RedeemWinnings -> [Tx] ->
DepositDai -> [Tx] -> GetPendingQuestions -> [MechInteract] ->
AnswerQuestions -> [Tx] -> SelectKeeper -> RedeemBond -> [Tx] ->
CollectProposedMarkets -> ApproveMarkets -> RetrieveApprovedMarket ->
PrepareTransaction -> [Tx] -> PostTransaction -> Reset
```

---

## 2. Proposed Architecture

### Design principles

1. **Linear FSMs only** -- no conditional branching. Every round either produces a tx (routes through TxSettlement + PostTx, then returns to the next round) or skips (NO_TX -> next round directly).
2. **Recovery first, action second** -- each cycle starts by recovering ALL types of locked funds, THEN does the service-specific work (create markets or resolve questions). This ensures maximum capital is available for the action phase.
3. **One shared skill for ALL fund recovery** -- `fund_recovery_abci` handles LP tokens, conditional tokens, Realitio bonds, and xDAI wrapping. Both services compose it. Rounds that find nothing to do emit NO_TX and the FSM advances to the next round.
4. **Separate safes** -- each service runs its own Gnosis Safe with its own budget.

### Full composed FSMs

#### Market Creator Service

```
Registration
  |
  v
IdentifyServiceOwner
  |
  v
FundsForwarder -(Tx?)-> [TxSettlement]
  |
  v
========================= fund_recovery_abci =========================
  |
SyncLockedFunds
  |
  v
RemoveLiquidity ----DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
RedeemPositions <---+------------------------------------------'
  |
  v
RedeemPositions ----DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
ClaimBonds <--------+------------------------------------------'
  |
  v
ClaimBonds ---------DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
WithdrawBonds <-----+------------------------------------------'
  |
  v
WithdrawBonds ------DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
DepositDai <--------+------------------------------------------'
  |
  v
DepositDai ---------DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
[FinishedRecovery] <+------------------------------------------'
  |
===================================================================
  |
  v
================== market_creation_manager_abci ===================
  |
CollectRandomness
  |
  v
SelectKeeper
  |
  v
CollectProposedMarkets
  |
  v
ApproveMarkets
  |
  v
RetrieveApprovedMarket --NO_MARKETS--> [FinishedNoTx]
  |
  v
PrepareTransaction ------DONE-------> [TxSettlement] -> PostCreation
  |                                                         |
  v                                                         |
[FinishedNoTx] <--------------------------------------------'
  |
===================================================================
  |
  v
ResetPause -> [back to IdentifyServiceOwner]

Background: TerminationAbci
```

#### Market Resolver Service

```
Registration
  |
  v
IdentifyServiceOwner
  |
  v
FundsForwarder -(Tx?)-> [TxSettlement]
  |
  v
========================= fund_recovery_abci =========================
  |
SyncLockedFunds
  |
  v
RemoveLiquidity ----DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
RedeemPositions <---+------------------------------------------'
  |
  v
RedeemPositions ----DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
ClaimBonds <--------+------------------------------------------'
  |
  v
ClaimBonds ---------DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
WithdrawBonds <-----+------------------------------------------'
  |
  v
WithdrawBonds ------DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
DepositDai <--------+------------------------------------------'
  |
  v
DepositDai ---------DONE----> [TxSettlement] -> PostRecovery -.
  |--- NO_TX ------.                                          |
  v                 |                                          |
[FinishedRecovery] <+------------------------------------------'
  |
===================================================================
  |
  v
=============== market_resolution_manager_abci ====================
  |
ScanMarkets
  |
  v
PrepareResolutions --DONE--> [MechInteract] -.
  |--- NO_TX ------.                         |
  v                 |                         |
SubmitResolutions <-+-------------------------'
  |
  v
SubmitResolutions ---DONE---> [TxSettlement] -> PostResolution
  |--- NO_TX ------.                               |
  v                 |                               |
[FinishedNoTx] <----+-------------------------------'
  |
===================================================================
  |
  v
ResetPause -> [back to IdentifyServiceOwner]

Background: TerminationAbci
```

**Key observations:**
- Both services have the IDENTICAL `fund_recovery_abci` block. The market creator won't typically have Realitio bonds (it doesn't answer questions), so ClaimBonds and WithdrawBonds emit NO_TX and skip. The resolver won't typically have LP tokens, so RemoveLiquidity and RedeemPositions emit NO_TX and skip. But the rounds are there -- if somehow a service accumulates unexpected fund types, they get recovered.
- The resolver's `PrepareResolutions -> [MechInteract] -> SubmitResolutions` is a single linear path. ScanMarkets classifies everything (new answers, challenges, escalations) upfront. PrepareResolutions builds Mech requests for all of them. SubmitResolutions builds `submitAnswer` transactions for all -- answering and challenging are the SAME Realitio call, just with different bond amounts.

---

## 3. Shared Skill: `fund_recovery_abci`

### Purpose

A reusable skill that recovers ALL types of locked funds from an Omen prediction market safe. Runs first in every cycle to maximize available capital for subsequent rounds.

### FSM specification

```
Rounds:
  0. SyncLockedFundsRound
  1. RemoveLiquidityRound
  2. RedeemPositionsRound
  3. ClaimBondsRound
  4. WithdrawBondsRound
  5. DepositDaiRound
  6. PostRecoveryRound
  7. FinishedRecoveryWithTxRound  (degenerate -> TxSettlement in composition)
  8. FinishedRecoveryRound        (degenerate -> next skill in composition)

Initial state: SyncLockedFundsRound
Initial states: {SyncLockedFundsRound, PostRecoveryRound}

Transition function:
  SyncLockedFundsRound:
    DONE          -> RemoveLiquidityRound
    ERROR         -> FinishedRecoveryRound       # skip recovery, proceed to action
    NO_MAJORITY   -> SyncLockedFundsRound
    ROUND_TIMEOUT -> SyncLockedFundsRound

  RemoveLiquidityRound:
    DONE          -> FinishedRecoveryWithTxRound  # -> TxSettlement -> PostRecovery
    NO_TX         -> RedeemPositionsRound          # skip, next round
    ERROR         -> RedeemPositionsRound
    NO_MAJORITY   -> RedeemPositionsRound
    ROUND_TIMEOUT -> RedeemPositionsRound

  RedeemPositionsRound:
    DONE          -> FinishedRecoveryWithTxRound
    NO_TX         -> ClaimBondsRound
    ERROR         -> ClaimBondsRound
    NO_MAJORITY   -> ClaimBondsRound
    ROUND_TIMEOUT -> ClaimBondsRound

  ClaimBondsRound:
    DONE          -> FinishedRecoveryWithTxRound
    NO_TX         -> WithdrawBondsRound
    ERROR         -> WithdrawBondsRound
    NO_MAJORITY   -> WithdrawBondsRound
    ROUND_TIMEOUT -> WithdrawBondsRound

  WithdrawBondsRound:
    DONE          -> FinishedRecoveryWithTxRound
    NO_TX         -> DepositDaiRound
    ERROR         -> DepositDaiRound
    NO_MAJORITY   -> DepositDaiRound
    ROUND_TIMEOUT -> DepositDaiRound

  DepositDaiRound:
    DONE          -> FinishedRecoveryWithTxRound
    NO_TX         -> FinishedRecoveryRound
    ERROR         -> FinishedRecoveryRound
    NO_MAJORITY   -> FinishedRecoveryRound
    ROUND_TIMEOUT -> FinishedRecoveryRound

  PostRecoveryRound:
    REMOVE_LIQUIDITY_DONE  -> RedeemPositionsRound
    REDEEM_POSITIONS_DONE  -> ClaimBondsRound
    CLAIM_BONDS_DONE       -> WithdrawBondsRound
    WITHDRAW_BONDS_DONE    -> DepositDaiRound
    DEPOSIT_DAI_DONE       -> FinishedRecoveryRound
    ERROR                  -> FinishedRecoveryRound
    NO_MAJORITY            -> PostRecoveryRound
    NONE                   -> PostRecoveryRound
```

### Linearized flow diagram

```
SyncLockedFunds ─────────────────────────────────────────────────────────────────
       │
       v
RemoveLiquidity ──DONE──> [Tx] ─> PostRecovery(REMOVE_DONE) ──┐
       │                                                        │
       │──NO_TX──┐                                              │
       v         │                                              │
RedeemPositions <┴──────────────────────────────────────────────┘
       │
       v
RedeemPositions ──DONE──> [Tx] ─> PostRecovery(REDEEM_DONE) ──┐
       │                                                        │
       │──NO_TX──┐                                              │
       v         │                                              │
ClaimBonds <─────┴──────────────────────────────────────────────┘
       │
       v
ClaimBonds ───────DONE──> [Tx] ─> PostRecovery(CLAIM_DONE) ───┐
       │                                                        │
       │──NO_TX──┐                                              │
       v         │                                              │
WithdrawBonds <──┴──────────────────────────────────────────────┘
       │
       v
WithdrawBonds ────DONE──> [Tx] ─> PostRecovery(WITHDRAW_DONE) ┐
       │                                                        │
       │──NO_TX──┐                                              │
       v         │                                              │
DepositDai <─────┴──────────────────────────────────────────────┘
       │
       v
DepositDai ───────DONE──> [Tx] ─> PostRecovery(DEPOSIT_DONE) ─┐
       │                                                        │
       │──NO_TX──┐                                              │
       v         │                                              │
[FinishedRecovery] <────────────────────────────────────────────┘
```

Every round follows the same pattern: check if work exists -> if yes, build tx and route through TxSettlement -> PostRecovery routes to the next round. If no work, skip directly to the next round.

### Round details

#### `SyncLockedFundsRound`
- **Adapted from**: current `SyncMarketsRound` + subgraph queries from other behaviours
- **Purpose**: Single discovery pass for ALL locked fund types
- **Queries**:
  1. **Omen subgraph** -- FPMM pool memberships for the safe (LP shares to remove)
  2. **ConditionalTokens subgraph** -- user positions with balance > 0 (residual CT to redeem)
  3. **Omen subgraph** -- finalized markets matching held conditions (CT redemption targets)
  4. **Realitio subgraph** -- questions answered by the safe, finalized, not yet claimed
  5. **Realitio contract** -- `balanceOf(safe)` for withdrawable internal balance
- **Writes to SynchronizedData**:
  - `markets_to_remove_liquidity: List[Dict]` -- FPMM markets with LP to remove
  - `positions_to_redeem: List[Dict]` -- CT positions to redeem (resolve + redeem)
  - `bonds_to_claim: List[Dict]` -- Realitio questions with unclaimed bonds
  - `realitio_withdrawable: int` -- current Realitio internal balance
- **Events**: `DONE`, `ERROR`, `NO_MAJORITY`, `ROUND_TIMEOUT`

#### `RemoveLiquidityRound`
- **Adapted from**: current `RemoveFundingRound` + `SyncMarketsRound`
- **Purpose**: Remove liquidity from expired/resolved FPMM markets
- **Reads**: `markets_to_remove_liquidity` from SynchronizedData
- **Logic**: Find first market where `removal_timestamp < now`, build removeFunding + mergePositions + withdraw multisend
- **Contract calls**: FPMM.removeFunding, CT.mergePositions, wxDAI.withdraw
- **Events**: `DONE` (tx ready), `NO_TX` (nothing to remove), `ERROR`

#### `RedeemPositionsRound`
- **Adapted from**: current `RedeemWinningsRound`
- **Purpose**: Resolve conditions and redeem conditional token positions
- **Reads**: `positions_to_redeem` from SynchronizedData
- **Logic**: For each redeemable market (up to batch_size): check if resolved on-chain, if not prepend resolve tx, build redeemPositions tx
- **Contract calls**: RealitioProxy.resolve, CT.redeemPositions
- **Events**: `DONE` (tx ready), `NO_TX` (nothing to redeem), `ERROR`

#### `ClaimBondsRound`
- **Adapted from**: planned `ClaimWinningsRound` (see `claim_winnings.md`)
- **Purpose**: Claim finalized Realitio bonds via `claimWinnings`
- **Reads**: `bonds_to_claim` from SynchronizedData
- **Logic**:
  1. For each unclaimed question (up to `claim_bonds_batch_size`):
     - Check on-chain `getHistoryHash` -- skip if already claimed (bytes32(0))
     - If sole answerer: build params from question data directly
     - If contested: reconstruct history chain from LogNewAnswer events
  2. Build multisend of claimWinnings calls
- **Contract calls**: Realitio.claimWinnings
- **Events**: `DONE` (tx ready), `NO_TX` (nothing to claim), `ERROR`

#### `WithdrawBondsRound`
- **Adapted from**: current `RedeemBondRound`
- **Purpose**: Withdraw Realitio internal balance to the safe
- **Reads**: `realitio_withdrawable` from SynchronizedData (and re-checks on-chain)
- **Logic**: Check balanceOf, if > min_threshold build withdraw tx
- **Contract calls**: Realitio.balanceOf, Realitio.withdraw
- **Events**: `DONE` (tx ready), `NO_TX` (balance too low), `ERROR`

#### `DepositDaiRound`
- **Adapted from**: current `DepositDaiRound`
- **Purpose**: Wrap excess xDAI into wxDAI for market operations
- **Logic**: Check native xDAI balance, if > threshold wrap the excess
- **Contract calls**: wxDAI.deposit (fallback with ether)
- **Events**: `DONE` (tx ready), `NO_TX` (balance below threshold), `ERROR`

#### `PostRecoveryRound`
- **Adapted from**: recovery-specific portion of current `PostTransactionRound`
- **Purpose**: After TxSettlement, route to the next recovery round
- **Logic**: Read `tx_submitter` to determine which round produced the tx, emit the corresponding event to advance
- **Events**: `REMOVE_LIQUIDITY_DONE`, `REDEEM_POSITIONS_DONE`, `CLAIM_BONDS_DONE`, `WITHDRAW_BONDS_DONE`, `DEPOSIT_DAI_DONE`, `ERROR`

### Final states

| Final State | Routes to (in composition) |
|---|---|
| `FinishedRecoveryWithTxRound` | -> TxSettlement (settle the prepared tx) |
| `FinishedRecoveryRound` | -> next skill in chain (market creation or resolution) |

### Configuration parameters

```yaml
# Batch sizes
claim_bonds_batch_size: 10           # max claimWinnings per cycle
redeem_positions_batch_size: 5       # max redeemPositions per cycle

# Thresholds
xdai_threshold: 500000000000000000   # 0.5 xDAI minimum to keep unwrapped
min_balance_withdraw_realitio: 100000000000000000  # 0.1 xDAI min to withdraw

# Contract addresses (shared with parent skill)
realitio_contract: "0x..."
realitio_oracle_proxy_contract: "0x..."
conditional_tokens_contract: "0x..."
collateral_tokens_contract: "0x..."
```

### Contracts required

| Contract | Methods used |
|----------|-------------|
| FPMM | removeFunding, get_balance, get_total_supply |
| ConditionalTokens | mergePositions, redeemPositions, check_resolved, get_user_holdings |
| RealitioProxy | resolve |
| Realitio | claimWinnings, withdraw, balanceOf, getHistoryHash |
| ERC20/wxDAI | withdraw (unwrap), deposit (wrap), check_balance |
| GnosisSafe | get_raw_safe_transaction_hash |
| MultiSend | get_tx_data |

---

## 4. Slimmed Market Creator: `market_creation_manager_abci` (v2)

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

### What is removed (moved to fund_recovery_abci or resolver)

| Round | Destination |
|-------|------------|
| `SyncMarketsRound` | fund_recovery_abci -> SyncLockedFundsRound |
| `RemoveFundingRound` | fund_recovery_abci -> RemoveLiquidityRound |
| `RedeemWinningsRound` | fund_recovery_abci -> RedeemPositionsRound |
| `DepositDaiRound` | fund_recovery_abci -> DepositDaiRound |
| `GetPendingQuestionsRound` | market_resolution_manager_abci -> ScanMarketsRound |
| `AnswerQuestionsRound` | market_resolution_manager_abci -> SubmitResolutionsRound |
| `RedeemBondRound` | fund_recovery_abci -> WithdrawBondsRound |
| `PostTransactionRound` | Split: recovery routing -> fund_recovery_abci PostRecoveryRound, creation routing -> PostCreationRound |

### FSM specification

```
Rounds:
  0. CollectRandomnessRound
  1. SelectKeeperRound
  2. CollectProposedMarketsRound
  3. ApproveMarketsRound
  4. RetrieveApprovedMarketRound
  5. PrepareTransactionRound
  6. PostCreationRound
  7. FinishedMarketCreationRound     (degenerate -> TxSettlement)
  8. FinishedWithoutTxRound          (degenerate -> ResetPause)

Initial state: CollectRandomnessRound

Transition function:
  CollectRandomnessRound:
    DONE          -> SelectKeeperRound
    NO_MAJORITY   -> CollectRandomnessRound
    NONE          -> CollectRandomnessRound
    ROUND_TIMEOUT -> CollectRandomnessRound

  SelectKeeperRound:
    DONE          -> CollectProposedMarketsRound
    NO_MAJORITY   -> CollectRandomnessRound
    NONE          -> CollectRandomnessRound
    ROUND_TIMEOUT -> CollectRandomnessRound

  CollectProposedMarketsRound:
    DONE                       -> ApproveMarketsRound
    MAX_APPROVED_MARKETS_REACHED -> RetrieveApprovedMarketRound
    SKIP_MARKET_APPROVAL       -> RetrieveApprovedMarketRound
    ERROR                      -> RetrieveApprovedMarketRound
    MAX_RETRIES_REACHED        -> RetrieveApprovedMarketRound
    NO_MAJORITY                -> RetrieveApprovedMarketRound
    NONE                       -> RetrieveApprovedMarketRound
    ROUND_TIMEOUT              -> RetrieveApprovedMarketRound

  ApproveMarketsRound:
    DONE          -> RetrieveApprovedMarketRound
    ERROR         -> RetrieveApprovedMarketRound
    MAX_RETRIES   -> RetrieveApprovedMarketRound
    ROUND_TIMEOUT -> RetrieveApprovedMarketRound

  RetrieveApprovedMarketRound:
    DONE              -> PrepareTransactionRound
    NO_MARKETS        -> FinishedWithoutTxRound
    ERROR             -> FinishedWithoutTxRound
    ROUND_TIMEOUT     -> FinishedWithoutTxRound

  PrepareTransactionRound:
    DONE          -> FinishedMarketCreationRound
    NO_MAJORITY   -> FinishedWithoutTxRound
    NONE          -> FinishedWithoutTxRound
    ROUND_TIMEOUT -> FinishedWithoutTxRound

  PostCreationRound:
    DONE          -> FinishedWithoutTxRound
    ERROR         -> FinishedWithoutTxRound
    NO_MAJORITY   -> PostCreationRound
    NONE          -> PostCreationRound
```

### Linearized flow diagram

```
CollectRandomness -> SelectKeeper -> CollectProposedMarkets -> ApproveMarkets
       |                                                           |
       v                                                           v
RetrieveApprovedMarket ──NO_MARKETS──> [FinishedNoTx]
       |
       v
PrepareTransaction ──DONE──> [TxSettlement] -> PostCreation -> [FinishedNoTx]
```

### Composed app: `market_maker_abci` (v2)

```
Composition chain:
  AgentRegistrationAbciApp
  -> IdentifyServiceOwnerAbciApp
  -> FundsForwarderAbciApp
  -> FundRecoveryAbciApp            # NEW: shared skill
  -> MarketCreationManagerAbciApp   # SLIMMED: no recovery, no answering
  -> TransactionSettlementAbciApp
  -> ResetPauseAbciApp
  + TerminationAbciApp (background)

Transition mapping:
  FinishedRegistrationRound           -> IdentifyServiceOwnerRound
  FinishedIdentifyServiceOwnerRound   -> FundsForwarderRound
  FinishedIdentifyServiceOwnerError   -> SyncLockedFundsRound
  FinishedFundsForwarderWithTxRound   -> TxSettlement
  FinishedFundsForwarderNoTxRound     -> SyncLockedFundsRound

  # Fund recovery -> TxSettlement -> PostRecovery -> next recovery round
  FinishedRecoveryWithTxRound         -> TxSettlement
  FinishedTransactionSubmissionRound  -> PostRecoveryRound (or PostCreationRound)
  FinishedRecoveryRound               -> CollectRandomnessRound

  # Market creation -> TxSettlement -> PostCreation -> reset
  FinishedMarketCreationRound         -> TxSettlement
  FinishedWithoutTxRound              -> ResetAndPauseRound

  # Reset
  FinishedResetAndPauseRound          -> IdentifyServiceOwnerRound
  FinishedResetAndPauseErrorRound     -> RegistrationRound
```

### Removed dependencies

- **MechInteract** skill -- no longer needed (market creator doesn't answer questions)
- Realitio `submitAnswer` calls -- removed
- `mech_tool_resolve_market`, `answer_retry_intervals`, `questions_to_close_batch_size` params -- removed
- `mech_interact_round_timeout_seconds` -- removed

### Kept dependencies

- FPMMDeterministicFactory (market creation)
- Realitio (askQuestion -- asking a question is part of market creation, NOT answering)
- ConditionalTokens (prepareCondition for market creation)
- ERC20/wxDAI (collateral for market creation)
- Market Approval Server (market proposals)
- All fund_recovery_abci contract dependencies (via composed skill)

---

## 5. New Skill: `market_resolution_manager_abci`

### Purpose

Autonomously resolves Omen prediction markets by:
1. Discovering markets needing answers (unanswered, incorrectly answered, re-challenged)
2. Evaluating ALL discovered questions using Mech in a single pass
3. Submitting answers/challenges to Realitio in a single multisend

Answering and challenging are the SAME Realitio operation (`submitAnswer`), just with different bond amounts. The FSM treats them identically.

### FSM specification

```
Rounds:
  0. ScanMarketsRound
  1. PrepareResolutionsRound
  2. SubmitResolutionsRound
  3. PostResolutionRound
  4. FinishedWithMechRequestRound     (degenerate -> MechInteract)
  5. FinishedResolutionWithTxRound    (degenerate -> TxSettlement)
  6. FinishedResolutionRound          (degenerate -> ResetPause)

Initial state: ScanMarketsRound
Initial states: {ScanMarketsRound, SubmitResolutionsRound, PostResolutionRound}

Transition function:
  ScanMarketsRound:
    DONE          -> PrepareResolutionsRound
    NONE          -> FinishedResolutionRound       # nothing to do
    ERROR         -> FinishedResolutionRound
    NO_MAJORITY   -> ScanMarketsRound
    ROUND_TIMEOUT -> ScanMarketsRound

  PrepareResolutionsRound:
    DONE          -> FinishedWithMechRequestRound   # -> MechInteract -> SubmitResolutions
    NO_TX         -> FinishedResolutionRound        # escalations only, no mech needed
    ERROR         -> FinishedResolutionRound
    NO_MAJORITY   -> FinishedResolutionRound
    ROUND_TIMEOUT -> FinishedResolutionRound

  SubmitResolutionsRound:
    DONE          -> FinishedResolutionWithTxRound  # -> TxSettlement -> PostResolution
    NO_TX         -> FinishedResolutionRound        # mech said don't answer/challenge
    ERROR         -> FinishedResolutionRound
    NO_MAJORITY   -> FinishedResolutionRound
    ROUND_TIMEOUT -> FinishedResolutionRound

  PostResolutionRound:
    DONE          -> FinishedResolutionRound
    ERROR         -> FinishedResolutionRound
    NO_MAJORITY   -> PostResolutionRound
    NONE          -> PostResolutionRound
```

### Linearized flow diagram

```
ScanMarkets ──DONE──> PrepareResolutions ──DONE──> [MechInteract]
    |                       |                            |
    |--NONE--> [Done]       |--NO_TX--> [Done]           |
                                                         v
                                                  SubmitResolutions
                                                         |
                                              ──DONE──> [TxSettlement]
                                                         |
                                                         v
                                                   PostResolution
                                                         |
                                                         v
                                                      [Done]
```

### Round details

#### `ScanMarketsRound`
- **Adapted from**: current `GetPendingQuestionsBehaviour` (expanded scope)
- **Purpose**: Discover ALL markets needing resolution attention in a single pass
- **Queries**:
  1. **Omen subgraph** -- markets past openingTimestamp, answer not finalized, no bond posted yet (need initial answer)
  2. **Omen subgraph** -- markets with existing answers where we haven't yet evaluated (potential challenges)
  3. **Realitio subgraph** -- questions where WE are a previous answerer but someone else posted a newer answer (we've been challenged / re-challenged)
- **Configurable scope**:
  - `resolution_scope: "own" | "all"` -- track specific creators or any Omen market
  - `creator_addresses: List[str]` -- creator safe addresses to track (if scope is "own")
  - `min_market_liquidity: int` -- minimum liquidity to consider a market worth resolving
- **Classification** (all stored in SynchronizedData, processed linearly later):
  - `questions_to_answer: List[Dict]` -- unanswered questions
  - `questions_to_evaluate: List[Dict]` -- existing answers to check via Mech
  - `questions_to_escalate: List[Dict]` -- we've been re-challenged, need to re-assert or abandon
- **Priority**: Escalations first (time-sensitive, bonds at risk), then challenges, then new answers
- **Events**: `DONE` (work found), `NONE` (nothing to do), `ERROR`

#### `PrepareResolutionsRound`
- **Adapted from**: current `GetPendingQuestionsBehaviour` (Mech prep portion)
- **Purpose**: Build Mech metadata requests for ALL questions that need AI evaluation
- **Logic**:
  1. Read classified questions from SynchronizedData
  2. Check safe balance -- enough xDAI for all planned bonds?
  3. Apply retry policy (exponential backoff via `answer_retry_intervals`)
  4. For each question to answer: build standard Mech request (same as current)
  5. For each question to evaluate (challenge candidate): build Mech request with added context (current answer, current bond, market data)
  6. For escalations where we already know our answer: either skip Mech (emit NO_TX to go directly to SubmitResolutions) or re-evaluate with Mech for safety
  7. Combine into single mech_requests list
- **Events**: `DONE` (mech requests ready), `NO_TX` (only escalations, skip Mech), `ERROR`

#### `SubmitResolutionsRound`
- **Adapted from**: current `AnswerQuestionsBehaviour`
- **Purpose**: Build `submitAnswer` transactions for ALL resolution actions
- **Logic**:
  1. Parse mech_responses (or escalation data from SynchronizedData)
  2. For each question:
     - **New answer**: `submitAnswer(question_id, answer, 0)` with `value = initial_bond`
     - **Challenge**: `submitAnswer(question_id, our_answer, current_bond)` with `value = 2 * current_bond`
       - Only if Mech disagrees with existing answer AND confidence >= threshold
     - **Escalation**: `submitAnswer(question_id, our_answer, current_bond)` with `value = 2 * current_bond`
       - Only if bond < `max_challenge_bond` AND Mech still agrees with our answer
     - **Abandon**: skip -- Mech changed its mind, don't re-escalate
  3. Unwrap wxDAI to xDAI if needed for bond payments
  4. Build multisend: [unwrap txs] + [submitAnswer txs]
- **Events**: `DONE` (tx ready), `NO_TX` (Mech said skip all), `ERROR`

#### `PostResolutionRound`
- **Purpose**: Handle post-tx effects (e.g., update shared state tracking)
- **Logic**: Mark answered/challenged questions in shared state to avoid re-processing
- **Events**: `DONE`, `ERROR`

### Composed app: `market_resolver_abci`

```
Composition chain:
  AgentRegistrationAbciApp
  -> IdentifyServiceOwnerAbciApp
  -> FundsForwarderAbciApp
  -> FundRecoveryAbciApp                  # shared skill (same as market creator)
  -> MarketResolutionManagerAbciApp       # NEW: resolution + challenge
  -> TransactionSettlementAbciApp
  -> MechInteractAbciApp                  # needed for AI evaluation
  -> ResetPauseAbciApp
  + TerminationAbciApp (background)

Transition mapping:
  FinishedRegistrationRound               -> IdentifyServiceOwnerRound
  FinishedIdentifyServiceOwnerRound       -> FundsForwarderRound
  FinishedIdentifyServiceOwnerError       -> SyncLockedFundsRound
  FinishedFundsForwarderWithTxRound       -> TxSettlement
  FinishedFundsForwarderNoTxRound         -> SyncLockedFundsRound

  # Fund recovery loop
  FinishedRecoveryWithTxRound             -> TxSettlement
  FinishedRecoveryRound                   -> ScanMarketsRound

  # Resolution: prepare -> mech -> submit -> settle -> post
  FinishedWithMechRequestRound            -> MechVersionDetectionRound
  FinishedMechResponseRound               -> SubmitResolutionsRound
  FinishedMechRequestSkipRound            -> ScanMarketsRound
  FinishedMechResponseTimeoutRound        -> ScanMarketsRound
  FinishedResolutionWithTxRound           -> TxSettlement
  FinishedTransactionSubmissionRound      -> PostResolutionRound (or PostRecoveryRound)

  # Done
  FinishedResolutionRound                 -> ResetAndPauseRound

  # Reset
  FinishedResetAndPauseRound              -> IdentifyServiceOwnerRound
  FinishedResetAndPauseErrorRound         -> RegistrationRound
```

### Why answering and challenging are the same flow

Realitio's `submitAnswer(question_id, answer, max_previous)` is the same call for:

| Action | answer param | max_previous | bond (tx value) |
|--------|-------------|-------------|----------------|
| **First answer** | Mech's answer | 0 | `initial_bond` (e.g., 10 xDAI) |
| **Challenge** | Our different answer | current_bond | >= 2x current_bond |
| **Re-escalation** | Same answer as before | current_bond | >= 2x current_bond |

The only difference is the Mech prompt context and the bond amount. The FSM doesn't need branching -- ScanMarkets classifies upfront, PrepareResolutions builds appropriate Mech requests, SubmitResolutions builds appropriate txs. All linear.

### Fraud detection and challenge strategy

#### The attack pattern

An attacker can exploit Omen markets by combining trading with oracle manipulation:

```
1. Market: "Will X happen?" -- odds 90% Yes / 10% No
2. Attacker buys a large "No" position cheaply (10% implied price)
3. After openingTimestamp, attacker submits answer "No" with minimum bond (e.g., 10 xDAI)
4. If nobody challenges within the Realitio timeout, "No" finalizes
5. Attacker redeems "No" tokens at full value -- massive profit
6. LP (market creator) holds worthless "Yes" residual tokens -- loss
```

The attack is economically rational because:
- The cost is small: buy cheap tokens + post minimum bond
- The payoff is large: full collateral value of all "No" tokens
- The risk is low: if nobody monitors and challenges, the wrong answer sticks
- Bond loss on challenge is bounded: attacker only loses their posted bond

This is the primary adversarial scenario the market resolver must defend against.

#### What ScanMarketsRound must detect

ScanMarketsRound queries the Omen subgraph for markets with existing answers and classifies them. For fraud detection, it needs to identify **suspicious answers** -- answers that contradict market consensus. The key signals:

**Signal 1: Answer contradicts market odds**

```graphql
# Omen subgraph query for answered-but-not-finalized markets
{
  fixedProductMarketMakers(
    where: {
      creator_in: $creator_addresses       # markets we care about
      openingTimestamp_lt: $now
      answerFinalizedTimestamp: null        # not yet finalized
      currentAnswerBond_not: null           # someone has answered
    }
  ) {
    id
    outcomeTokenMarginalPrices             # implied probability per outcome
    outcomeTokenAmounts                    # pool token reserves
    currentAnswer                          # the posted answer
    question {
      id
      currentAnswerBond                    # bond amount on current answer
      timeout                              # seconds until finalization
      answers { answer, bondAggregate, lastBond }  # answer history
    }
  }
}
```

The resolver compares `currentAnswer` against `outcomeTokenMarginalPrices`:
- If currentAnswer is "No" (0x01) but marginalPrice[No] < 0.3 (market says 70%+ Yes), this is suspicious
- The bigger the divergence between answer and market consensus, the more suspicious
- Threshold: `min_odds_divergence` (e.g., 0.4 -- answer must contradict at least 40% of market weight)

**Signal 2: Answerer has a position on the winning side**

To confirm fraud (not just an honest disagreement), the resolver can check if the answerer holds tokens that would profit from their answer:

```graphql
# ConditionalTokens subgraph: check answerer's positions
{
  user(id: $answerer_address) {
    userPositions(where: {
      position_: { conditionIds_contains: [$condition_id] }
      balance_gt: "0"
    }) {
      balance
      position { indexSets }
    }
  }
}
```

If the answerer holds tokens on the SAME outcome they answered, it's a strong fraud signal. However, this query is optional -- the resolver should challenge incorrect answers regardless of attacker intent, because protecting the LP is the primary goal.

**Signal 3: Finalization urgency**

```
time_remaining = question.timeout - (now - last_answer_timestamp)
```

Questions close to finalization with suspicious answers are highest priority. If `time_remaining < escalation_timeout_buffer`, the resolver must act THIS cycle or the wrong answer finalizes.

#### Classification output

ScanMarketsRound produces a prioritized list in SynchronizedData:

```python
questions_to_resolve: List[Dict] = [
    {
        "question_id": "0x...",
        "market_id": "0x...",
        "action": "challenge",           # or "answer" or "escalate"
        "current_answer": "0x01",        # what's posted
        "market_odds": [0.85, 0.15],     # implied probabilities
        "current_bond": 10e18,           # bond on current answer (wei)
        "required_bond": 20e18,          # minimum to challenge (2x)
        "time_remaining": 43200,         # seconds until finalization
        "urgency": "high",              # high/medium/low
        "answerer": "0x...",             # who posted the current answer
        "answerer_has_position": True,   # fraud signal
    },
    ...
]
```

Priority ordering:
1. **Urgent escalations** -- we were re-challenged, timeout approaching
2. **Urgent challenges** -- suspicious answer, timeout approaching
3. **Normal challenges** -- suspicious answer, time remaining
4. **New answers** -- unanswered questions

#### Economic decision in PrepareResolutionsRound

Before building a challenge Mech request, PrepareResolutionsRound evaluates whether the challenge is economically justified:

```
Challenge cost   = required_bond (risk: lose if we're wrong)
Protected value  = LP_residual_tokens_value (what the creator would lose)
Bond profit      = attacker_bond (what we win if we're right)
```

The resolver should challenge when:
1. **Mech confidence >= threshold** (e.g., 0.85 that the current answer is wrong)
2. **Required bond <= max_challenge_bond** (absolute cap on risk)
3. **Economic ratio is favorable**: `(protected_value + bond_profit) / required_bond > min_challenge_ratio`

For example, if:
- Attacker posted 10 xDAI bond with wrong answer
- LP has 500 xDAI in residual tokens that would become worthless
- Challenge costs 20 xDAI (2x attacker's bond)
- Ratio: (500 + 10) / 20 = 25.5 -- very favorable

But if bond has been escalated to 200 xDAI and LP exposure is only 50 xDAI:
- Ratio: (50 + 200) / 400 = 0.625 -- questionable, depends on confidence

Configuration:
```yaml
min_odds_divergence: 0.4              # minimum gap between answer and market odds
min_challenge_ratio: 1.5              # minimum (protected + profit) / cost
max_challenge_bond: 100000000000000000000  # 100 xDAI absolute cap
escalation_timeout_buffer: 7200       # 2 hours -- must act if less time remaining
```

#### Bond escalation war

When the resolver challenges, the attacker may re-escalate. This creates a "bond war":

```
Round 1: Attacker answers "No"  with  10 xDAI bond
Round 2: Resolver answers "Yes" with  20 xDAI bond  (challenge)
Round 3: Attacker answers "No"  with  40 xDAI bond  (re-challenge)
Round 4: Resolver answers "Yes" with  80 xDAI bond  (re-escalate)
Round 5: Attacker answers "No"  with 160 xDAI bond  (re-challenge)
...
```

Each round doubles the bond. The total exposure for the resolver after N rounds:
```
total_exposure = initial_challenge * (2^N - 1)
```

The resolver's strategy for escalation wars:

1. **Re-evaluate each round**: When re-challenged (detected by ScanMarketsRound as `action: "escalate"`), PrepareResolutionsRound re-evaluates via Mech. If new evidence changes the picture, the resolver can ABANDON (accept the bond loss rather than throw good money after bad).

2. **Bond cap enforcement**: If the next required bond exceeds `max_challenge_bond`, the resolver stops escalating. The attacker "wins" the bond war but has also committed significant capital.

3. **Escalation round limit**: `max_escalation_rounds` caps how many times the resolver re-escalates per question (e.g., 5 rounds = up to 320x initial bond).

4. **Arbitration escape hatch** (future enhancement): If bond exceeds threshold, request arbitration from the configured arbitrator contract instead of continuing the bond war. This is a capped-cost resolution path but requires the arbitrator to be responsive.

#### What the resolver wins

If the resolver's answer is correct and finalizes:
- **All accumulated bonds** from the entire answer chain are credited via `claimWinnings`
- This includes the attacker's bonds from every escalation round
- The LP's residual tokens retain their value (market resolves correctly)
- `fund_recovery_abci` handles the `claimWinnings` + `withdraw` in the next cycle

If the resolver is wrong:
- The resolver loses all bonds it posted
- The attacker's answer finalizes
- This is why Mech confidence threshold is critical

#### End-to-end example

```
Cycle 1:
  ScanMarkets: finds market "Will BTC hit $100k by March?"
               currentAnswer = "No" (bond 10 xDAI)
               marketOdds = [0.82, 0.18] -- market says 82% Yes
               time_remaining = 48h
               --> classified as challenge, urgency=medium

  PrepareResolutions: builds Mech request with context:
    "Question: Will BTC hit $100k by March?
     Current answer: No (10 xDAI bond)
     Market consensus: 82% Yes
     Evaluate..."
    Mech returns: disagree, confidence=0.91, "BTC already at $99.5k"
    Economic check: LP exposure 300 xDAI, challenge cost 20 xDAI
    Ratio: (300 + 10) / 20 = 15.5 -- proceed

  SubmitResolutions: submitAnswer("Yes", max_previous=10 xDAI) with value=20 xDAI

Cycle 2:
  FundRecovery: nothing new to recover
  ScanMarkets: same question, but now we're the current answerer
               no re-challenge detected
               --> no action needed

Cycle 3:
  ScanMarkets: attacker re-challenged! currentAnswer = "No" (bond 40 xDAI)
               time_remaining = 36h
               --> classified as escalate, urgency=medium

  PrepareResolutions: re-evaluates via Mech
    Mech returns: disagree, confidence=0.93, "BTC hit $100.2k yesterday"
    Bond needed: 80 xDAI. Max bond: 100 xDAI. Within limits.
    Economic check: (300 + 50) / 80 = 4.4 -- proceed

  SubmitResolutions: submitAnswer("Yes", max_previous=40 xDAI) with value=80 xDAI

Cycle 4:
  ScanMarkets: no re-challenge. Timeout expires. "Yes" finalizes.

Cycle 5 (fund_recovery):
  ClaimBonds: claimWinnings for this question
              Resolver gets back: 80 (own bond) + 40 (attacker round 3) + 10 (attacker round 1) = 130 xDAI
              Net profit: 130 - 80 - 20 = 30 xDAI from bonds alone
              Plus: LP tokens protected (300 xDAI in creator's safe retains value)
  WithdrawBonds: withdraw 130 xDAI from Realitio to safe
```

### Configuration parameters

```yaml
# Scope
resolution_scope: "own"                            # "own" or "all"
creator_addresses: []                              # creator safe addresses to track
min_market_liquidity: 0                            # minimum liquidity to consider

# Answering
mech_tool_resolve_market: "resolve_market"         # Mech tool for new answers
questions_to_answer_batch_size: 5                  # max new answers per cycle
realitio_answer_question_bond: 10000000000000000000  # 10 xDAI initial bond
answer_retry_intervals: [86400, 259200]            # retry backoff (seconds)

# Challenging
challenge_confidence_threshold: 0.85               # Mech confidence to challenge
max_challenge_bond: 100000000000000000000           # 100 xDAI max per challenge
max_challenges_per_cycle: 3                        # limit per period
challenge_mech_tool: "evaluate_answer"             # Mech tool for challenge evaluation

# Escalation
max_escalation_rounds: 5                           # max re-escalations per question
escalation_timeout_buffer: 3600                    # seconds before timeout to act
```

### New Mech tool: `evaluate_answer`

Challenge and escalation evaluation requires a Mech tool that assesses an EXISTING answer:

```
Question: {question_text}
Current answer: {current_answer} (posted by {answerer} with bond {bond} xDAI)
Market liquidity: {liquidity} wxDAI
Resolution date: {resolution_date}

Evaluate whether the current answer is correct. Consider:
1. Current real-world evidence
2. Whether the question is still determinable
3. Confidence level in your assessment

Return: {agree|disagree|insufficient_evidence}, confidence (0-1), reasoning
```

---

## 6. Package Structure Changes

### New packages (dev)

```
packages/valory/
|-- skills/
|   |-- fund_recovery_abci/              # NEW: shared fund recovery
|   |   |-- __init__.py
|   |   |-- skill.yaml
|   |   |-- fsm_specification.yaml
|   |   |-- rounds.py
|   |   |-- payloads.py
|   |   |-- models.py
|   |   |-- handlers.py
|   |   |-- dialogues.py
|   |   |-- behaviours/
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   |-- sync_locked_funds.py
|   |   |   |-- remove_liquidity.py
|   |   |   |-- redeem_positions.py
|   |   |   |-- claim_bonds.py
|   |   |   |-- withdraw_bonds.py
|   |   |   |-- deposit_dai.py
|   |   |   `-- post_recovery.py
|   |   |-- states/
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   `-- ... (one per round)
|   |   `-- tests/
|   |       `-- ... (100% coverage)
|   |
|   |-- market_resolution_manager_abci/  # NEW: resolver core skill
|   |   |-- __init__.py
|   |   |-- skill.yaml
|   |   |-- fsm_specification.yaml
|   |   |-- rounds.py
|   |   |-- payloads.py
|   |   |-- models.py
|   |   |-- handlers.py
|   |   |-- dialogues.py
|   |   |-- behaviours/
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   |-- scan_markets.py
|   |   |   |-- prepare_resolutions.py
|   |   |   |-- submit_resolutions.py
|   |   |   `-- post_resolution.py
|   |   |-- states/
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   `-- ... (one per round)
|   |   `-- tests/
|   |       `-- ... (100% coverage)
|   |
|   |-- market_resolver_abci/            # NEW: resolver composed app
|   |   |-- __init__.py
|   |   |-- skill.yaml
|   |   |-- fsm_specification.yaml
|   |   |-- composition.py
|   |   |-- models.py
|   |   |-- handlers.py
|   |   |-- dialogues.py
|   |   |-- behaviours.py
|   |   `-- tests/
|   |
|   |-- market_creation_manager_abci/    # MODIFIED: slimmed (no recovery, no answering)
|   `-- market_maker_abci/               # MODIFIED: composes with fund_recovery_abci
|
|-- agents/
|   |-- market_maker/                    # MODIFIED
|   `-- market_resolver/                 # NEW
|
`-- services/
    |-- market_maker/                    # MODIFIED
    `-- market_resolver/                 # NEW
```

### packages.json changes

```json
{
  "dev": {
    "contract/valory/fpmm_deterministic_factory/0.1.0": "...",
    "contract/valory/fpmm/0.1.0": "...",
    "skill/valory/fund_recovery_abci/0.1.0": "...",
    "skill/valory/market_creation_manager_abci/0.1.0": "...",
    "skill/valory/market_maker_abci/0.1.0": "...",
    "skill/valory/market_resolution_manager_abci/0.1.0": "...",
    "skill/valory/market_resolver_abci/0.1.0": "...",
    "agent/valory/market_maker/0.1.0": "...",
    "agent/valory/market_resolver/0.1.0": "...",
    "service/valory/market_maker/0.1.0": "...",
    "service/valory/market_resolver/0.1.0": "..."
  }
}
```

---

## 7. Phased Implementation Plan

### Phase 0: Foundation (ClaimWinnings + lifecycle reorder)
**Goal**: Implement the missing ClaimWinningsRound and reorder the current FSM to lifecycle order. This establishes a clean baseline before splitting.

**Steps**:
1. Implement `ClaimWinningsRound` + `ClaimWinningsBehaviour` (per `claim_winnings.md`)
2. Reorder FSM to lifecycle order (per `fsm_lifecycle_restructure.md`)
3. Full test suite at 100% coverage
4. Full lint pipeline

**Deliverable**: Monolithic market creator with lifecycle-ordered FSM including ClaimWinnings

### Phase 1: Extract `fund_recovery_abci`
**Goal**: Extract all fund-recovery rounds into a standalone reusable skill.

**Steps**:
1. Create skill scaffold (skill.yaml, handlers, dialogues, models, payloads)
2. Move/adapt rounds:
   - SyncMarketsRound -> SyncLockedFundsRound (expanded queries)
   - RemoveFundingRound -> RemoveLiquidityRound
   - RedeemWinningsRound -> RedeemPositionsRound
   - ClaimWinningsRound -> ClaimBondsRound
   - RedeemBondRound -> WithdrawBondsRound
   - DepositDaiRound -> DepositDaiRound
3. Move corresponding behaviours with subgraph queries
4. Create PostRecoveryRound for post-tx routing
5. Define FSM specification, validate with `autonomy analyse fsm-specs`
6. Write full test suite (100% coverage)
7. Lint pipeline

**Deliverable**: Standalone `fund_recovery_abci` skill

### Phase 2: Slim down Market Creator
**Goal**: Remove recovery and answering rounds, compose with `fund_recovery_abci`.

**Steps**:
1. Remove rounds: SyncMarkets, RemoveFunding, RedeemWinnings, DepositDai, GetPendingQuestions, AnswerQuestions, RedeemBond, ClaimWinnings
2. Remove corresponding behaviours, payloads, states
3. Remove unused Event enum members
4. Simplify PostTransactionRound -> PostCreationRound
5. Update FSM transitions and specification
6. Update `market_maker_abci/composition.py`:
   - Add fund_recovery_abci to chain
   - Remove MechInteract from chain
   - Update transition mapping
7. Update skill.yaml, agent, service YAML files
8. Update/remove tests
9. Full lint pipeline

**Deliverable**: Slimmed Market Creator composing with fund_recovery_abci

### Phase 3: Create Market Resolver skill
**Goal**: Build `market_resolution_manager_abci` with answering + challenge logic.

**Steps**:
1. Create skill scaffold
2. Port answering logic:
   - ScanMarketsRound (from GetPendingQuestionsBehaviour, expanded)
   - PrepareResolutionsRound (from GetPendingQuestionsBehaviour mech prep)
   - SubmitResolutionsRound (from AnswerQuestionsBehaviour)
   - PostResolutionRound
3. Add challenge/escalation logic within the same linear rounds:
   - ScanMarketsRound: add challenge/escalation discovery queries
   - PrepareResolutionsRound: add challenge-evaluation Mech prompts
   - SubmitResolutionsRound: add challenge bond calculation
4. Define FSM specification, validate
5. Write full test suite (100% coverage)

**Deliverable**: `market_resolution_manager_abci` skill

### Phase 4: Compose Market Resolver service
**Goal**: Wire into a deployable service.

**Steps**:
1. Create `market_resolver_abci` composed app with composition.py
2. Create agent configuration
3. Create service configuration
4. Update packages.json
5. Full FSM spec validation across all skills
6. Full lint and test pipeline
7. Lock package hashes

**Deliverable**: Deployable Market Resolver service

### Phase 5: Integration testing & documentation
**Goal**: Validate both services work correctly and independently.

**Steps**:
1. Deploy both on testnet
2. Verify Creator creates markets without answering
3. Verify Resolver answers, challenges, and escalates
4. Verify fund recovery works for both
5. Verify no cross-service conflicts
6. Update CLAUDE.md, omen_lifecycle.md, FSM_AUDIT.md

**Deliverable**: Validated, documented split architecture

---

## 8. Risk Assessment

### High risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Bond management bugs** | Challenging with incorrect logic could lose significant funds | Strict confidence threshold, max_challenge_bond cap, conservative defaults. Extensive testing. |
| **Shared state conflicts** | Both services operating on same markets could interfere | Resolver checks `currentAnswerBond` to avoid re-answering. Each service tracks its own questions. Realitio's 2x bond requirement naturally prevents accidental double-answering. |
| **PostRecovery/PostResolution routing** | TxSettlement returns to the SAME PostRound entry point regardless of which skill's tx was settled. The composition must correctly route `FinishedTransactionSubmissionRound` to the right PostRound. | Use `tx_submitter` field to determine origin. Pattern already proven in current PostTransactionRound. |

### Medium risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Test coverage regression** | Extracting code requires rewriting ~5000 lines of tests | Budget significant time. Each phase includes full test suite. |
| **SyncLockedFundsRound complexity** | Consolidating 5 different subgraph queries into one round | Keep round focused: just query and store. Processing stays in individual rounds. |
| **Mech tool for challenges** | New `evaluate_answer` tool needs to work reliably | Start as wrapper around existing `resolve_market` with added context. |

### Low risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Third-party package compatibility** | Both services use same third-party packages | Pin exact versions in packages.json |
| **Subgraph query duplication** | Both services query similar Omen data | Accept -- they run on different safes |

---

## 9. Migration Strategy

**Recommendation**: Big-bang deployment. Deploy both services simultaneously to avoid a gap where questions go unanswered.

1. Complete all phases (0-4) before any deployment
2. Deploy Market Creator (v2) + Market Resolver simultaneously
3. Old monolithic service is stopped
4. Both new services start on their own safes
5. Market Creator's safe keeps existing LP positions (fund_recovery handles them)
6. Market Resolver's safe gets funded with xDAI for bonds

---

## 10. Open Questions

1. **Should the resolver resolve ALL Omen markets or only markets created by our creator?**
   - Config flag `resolution_scope` allows both modes
   - Resolving all markets increases ecosystem value but also bond exposure

2. **Should the resolver request arbitration when bond escalation exceeds the max?**
   - Defer to future phase -- adds complexity for edge case

3. **Should SyncLockedFundsRound do ALL queries or delegate discovery to each round?**
   - Current plan: centralized discovery in SyncLockedFunds, individual rounds just read and act
   - Alternative: each round does its own discovery (simpler SyncLockedFunds, but more subgraph calls per cycle)
   - Recommendation: centralized discovery -- fewer network calls, cleaner data flow

4. **How to handle TxSettlement routing when both fund_recovery and the action skill produce txs?**
   - `tx_submitter` field already identifies which round originated the tx
   - PostRecoveryRound and PostCreationRound/PostResolutionRound check this field to determine routing
   - The composition's `FinishedTransactionSubmissionRound` can map to a shared PostTxRouter that dispatches based on tx_submitter
