# Plan: Split Market Creator into Market Creator + Market Resolver

## Context

The `market_creation_manager_abci` skill currently handles the entire lifecycle of Omen prediction markets: creating markets, answering questions (via Mech), collecting LP tokens, redeeming conditional tokens, claiming bonds, and wrapping xDAI. This monolithic design makes the FSM large (14 active rounds, 9 final states, 17 events), hard to reason about, and impossible to run answering/challenging logic independently of market creation.

The goal is to split into **two independent services** that can run on separate safes:

1. **Market Creator** -- creates prediction markets, manages LP positions
2. **Market Resolver** -- answers questions, challenges incorrect answers, manages Realitio bonds

Plus a **shared `omen_funds_recoverer_abci` skill** (IMPLEMENTED) that both services use to recover ALL types of locked funds (LP tokens, conditional tokens, Realitio bonds). Fund recovery runs FIRST in each cycle, so services always operate with maximum available capital. Uses a tx accumulation pattern — 3 recovery rounds append tx dicts, then BuildMultisend bundles them into one safe multisend.

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

1. **Linear FSMs only** -- no conditional branching. Every round either produces a tx (routes through TxSettlement + PostTx, then returns to the next round) or skips (NONE -> next round directly).
2. **Recovery first, action second** -- each cycle starts by recovering ALL types of locked funds, THEN does the service-specific work (create markets or resolve questions). This ensures maximum capital is available for the action phase.
3. **One shared skill for ALL fund recovery** -- `omen_funds_recoverer_abci` handles LP tokens, conditional tokens, and Realitio bonds. Both services compose it. Recovery rounds accumulate tx dicts into `funds_recovery_txs`, then a final `BuildMultisendRound` bundles them into a single safe multisend. **Only one TxSettlement round trip per cycle** (not one per recovery type). DepositDai (xDAI wrapping) is excluded -- it's capital management, not recovery.
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
================= omen_funds_recoverer_abci ====================
  |
RemoveLiquidity -> RedeemPositions -> ClaimBonds -> BuildMultisend
  (each round accumulates tx dicts into funds_recovery_txs;
   BuildMultisend bundles them into ONE safe multisend)
  |
  |-- FinishedWithRecoveryTx --> [TxSettlement] --> PostTransaction
  |-- FinishedWithoutRecoveryTx -.
  |                               |
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
================= omen_funds_recoverer_abci ====================
  |
RemoveLiquidity -> RedeemPositions -> ClaimBonds -> BuildMultisend
  (each round accumulates tx dicts into funds_recovery_txs;
   BuildMultisend bundles them into ONE safe multisend)
  |
  |-- FinishedWithRecoveryTx --> [TxSettlement] --> PostTransaction
  |-- FinishedWithoutRecoveryTx -.
  |                               |
===================================================================
  |
  v
=============== market_resolution_manager_abci ====================
  |
ScanMarkets
  |
  v
EvaluateAnswers ---DONE---> [MechInteract] -.
  |--- NONE -------.                         |
  v                |                         |
BuildChallengesTx <+-------------------------'
  |
  v
BuildChallengesTx ---DONE---> [TxSettlement] -> CleanupTracking
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
- Both services have the IDENTICAL `omen_funds_recoverer_abci` block. The market creator won't typically have Realitio bonds (it doesn't answer questions), so ClaimBonds produces no txs. The resolver won't typically have LP tokens, so RemoveLiquidity produces no txs. Each round's subgraph query returns empty and it appends nothing to `funds_recovery_txs`. If no round finds work, BuildMultisend sees an empty list and emits NONE (no TxSettlement needed).
- The resolver's `ScanMarkets -> EvaluateAnswers -> [MechInteract] -> BuildChallengesTx -> CleanupTracking` is a linear path. ScanMarkets classifies markets by whitelist. EvaluateAnswers builds Mech requests for non-whitelisted answers. BuildChallengesTx compares Mech responses and builds `submitAnswer` txs for disagreements. Answering and challenging are the SAME Realitio call, just with different bond amounts.

---

## 3. Shared Skill: `omen_funds_recoverer_abci` (IMPLEMENTED)

> **Status:** Implemented and tested (170 tests). See `.claude/plans/omen_funds_recoverer.md` for the detailed v3 plan.

### Purpose

A reusable skill that recovers ALL types of locked funds from an Omen prediction market safe. Runs first in every cycle to maximize available capital for subsequent rounds.

### Key design change from original plan

The original plan had each recovery round producing its own tx and going through TxSettlement separately, requiring a PostRecovery router. This was replaced with a **tx accumulation pattern**:

- 3 recovery rounds (RemoveLiquidity, RedeemPositions, ClaimBonds) each query their own subgraph and append tx dicts to `funds_recovery_txs` in SynchronizedData
- A final `BuildMultisendRound` bundles everything into ONE safe multisend
- **One TxSettlement round trip per cycle** instead of up to 3
- **No PostRecovery router** — eliminates the `tx_submitter` string coupling with the parent app
- **Single initial state, 2 final states** — trivial composition
- **DepositDai excluded** — capital management, not recovery
- **No wxDAI unwrap** — recovered funds stay as wxDAI in the safe

### FSM specification (v3 — as implemented)

```
Rounds:
  0. RemoveLiquidityRound       (accumulates txs)
  1. RedeemPositionsRound       (accumulates txs)
  2. ClaimBondsRound            (accumulates txs)
  3. BuildMultisendRound        (bundles all into one safe multisend)
  4. FinishedWithRecoveryTxRound   (degenerate -> TxSettlement in composition)
  5. FinishedWithoutRecoveryTxRound (degenerate -> next skill in composition)

Initial state: RemoveLiquidityRound
Initial states: {RemoveLiquidityRound}

Transition function:
  RemoveLiquidityRound:
    DONE          -> RedeemPositionsRound
    NO_MAJORITY   -> RedeemPositionsRound
    ROUND_TIMEOUT -> RedeemPositionsRound

  RedeemPositionsRound:
    DONE          -> ClaimBondsRound
    NO_MAJORITY   -> ClaimBondsRound
    ROUND_TIMEOUT -> ClaimBondsRound

  ClaimBondsRound:
    DONE          -> BuildMultisendRound
    NO_MAJORITY   -> BuildMultisendRound
    ROUND_TIMEOUT -> BuildMultisendRound

  BuildMultisendRound:
    DONE          -> FinishedWithRecoveryTxRound
    NONE          -> FinishedWithoutRecoveryTxRound
    NO_MAJORITY   -> FinishedWithoutRecoveryTxRound
    ROUND_TIMEOUT -> FinishedWithoutRecoveryTxRound
```

### Flow diagram

```
RemoveLiquidity ──► RedeemPositions ──► ClaimBonds ──► BuildMultisend
  (accumulates       (accumulates        (accumulates     (bundles all
   LP removal txs)    resolve+redeem)     claim+withdraw)  into 1 multisend)
                                                              │
                                                    ┌─────────┴──────────┐
                                                    v                    v
                                          FinishedWithTx      FinishedWithoutTx
                                          (→ TxSettlement)    (→ next skill)
```

Each recovery round queries its own subgraph, builds raw tx dicts, and appends them to `funds_recovery_txs`. BuildMultisend reads the accumulated list and bundles into one safe multisend. Only one TxSettlement round trip per cycle.

### Round details

> Detailed round specifications are in `.claude/plans/omen_funds_recoverer.md`.
> Below is a summary of the v3 implementation.

#### `RemoveLiquidityRound`
- **Self-contained**: queries Omen subgraph for LP positions, verifies on-chain
- **Logic**: For markets where `openingTimestamp - liquidity_removal_lead_time < now`, build removeFunding + mergePositions tx dicts
- **Appends to**: `funds_recovery_txs`

#### `RedeemPositionsRound`
- **Self-contained**: queries CT subgraph for held positions + Omen subgraph for finalized markets
- **Logic**: Cross-reference, for winning positions build resolve (if needed) + redeemPositions tx dicts
- **Appends to**: `funds_recovery_txs`

#### `ClaimBondsRound`
- **Self-contained**: queries Realitio subgraph for finalized responses by safe
- **Logic**: Check getHistoryHash (skip if claimed), build claimWinnings tx dicts + withdraw() if balance > threshold
- **Appends to**: `funds_recovery_txs`

#### `BuildMultisendRound`
- **Reads**: `funds_recovery_txs` from SynchronizedData
- **Logic**: If empty → NONE (no tx). If non-empty → bundle into one safe multisend → DONE

### Final states

| Final State | Routes to (in composition) |
|---|---|
| `FinishedWithRecoveryTxRound` | -> TxSettlement (settle the single multisend) |
| `FinishedWithoutRecoveryTxRound` | -> next skill in chain (market creation or resolution) |

### Configuration parameters

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

### Contracts required

| Contract | Methods used |
|----------|-------------|
| FPMM | removeFunding, get_balance, get_total_supply, get_markets_with_funds |
| ConditionalTokens | mergePositions, redeemPositions, check_resolved, get_user_holdings |
| RealitioProxy | resolve |
| Realitio | claimWinnings, withdraw, balanceOf, getHistoryHash, get_claim_params, simulate_claim_winnings |
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

### What is removed (moved to omen_funds_recoverer_abci or resolver)

| Round | Destination |
|-------|------------|
| `SyncMarketsRound` | omen_funds_recoverer_abci -> RemoveLiquidityRound (self-contained query) |
| `RemoveFundingRound` | omen_funds_recoverer_abci -> RemoveLiquidityRound |
| `RedeemWinningsRound` | omen_funds_recoverer_abci -> RedeemPositionsRound |
| `DepositDaiRound` | Removed (capital management, not recovery) |
| `GetPendingQuestionsRound` | market_resolution_manager_abci -> ScanMarketsRound |
| `AnswerQuestionsRound` | market_resolution_manager_abci -> BuildChallengesTxRound |
| `RedeemBondRound` | omen_funds_recoverer_abci -> ClaimBondsRound (includes withdraw) |
| `PostTransactionRound` | Recovery routing eliminated (tx accumulation pattern). Creation routing stays as PostCreationRound |

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
  FinishedIdentifyServiceOwnerError   -> RemoveLiquidityRound
  FinishedFundsForwarderWithTxRound   -> TxSettlement
  FinishedFundsForwarderNoTxRound     -> RemoveLiquidityRound

  # Fund recovery -> single multisend -> TxSettlement -> PostTransaction
  FinishedWithRecoveryTxRound         -> TxSettlement
  FinishedWithoutRecoveryTxRound      -> CollectRandomnessRound

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
- All omen_funds_recoverer_abci contract dependencies (via composed skill)

---

## 5. New Skill: `market_resolution_manager_abci` (Watchdog)

### Purpose

Autonomous market watchdog — monitors Omen prediction markets for incorrect or malicious Realitio answers, and challenges them. Inspired by the manual [watchdog](https://github.com/valory-xyz/watchdog) CLI tool, but fully autonomous as an ABCI skill.

### Core logic (watchdog flow)

```
For each cycle:

0. SCAN: Fetch all pending (unfinalized) markets from watched creators
         (Omen subgraph: creator_in: $watched_addresses, answerFinalizedTimestamp: null)

1. FILTER by latest answerer:
   - If latest response is from a WHITELISTED address → skip (trusted answer)
     Whitelist = our safe, market creators, other configurable addresses
   - If NO answer yet → needs initial answer (standard resolve)
   - If answer from NON-whitelisted address → needs evaluation (potential attack)

2. EVALUATE via Mech:
   - Query Mech with the market question + current answer context
   - Compare Mech's answer vs the on-chain answer:

     a) Mech AGREES with on-chain answer:
        → Mark as "verified_ok" in local tracking DB
        → Do NOT challenge — the answer is correct even if from unknown address
        → Store this verdict locally so we don't re-query Mech on subsequent cycles

     b) Mech DISAGREES with on-chain answer:
        → Store Mech response + metadata locally
        → CHALLENGE: build submitAnswer tx with 2x bond and Mech's answer

3. SUBMIT: Build multisend with all challenge txs for this cycle

4. CLEANUP: Purge local tracking DB entries for markets that have been
   definitively finalized (answerFinalizedTimestamp != null)
```

### Why this flow matters

The watchdog protects against the attack pattern where an adversary:
1. Buys cheap outcome tokens on the "wrong" side
2. Posts a small-bond answer that contradicts market consensus
3. If unchallenged, the wrong answer finalizes and the attacker profits

By continuously monitoring and challenging, the watchdog:
- Defends the market creator's LP positions
- Earns bond profits when challenges succeed (attacker loses their bond)
- Acts as a "good samaritan" for the ecosystem

### Local tracking database

The skill needs persistent cross-period state to avoid redundant Mech queries:

```python
# Stored in SynchronizedData (cross_period_persisted_keys)
verified_markets: Dict[str, VerifiedMarketEntry] = {
    "question_id_hex": {
        "verified_at": 1711900000,           # timestamp of verification
        "on_chain_answer": "0x00...00",      # the answer that was verified as correct
        "mech_agrees": True,                 # Mech confirmed the answer
    }
}
```

**Lifecycle:**
- Added when Mech agrees with a non-whitelisted answer (step 2a)
- Consulted on each scan to skip already-verified markets
- Purged when the market finalizes (answer accepted, timeout expired)
- If someone re-challenges a verified market (new answer appears), the entry is invalidated and re-evaluated

### Whitelist rationale

The whitelist avoids unnecessary Mech queries for trusted answerers:
- **Our own safe**: We trust our own answers
- **Market creators**: They have skin in the game (LP positions at risk)
- **Configurable addresses**: Other trusted resolvers in the ecosystem

If a whitelisted address answered, we trust it and move on. Only non-whitelisted answers trigger Mech evaluation.

### FSM specification

```
Rounds:
  0. ScanMarketsRound           # scan pending markets, filter by whitelist
  1. EvaluateAnswersRound       # query Mech for non-whitelisted answers
  2. BuildChallengesTxRound     # build submitAnswer txs for disagreements
  3. CleanupTrackingRound       # purge finalized markets from local DB
  4. FinishedWithMechRequestRound      (degenerate -> MechInteract)
  5. FinishedWithChallengeTxRound      (degenerate -> TxSettlement)
  6. FinishedResolutionRound           (degenerate -> ResetPause)

Initial state: ScanMarketsRound
Initial states: {ScanMarketsRound, BuildChallengesTxRound}

Transition function:
  ScanMarketsRound:
    DONE          -> EvaluateAnswersRound     # found markets needing evaluation
    NONE          -> CleanupTrackingRound     # nothing to evaluate this cycle
    NO_MAJORITY   -> ScanMarketsRound
    ROUND_TIMEOUT -> ScanMarketsRound

  EvaluateAnswersRound:
    DONE          -> FinishedWithMechRequestRound  # -> MechInteract -> BuildChallenges
    NONE          -> CleanupTrackingRound           # all verified ok, nothing to challenge
    NO_MAJORITY   -> CleanupTrackingRound
    ROUND_TIMEOUT -> CleanupTrackingRound

  BuildChallengesTxRound:
    DONE          -> FinishedWithChallengeTxRound  # -> TxSettlement -> Cleanup
    NONE          -> CleanupTrackingRound           # Mech agreed with all, no challenges
    NO_MAJORITY   -> CleanupTrackingRound
    ROUND_TIMEOUT -> CleanupTrackingRound

  CleanupTrackingRound:
    DONE          -> FinishedResolutionRound
    NO_MAJORITY   -> FinishedResolutionRound
    ROUND_TIMEOUT -> FinishedResolutionRound
```

### Flow diagram

```
ScanMarkets ──DONE──► EvaluateAnswers ──DONE──► [MechInteract]
    |                       |                         |
    |──NONE──┐              |──NONE──┐                v
             |                       |         BuildChallengesTx
             |                       |                |
             |                       |     ──DONE──► [TxSettlement]
             |                       |                |
             v                       v                v
         CleanupTracking ◄────────────────────────────┘
             |
             v
       [FinishedResolution]
```

### Round details

#### `ScanMarketsRound`

**Purpose**: Discover pending markets from watched creators and classify by answerer.

**Queries** (Omen + Realitio subgraphs):

```graphql
# Omen subgraph: unfinalized markets from watched creators
fixedProductMarketMakers(
  where: {
    creator_in: $watched_addresses
    openingTimestamp_lt: $now
    answerFinalizedTimestamp: null
  }
) {
  id, currentAnswer, question { id, currentAnswerBond, timeout }
  outcomeTokenMarginalPrices
}
```

Then for each answered market, fetch latest responder from Realitio subgraph.

**Classification logic:**

```
for each pending market:
    if no answer yet:
        → add to questions_to_answer (standard resolve, needs Mech)
    elif latest_answerer in whitelist:
        → skip (trusted)
    elif question_id in verified_markets AND on_chain_answer == verified_answer:
        → skip (already verified by Mech in a previous cycle)
    else:
        → add to questions_to_evaluate (needs Mech evaluation)
```

**Whitelist**: `whitelist_addresses: List[str]` — configurable list containing:

- Our own safe address (auto-included)
- Market creator addresses
- Other trusted resolver addresses

**Events**: `DONE` (found markets needing Mech), `NONE` (nothing to evaluate)

#### `EvaluateAnswersRound`

**Purpose**: Build Mech requests for markets that need AI evaluation.

**Logic:**

1. Read `questions_to_answer` and `questions_to_evaluate` from SynchronizedData
2. For new answers: build standard Mech request (question text only)
3. For challenges: build Mech request with context (current answer, bond, market odds)
4. Combine into `mech_requests` list
5. If list is empty (all were filtered by whitelist/verification) → NONE

**Events**: `DONE` (mech requests ready → MechInteract), `NONE` (nothing to evaluate)

#### `BuildChallengesTxRound`

**Purpose**: After MechInteract returns, compare Mech answers with on-chain answers and build challenge txs.

**Logic:**

```
for each mech_response:
    if question was unanswered:
        → build submitAnswer(question_id, mech_answer, 0) with value = initial_bond

    elif mech_answer AGREES with on_chain_answer:
        → add to verified_markets (local tracking DB)
        → do NOT challenge

    elif mech_answer DISAGREES with on_chain_answer:
        → store mech_response in local tracking DB
        → check economic viability:
            - required_bond = 2 * current_bond
            - if required_bond > max_challenge_bond → skip (too expensive)
            - if safe balance < required_bond → skip (insufficient funds)
        → build submitAnswer(question_id, mech_answer, current_bond) with value = 2x bond
```

**Bond amounts**: All `submitAnswer` calls use native xDAI as `msg.value`. If safe holds wxDAI, unwrap first.

**Events**: `DONE` (challenge txs built → TxSettlement), `NONE` (Mech agreed with all answers)

#### `CleanupTrackingRound`

**Purpose**: Purge finalized markets from `verified_markets` local DB.

**Logic:**

1. Query Omen subgraph for markets in `verified_markets` that now have `answerFinalizedTimestamp != null`
2. Remove those entries from `verified_markets`
3. This keeps the DB bounded — only tracks active/pending markets

**Events**: `DONE` (always — cleanup is best-effort)

### Composed app: `market_resolver_abci`

```
Composition chain:
  AgentRegistrationAbciApp
  -> IdentifyServiceOwnerAbciApp
  -> FundsForwarderAbciApp
  -> OmenFundsRecovererAbciApp             # shared skill (same as market creator)
  -> MarketResolutionManagerAbciApp        # watchdog: scan + evaluate + challenge
  -> TransactionSettlementAbciApp
  -> MechInteractAbciApp                   # needed for AI evaluation
  -> ResetPauseAbciApp
  + TerminationAbciApp (background)

Transition mapping:
  FinishedRegistrationRound               -> IdentifyServiceOwnerRound
  FinishedIdentifyServiceOwnerRound       -> FundsForwarderRound
  FinishedIdentifyServiceOwnerError       -> RemoveLiquidityRound
  FinishedFundsForwarderWithTxRound       -> TxSettlement
  FinishedFundsForwarderNoTxRound         -> RemoveLiquidityRound

  # Fund recovery
  FinishedWithRecoveryTxRound             -> TxSettlement
  FinishedWithoutRecoveryTxRound          -> ScanMarketsRound

  # Watchdog: scan -> evaluate -> mech -> build challenges -> settle -> cleanup
  FinishedWithMechRequestRound            -> MechVersionDetectionRound
  FinishedMechResponseRound               -> BuildChallengesTxRound
  FinishedMechRequestSkipRound            -> CleanupTrackingRound
  FinishedMechResponseTimeoutRound        -> CleanupTrackingRound
  FinishedWithChallengeTxRound            -> TxSettlement
  FinishedTransactionSubmissionRound      -> CleanupTrackingRound

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

The only difference is the Mech prompt context and the bond amount. The FSM doesn't need branching — ScanMarkets classifies upfront, EvaluateAnswers builds appropriate Mech requests, BuildChallengesTx builds the submitAnswer txs. All linear.

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

#### What ScanMarketsRound detects

ScanMarketsRound queries the Omen subgraph for pending markets from watched creators with existing answers. It classifies them by checking the latest answerer against the whitelist. For non-whitelisted answers, the following signals help prioritize:

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

ScanMarketsRound produces a prioritized list of markets needing evaluation in SynchronizedData:

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

#### Economic decision in BuildChallengesTxRound

Before building a challenge tx, BuildChallengesTxRound evaluates whether the challenge is economically justified:

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
# Watchdog scope
watched_addresses: []                 # market creator safe addresses to monitor
whitelist_addresses: []               # trusted answerers (our safe auto-included)

# Challenge economics
min_odds_divergence: 0.4              # minimum gap between answer and market odds
min_challenge_ratio: 1.5              # minimum (protected + profit) / cost
max_challenge_bond: 100000000000000000000  # 100 xDAI absolute cap (wei)
escalation_timeout_buffer: 7200       # 2 hours -- must act if less time remaining

# Answering
realitio_answer_question_bond: 10000000000000000000  # 10 xDAI initial bond (wei)
mech_tool_resolve_market: "resolve-market-reasoning-gpt-4.1"

# Escalation
max_escalation_rounds: 5              # max re-escalations per question
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

1. **Re-evaluate each round**: When re-challenged (detected by ScanMarketsRound as non-whitelisted new answer on a previously verified market), EvaluateAnswersRound re-evaluates via Mech. If new evidence changes the picture, the resolver can ABANDON (accept the bond loss rather than throw good money after bad). The `verified_markets` entry is invalidated and re-evaluated fresh.

2. **Bond cap enforcement**: If the next required bond exceeds `max_challenge_bond`, the resolver stops escalating. The attacker "wins" the bond war but has also committed significant capital.

3. **Escalation round limit**: `max_escalation_rounds` caps how many times the resolver re-escalates per question (e.g., 5 rounds = up to 320x initial bond).

4. **Arbitration escape hatch** (future enhancement): If bond exceeds threshold, request arbitration from the configured arbitrator contract instead of continuing the bond war. This is a capped-cost resolution path but requires the arbitrator to be responsive.

#### What the resolver wins

If the resolver's answer is correct and finalizes:
- **All accumulated bonds** from the entire answer chain are credited via `claimWinnings`
- This includes the attacker's bonds from every escalation round
- The LP's residual tokens retain their value (market resolves correctly)
- `omen_funds_recoverer_abci` handles the `claimWinnings` + `withdraw` in the next cycle

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

  EvaluateAnswers: builds Mech request with context:
    "Question: Will BTC hit $100k by March?
     Current answer: No (10 xDAI bond)
     Market consensus: 82% Yes
     Evaluate..."
    Mech returns: disagree, confidence=0.91, "BTC already at $99.5k"
    Economic check: LP exposure 300 xDAI, challenge cost 20 xDAI
    Ratio: (300 + 10) / 20 = 15.5 -- proceed

  BuildChallengesTx: submitAnswer("Yes", max_previous=10 xDAI) with value=20 xDAI

Cycle 2:
  FundRecovery: nothing new to recover
  ScanMarkets: same question, but now we're the current answerer
               no re-challenge detected
               --> no action needed

Cycle 3:
  ScanMarkets: attacker re-challenged! currentAnswer = "No" (bond 40 xDAI)
               time_remaining = 36h
               --> classified as escalate, urgency=medium

  EvaluateAnswers: re-evaluates via Mech
    Mech returns: disagree, confidence=0.93, "BTC hit $100.2k yesterday"
    Bond needed: 80 xDAI. Max bond: 100 xDAI. Within limits.
    Economic check: (300 + 50) / 80 = 4.4 -- proceed

  BuildChallengesTx: submitAnswer("Yes", max_previous=40 xDAI) with value=80 xDAI

Cycle 4:
  ScanMarkets: no re-challenge. Timeout expires. "Yes" finalizes.

Cycle 5 (fund_recovery):
  ClaimBonds: claimWinnings for this question
              Resolver gets back: 80 (own bond) + 40 (attacker round 3) + 10 (attacker round 1) = 130 xDAI
              Net profit: 130 - 80 - 20 = 30 xDAI from bonds alone
              Plus: LP tokens protected (300 xDAI in creator's safe retains value)
  ClaimBonds: claimWinnings + withdraw 130 xDAI from Realitio to safe
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
|   |-- omen_funds_recoverer_abci/              # IMPLEMENTED: shared fund recovery
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
|   |   |   |-- remove_liquidity.py
|   |   |   |-- redeem_positions.py
|   |   |   |-- claim_bonds.py
|   |   |   |-- build_multisend.py
|   |   |   `-- round_behaviour.py
|   |   `-- tests/
|   |       `-- ... (170 tests)
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
|   `-- market_maker_abci/               # MODIFIED: composes with omen_funds_recoverer_abci
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
    "skill/valory/omen_funds_recoverer_abci/0.1.0": "...",
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

### Phase 0+1: `omen_funds_recoverer_abci` (DONE)
**Goal**: Create a standalone reusable skill that recovers all locked funds from Omen markets.

**What was done** (differs from original plan):
- Skipped the monolithic ClaimWinnings + lifecycle reorder — went straight to standalone skill
- Built `omen_funds_recoverer_abci` with tx accumulation pattern (not per-round TxSettlement)
- 3 self-contained recovery rounds + BuildMultisend, no SyncLockedFunds or PostRecovery
- Validated with Tenderly simulations (`simulate_redemption.py`, `simulate_redeem_no_merge.py`)
- 170 tests passing, formatted with isort + black

**Deliverable**: Standalone `omen_funds_recoverer_abci` skill at `packages/valory/skills/omen_funds_recoverer_abci/`
**Detailed plan**: `.claude/plans/omen_funds_recoverer.md`

### Phase 2: Slim down Market Creator
**Goal**: Remove recovery and answering rounds, compose with `omen_funds_recoverer_abci`.

**Steps**:

1. Remove rounds: SyncMarkets, RemoveFunding, RedeemWinnings, DepositDai, GetPendingQuestions, AnswerQuestions, RedeemBond
2. Remove corresponding behaviours, payloads, states
3. Remove unused Event enum members
4. Simplify PostTransactionRound -> PostCreationRound
5. Update FSM transitions and specification
6. Update `market_maker_abci/composition.py`:
   - Add `omen_funds_recoverer_abci` to chain
   - Map `FinishedWithRecoveryTxRound` -> TxSettlement
   - Map `FinishedWithoutRecoveryTxRound` -> MarketCreationManager initial round
   - Add one `tx_submitter` string check in PostTransaction for recovery tx routing
   - Remove MechInteract from chain (moves to resolver)
7. Update skill.yaml, agent, service YAML files
8. Update/remove tests
9. Full lint pipeline

**Deliverable**: Slimmed Market Creator composing with `omen_funds_recoverer_abci`

### Phase 3: Create Market Resolver skill
**Goal**: Build `market_resolution_manager_abci` with answering + challenge logic.

**Steps**:
1. Create skill scaffold
2. Port answering logic:
   - ScanMarketsRound (from GetPendingQuestionsBehaviour, expanded)
   - EvaluateAnswersRound (builds Mech requests for non-whitelisted answers)
   - BuildChallengesTxRound (compares Mech vs on-chain, builds challenge txs)
   - CleanupTrackingRound (purges finalized markets from local DB)
3. Implement watchdog logic:
   - ScanMarketsRound: whitelist filtering, verified_markets lookup
   - EvaluateAnswersRound: Mech request building with answer context
   - BuildChallengesTxRound: Mech comparison, economic checks, bond calculation
   - CleanupTrackingRound: prune finalized entries from verified_markets
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
| **TxSettlement routing** | TxSettlement returns to a single PostTx entry point. The composition must route correctly. | Recovery skill uses tx accumulation (one multisend), so only one `tx_submitter` string to check. Proven simpler than per-round TxSettlement routing. |

### Medium risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Test coverage regression** | Extracting code requires rewriting ~5000 lines of tests | Budget significant time. Each phase includes full test suite. |
| **Subgraph query reliability** | Each recovery round depends on its subgraph being available | Rounds that fail to query produce no txs (safe degradation). BuildMultisend bundles whatever was found. |
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

3. ~~**Should SyncLockedFundsRound do ALL queries or delegate discovery to each round?**~~ **RESOLVED**: Each round does its own discovery (self-contained subgraph queries). Subgraph queries are fast (<1s) for safe-filtered results, so the overhead is negligible.

4. ~~**How to handle TxSettlement routing when both fund_recovery and the action skill produce txs?**~~ **RESOLVED**: The tx accumulation pattern eliminates this problem. Recovery produces ONE multisend, so the parent's PostTransaction only needs one `tx_submitter` string check. No PostRecoveryRound or shared router needed.
