# Omen Prediction Market Lifecycle

A comprehensive reference for the CT framework, Omen markets, Realitio oracle, every contract method, and how to recover every type of locked fund.

---

## 1. Contract Stack

```
┌─────────────────────────────────────────────────────────────┐
│                      OMEN (UI + Subgraph)                    │
│                                                              │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │   FPMM   │    │  Conditional  │    │   Realitio   │      │
│   │  (AMM)   │    │    Tokens     │    │   (Oracle)   │      │
│   │ per-mkt  │    │  (singleton)  │    │  (singleton)  │     │
│   └────┬─────┘    └──────┬───────┘    └──────┬───────┘      │
│        │                 │                    │              │
│        │   splitPosition │    reportPayouts   │              │
│        │   mergePositions│    (via Proxy)      │             │
│        │   redeemPositions                     │             │
│        │                 │                    │              │
│   ┌────┴─────┐    ┌──────┴───────┐    ┌──────┴───────┐      │
│   │  FPMM    │    │  Realitio    │    │    wxDAI     │      │
│   │ Factory  │    │   Proxy      │    │   (ERC20)    │      │
│   │(singleton)│   │ (singleton)  │    │  (singleton)  │     │
│   └──────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Contract inventory

| Contract | Gnosis Address | Singleton? | Role |
|----------|---------------|-----------|------|
| **ConditionalTokens** | `0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce` | Yes (1 per chain) | ERC-1155 token system. Manages conditions, positions, splitting/merging, redemption. |
| **Realitio** (v2.1) | `0x79e32aE03fb27B07C89c0c568F80287C01ca2E57` | Yes (1 per chain) | Oracle. Holds bonds, accepts answers, pays out bond winners. Internal balance per address. |
| **RealitioProxy** | configured per deployment | Yes (1 per env) | Bridge: reads Realitio answers → calls `reportPayouts` on CT. |
| **FPMMDeterministicFactory** | configured per deployment | Yes (1 per env) | Deploys FPMM markets with deterministic addresses (CREATE2). |
| **FPMM** | per-market address | No (1 per market) | AMM pool for trading outcome tokens. Constant-product formula. |
| **wxDAI** (ERC20) | `0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d` | Yes (1 per chain) | Wrapped xDAI — collateral for all Omen markets on Gnosis. |
| **Arbitrator** | configured per deployment | Yes (1 per env) | Dispute resolution (rarely used). |

---

## 2. The Conditional Tokens (CT) Framework

### What it is

ConditionalTokens is an **ERC-1155 token system** by Gnosis. It represents conditional outcomes as transferable tokens — tokens that only have value if a specific real-world condition resolves a certain way.

### Core concepts

- **Condition:** A registered question with N possible outcomes. Created via `prepareCondition()`. Each condition has `condition_id = keccak256(oracle, question_id, outcome_count)`.
- **Position:** A claim on collateral that pays out if a specific outcome occurs. Positions are ERC-1155 tokens.
- **Collateral:** The underlying token backing positions (wxDAI on Gnosis).
- **Index sets:** Bitmask representing which outcomes a position covers. For binary (Yes/No): `1` (binary `01`) = outcome 0 (Yes), `2` (binary `10`) = outcome 1 (No).

### On-chain storage

```
mapping(bytes32 => uint[]) public payoutNumerators;   // [0, 0] initially → [1, 0] after resolution
mapping(bytes32 => uint)   public payoutDenominator;   // 0 initially → 1 after resolution
```

- `payoutDenominator == 0` → condition is **unresolved** (this is what `check_resolved()` checks)
- `payoutDenominator > 0` → condition is **resolved**

### How `prepareCondition()` works on-chain

```solidity
ConditionalTokens.prepareCondition(
    address oracle,         // who can call reportPayouts (for Omen: RealitioProxy)
    bytes32 questionId,     // external question identifier (for Omen: the Realitio question_id)
    uint outcomeSlotCount   // number of possible outcomes (typically 2 for binary)
)
```

What happens:

1. Computes `conditionId = keccak256(oracle, questionId, outcomeSlotCount)` — deterministic, computable off-chain before the tx.
2. Stores `payoutNumerators[conditionId] = new uint[](outcomeSlotCount)` — array of zeros.
3. Initializes `payoutDenominator[conditionId] = 0`.
4. Emits `ConditionPreparation(conditionId, oracle, questionId, outcomeSlotCount)`.

No tokens are created yet, no collateral locked. Just a record that outcome slots exist.

**Why the conditionId is deterministic:** The FPMM Factory needs the conditionId to create the market, but the condition must be prepared first. Since the id is deterministic, the market creation multisend can prepare the condition and reference its id in the same transaction.

### Relationship between condition and positions

Positions (ERC-1155 tokens) are only created when someone calls `splitPosition()`. Token IDs are derived from the conditionId:

```
positionId = keccak256(collateralToken, collectionId)
collectionId = keccak256(conditionId, indexSet)
```

Each (condition, outcome, collateral) triple maps to a unique ERC-1155 token ID.

### Position lifecycle

```
           prepareCondition()                    splitPosition()
Collateral ──────────────────→ Condition registered ──────────────→ Outcome tokens exist
(wxDAI)                        (no tokens yet)                     (ERC-1155 tokens)


                mergePositions()                                   redeemPositions()
Outcome tokens ─────────────────→ Collateral returned    OR    ───────────────────→ Collateral
(equal amounts                    (ANY time, no                   (winning tokens      returned
 of ALL outcomes)                  resolution needed)              only, AFTER resolve)
```

### Position operations

| Operation | When | What happens | Requires resolution? |
|-----------|------|-------------|---------------------|
| `splitPosition(collateral, condition, amount)` | Any time | Locks `amount` collateral, mints `amount` of EACH outcome token | No |
| `mergePositions(collateral, condition, amount)` | Any time | Burns `amount` of EVERY outcome token, returns `amount` collateral | No |
| `redeemPositions(collateral, condition, indexSets)` | After resolution | Burns winning outcome tokens, returns collateral proportional to payout | Yes |
| `reportPayouts(question_id, payouts[])` | At resolution | Sets the payout vector — only callable by the designated oracle | N/A (this IS resolution) |

### Splitting and merging

Splitting 100 wxDAI into a binary condition:
- 100 wxDAI is locked in the CT contract
- You receive 100 "Yes" tokens AND 100 "No" tokens
- Total value conserved: 100 Yes + 100 No = 100 wxDAI always

Merging is the reverse. If you hold 50 Yes AND 50 No, merge them back into 50 wxDAI — no resolution needed. This is how LPs recover collateral from unresolved markets.

### Payout mechanics

At resolution, `reportPayouts(questionId, payouts[])` sets a **payout vector** that always sums to 1.

**Binary market examples:**

| Payout vector | Meaning | 100 Yes tokens redeem for | 100 No tokens redeem for |
|--------------|---------|--------------------------|-------------------------|
| `[1, 0]` | Yes won | 100 wxDAI | 0 |
| `[0, 1]` | No won | 0 | 100 wxDAI |
| `[0.7, 0.3]` | Scalar result | 70 wxDAI | 30 wxDAI |

**Multi-outcome market example** (e.g., "Who wins?" with 4 candidates):

Splitting 100 wxDAI gives you 100 of each: A, B, C, D tokens.

| Payout vector | Meaning | A redeems | B redeems | C redeems | D redeems |
|--------------|---------|-----------|-----------|-----------|-----------|
| `[1, 0, 0, 0]` | A won | 100 wxDAI | 0 | 0 | 0 |
| `[0.5, 0.5, 0, 0]` | Split A/B | 50 wxDAI | 50 wxDAI | 0 | 0 |

In practice, almost all Omen markets are binary with `[1, 0]` or `[0, 1]`.

### The oracle role

CT doesn't care HOW the answer is determined. It only needs someone to call `reportPayouts()`. The "oracle" is the address specified in `prepareCondition()`. For Omen, this is the **RealitioProxy** contract.

---

## 3. How Realitio Works

### The answer cycle

```
askQuestion()        submitAnswer()       submitAnswer()          timeout expires
────────────→ Q open ──────────────→ Answer A ──────────────→ Answer B ─────────────→ FINALIZED
              (no answer)    (bond: 10 xDAI)   (bond: 20 xDAI)        (B wins)
                                                (must be >= 2x)
```

**Key rules:**
- Each new answer must post a bond >= 2x the previous bond
- The timeout resets with each new answer
- When timeout expires, the last posted answer becomes final
- Bonds are in **native xDAI**, not wxDAI

### Answer encoding (Omen convention)

- `0x00...00` = outcomes[0] = "Yes"
- `0x00...01` = outcomes[1] = "No"
- `0xff...ff` = INVALID

### Bond settlement

After finalization, `claimWinnings()` settles the bond chain:

```
submitAnswer(10 xDAI) → submitAnswer(20 xDAI) → timeout → claimWinnings()
       ↓                       ↓                              ↓
 10 xDAI locked          20 xDAI locked              30 xDAI credited
 in Realitio             in Realitio              to winner's internal balance
                                                         ↓
                                                   withdraw()
                                                         ↓
                                                  30 xDAI → winner's wallet
```

### Two-step withdrawal

1. **`claimWinnings(question_id, ...)`** — settles the bond chain, credits the winner's internal balance. Must be called per-question. Requires reconstructing the full answer history.
2. **`withdraw()`** — transfers the entire internal balance to the caller. Not per-question — it drains everything.

If nobody calls `claimWinnings()`, the internal balance stays at 0 and `withdraw()` has nothing to send.

---

## 4. Two Independent Value Flows

There are **two completely separate pots of money** in an Omen market:

```
                    Realitio question finalized
                    (timeout expired)
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     RealitioProxy.resolve()    Realitio.claimWinnings()
              │                         │
              ▼                         ▼
     CT.redeemPositions()       Realitio.withdraw()
              │                         │
              ▼                         ▼
         wxDAI back                xDAI back
```

- **Left branch (`resolve` → `redeemPositions`)** — reads finalized answer, translates to payout vector, writes to CT. Unlocks `redeemPositions()` for outcome token holders. About the **market collateral** (wxDAI).
- **Right branch (`claimWinnings` → `withdraw`)** — settles the bond chain inside Realitio. Credits the winning answerer's internal balance. About the **oracle bonds** (native xDAI).

You can call one without the other.

### `resolve()` vs `claimWinnings()` — the key distinction

| | `resolve()` | `claimWinnings()` |
|---|---|---|
| **Contract** | RealitioProxy → ConditionalTokens | Realitio |
| **What it does** | Reports finalized Realitio answer to CT (`reportPayouts`) | Settles bond chain, credits winner's internal balance |
| **Event emitted** | `ConditionResolution` (on CT) | `LogClaim` (on Realitio) |
| **Unlocks** | `redeemPositions()` — outcome tokens → wxDAI | `withdraw()` — internal balance → xDAI |
| **Who needs it** | Anyone holding conditional tokens (LPs, traders) | Anyone who posted bonds (market creator, challengers) |
| **Currency recovered** | wxDAI (collateral) | native xDAI (bonds) |
| **Parameters** | `question_id, template_id, question_data, num_outcomes` | `question_id, history_hashes[], addrs[], bonds[], answers[]` |
| **Complexity** | Simple — 4 params from subgraph | Complex — must reconstruct full answer history from `LogNewAnswer` events |

### Who calls what in practice

| Caller | `resolve()` | `claimWinnings()` | `redeemPositions()` | `withdraw()` |
|--------|---|---|---|---|
| **Trader** | Yes (to unlock token redemption) | Sometimes (if they also answered) | Yes (to get winning bet back) | Sometimes |
| **Market creator (LP)** | Yes (to unlock LP residual redemption) | Yes (to recover posted bonds) | Yes (to redeem LP excess tokens) | Yes (to extract claimed bonds) |
| **External answerer** | No | Yes (to recover bonds) | No | Yes |

---

## 5. Market Lifecycle — Phase by Phase

### Phase 1: Market Creation (LP)

All four steps happen atomically in a single multisend transaction:

```
Safe (multisend) ──→ wxDAI.approve(Factory, amount)
                 ──→ Realitio.askQuestion(...)                    → question_id created
                 ──→ ConditionalTokens.prepareCondition(Proxy, qId, 2) → condition_id created
                 ──→ Factory.create2FPMM(CT, wxDAI, [condId], fee, funds)
                         │
                         ├─→ wxDAI.transferFrom(Safe, Factory, funds)
                         ├─→ CT.splitPosition(wxDAI, 0, condId, [1,2], funds)
                         ├─→ deploys new FPMM contract
                         └─→ deposits outcome tokens into FPMM
```

After creation:
- Creator holds LP shares (representing their liquidity position)
- NO wxDAI (it's locked as collateral in CT, managed by FPMM)
- Market has: a Realitio question, a CT condition, an FPMM pool with balanced outcome tokens

### Phase 2: Trading (Trader)

```
Buy:
  1. ERC20.approve(FPMM, investmentAmount)
  2. FPMM.buy(investmentAmount, outcomeIndex, minOutcomeTokensToBuy)
     → FPMM takes wxDAI, calls CT.splitPosition(), keeps opposite tokens, sends chosen tokens to trader
     → Pool imbalances → price of chosen outcome goes up

Sell:
  1. ConditionalTokens.setApprovalForAll(FPMM, true)
  2. FPMM.sell(returnAmount, outcomeIndex, maxOutcomeTokensToSell)
     → FPMM takes outcome tokens, calls CT.mergePositions() where possible, sends wxDAI to trader
```

Trading fees stay in the pool and are captured by the LP when removing liquidity.

### Phase 3: Question Resolution (Oracle)

```
Realitio.submitAnswer(question_id, answer, max_previous)
  → Submit answer with bond (native xDAI sent as tx value)
  → answer: 0x00...00 = Yes, 0x00...01 = No, 0xff...ff = Invalid
  → Each subsequent answer must at least double the bond
  → After timeout with no new answer, last answer is finalized
  → Bond held in Realitio until claimWinnings is called
```

The market-creator's `AnswerQuestionsBehaviour` does this using Mech responses. It unwraps wxDAI to xDAI before posting the bond.

### Phase 4: Remove Liquidity (LP)

```
Safe (multisend) ──→ FPMM.removeFunding(shares)
                         └─→ returns outcome tokens to Safe
                 ──→ CT.mergePositions(wxDAI, 0, condId, slots, amount)
                         └─→ burns equal outcome tokens, returns wxDAI to Safe
                 ──→ wxDAI.withdraw(amount)  [optional]
                         └─→ unwraps wxDAI to xDAI
```

**After this step:** Safe holds residual conditional tokens on exactly one side (the heavier side from trading). These cannot be converted to collateral until the condition is resolved.

### Phase 5: Condition Resolution (Bridge Oracle → CT)

```
Safe ──→ RealitioProxy.resolve(qId, templateId, question, numOutcomes)
              │
              ├─→ Realitio.resultFor(qId) → reads finalized answer
              └─→ CT.reportPayouts(qId, [1, 0]) → condition resolved
```

Sets `payoutNumerators` and `payoutDenominator` for the condition. One-time operation. After this, `redeemPositions` works.

### Phase 6: Redeem Conditional Tokens (LP and Trader)

```
Safe ──→ CT.redeemPositions(wxDAI, 0, condId, [1, 2])
              └─→ burns outcome tokens, returns wxDAI to Safe
```

- For each outcome: `payout = balance[i] * payoutNumerator[i] / payoutDenominator`
- Winning tokens → full collateral value
- Losing tokens → 0 (burns them, doesn't revert)
- `indexSets = [1, 2]` for binary markets (one bit per outcome)

**Prerequisite:** `resolve()` must have been called (Phase 5).

### Phase 7: Claim Bond Winnings (Answerer)

```
Safe ──→ Realitio.claimWinnings(qId, hashes[], addrs[], bonds[], answers[])
              └─→ credits Safe's internal Realitio balance
```

Parameters must be reconstructed from `LogNewAnswer` events, reverse-chronological order.

**For uncontested questions** (single answerer — common for market creator):
```python
history_hashes = [bytes32(0)]     # no previous answer
addrs = [safe_address]            # the answerer
bonds = [bond_amount]             # the bond posted
answers = [answer_bytes]          # the answer value
```

**For contested questions** (multiple answerers):
```python
# Ordered reverse-chronologically (newest first)
history_hashes = [hash_n, hash_n-1, ..., bytes32(0)]
addrs = [addr_n, addr_n-1, ..., addr_1]
bonds = [bond_n, bond_n-1, ..., bond_1]
answers = [answer_n, answer_n-1, ..., answer_1]
```

### Phase 8: Withdraw Bonds (Answerer)

```
Safe ──→ Realitio.withdraw()
              └─→ transfers internal balance as native xDAI to Safe
```

**Prerequisite:** `claimWinnings()` must have been called (Phase 7).

### Phase 9: Deposit DAI (LP)

```
wxDAI.deposit()   [payable]
  → Wrap native xDAI into wxDAI (ERC20) for the next cycle of market creation
```

---

## 6. Market-Creator FSM Mapping

| FSM Round | Lifecycle Phase | What it does |
|-----------|----------------|---|
| `DepositDaiRound` | Phase 9 | wxDAI.deposit() |
| `GetPendingQuestionsRound` | — | Query subgraph for unanswered questions |
| `MechInteract` | — | Get AI answers from Mech |
| `AnswerQuestionsRound` | Phase 3 | wxDAI.withdraw() + submitAnswer |
| `CollectProposedMarketsRound` | — | Fetch market proposals |
| `ApproveMarketsRound` | — | Validate via LLM |
| `PrepareTransactionRound` | Phase 1 | approve + askQuestion + prepareCondition + create2FPMM |
| `OmenFpmmRemoveLiquidity` | Phase 4 | removeFunding + mergePositions + withdraw |
| `OmenCtRedeemTokens` | Phase 5 + 6 | resolve (if needed) + redeemPositions |
| `OmenRealitioWithdrawBonds` | Phase 7 + 8 | claimWinnings + withdraw |

---

## 7. Fund Recovery Guide

Four types of locked funds, each with its own discovery query, on-chain check, and recovery path.

### Type 1: LP Shares in FPMM

**What is locked:** Your share of the FPMM liquidity pool.
**When recoverable:** Any time (no resolution needed).

```graphql
{
  fpmmPoolMemberships(where: {funder: "$safe", amount_gt: "0"}, first: 1000) {
    pool {
      id
      openingTimestamp
      liquidityMeasure
      outcomeTokenAmounts
      conditions {
        id
        question { id }
        outcomeSlotCount
      }
    }
  }
}
```

**On-chain check:** `FPMM.balanceOf(safe) > 0`

**Recovery (multisend):**
```
1. FPMM.removeFunding(shares)
   → Burns LP shares, returns outcome tokens proportional to pool share
   → You now hold e.g. 80 Yes tokens + 120 No tokens

2. CT.mergePositions(wxDAI, 0, conditionId, outcomeSlotCount, min(80,120))
   → Burns 80 Yes + 80 No, returns 80 wxDAI

3. wxDAI.withdraw(80)  [optional — unwrap to xDAI]

After this you still hold 40 excess No tokens → recover via Type 2.
```

### Type 2: Conditional Token Positions (Winning Outcome Tokens)

**What is locked:** Outcome tokens from LP removal excess, or trader-bought tokens.
**When recoverable:** Only after condition is resolved on CT.

```graphql
# CT subgraph — find positions with balance
{
  user(id: "$safe") {
    userPositions(where: {balance_gt: "0"}, first: 1000) {
      balance
      position {
        conditionIds
        indexSets
      }
    }
  }
}

# Then check which conditions have finalized markets:
{
  fixedProductMarketMakers(
    where: {
      conditions_: {id_in: [$conditionIds]}
      answerFinalizedTimestamp_not: null
      answerFinalizedTimestamp_lt: "$now"
    }
  ) {
    id
    payouts
    templateId
    question { id, data }
    conditions { id, outcomeSlotCount }
  }
}
```

**On-chain check:** `CT.payoutDenominator(conditionId) > 0` → already resolved. If 0, need to resolve first.

**Recovery (multisend):**
```
# Step 1 (only if condition not yet resolved):
RealitioProxy.resolve(questionId, templateId, questionData, numOutcomes)

# Step 2:
CT.redeemPositions(wxDAI, 0, conditionId, [1, 2])
   → Burns ALL outcome tokens for this condition
   → Returns wxDAI proportional to payout × balance
   → Winning tokens → full collateral value
   → Losing tokens → 0
```

### Type 3: Realitio Bonds (claimWinnings)

**What is locked:** xDAI bonds posted when answering questions.
**When recoverable:** After question finalization.

```graphql
{
  responses(
    where: {
      user: "$safe"
      question_: {
        answerFinalizedTimestamp_not: null
        answerFinalizedTimestamp_lt: "$now"
      }
    }
    first: 1000
  ) {
    question { id, createdBlock, updatedBlock }
    bond
    answer
  }
}
```

**On-chain check:** `Realitio.getHistoryHash(questionId)` — if `bytes32(0)`, already claimed. If non-zero, unclaimed.

**Recovery:**
```
# Step 1: Reconstruct answer history from LogNewAnswer events
Realitio.get_claim_params(fromBlock, toBlock, questionId)
   → Returns: history_hashes[], addresses[], bonds[], answers[]

# Step 2: Claim the bonds
Realitio.claimWinnings(questionId, historyHashes[], addrs[], bonds[], answers[])
   → Credits winner's internal Realitio balance
   → Does NOT transfer xDAI — only credits internal balance

# Step 3: Withdraw (see Type 4)
```

### Type 4: Realitio Internal Balance (withdraw)

**What is locked:** xDAI credited inside Realitio from `claimWinnings()` or received bonds.
**When recoverable:** Any time balance > 0.

**On-chain check:** `Realitio.balanceOf(safe)` — single RPC call, no subgraph needed.

**Recovery:**
```
Realitio.withdraw()
   → Transfers entire internal balance as native xDAI to caller
```

---

## 8. Visual Summary

```
                    LP (market-creator)                          Trader
                    ═══════════════════                          ══════
                           │
            ┌──────────────┴──────────────┐
            │  1. approve + askQuestion    │
            │  2. prepareCondition         │
            │  3. create2FPMM (+ fund)    │
            └──────────────┬──────────────┘
                           │
                    Market is live
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            │         ┌────┴────┐         │
            │         │ Trading │ ←───── approve + buy/sell
            │         └────┬────┘         │
            │              │              │
       submitAnswer        │              │
       (via Mech)          │              │
            │              │              │
            │         Answer finalizes    │
            │         (timeout expires)   │
            │              │              │
    ┌───────┴───────┐      │              │
    │ removeFunding │      │              │
    │ mergePositions│      │              │
    │ withdraw      │      │              │
    └───────┬───────┘      │              │
            │              │              │
            │    CONDITIONAL TOKENS FLOW  │
            │    ~~~~~~~~~~~~~~~~~~~~~~~~ │
            │              │       ┌──────┴──────┐
            │              │       │   resolve   │ ← reports answer to CT
            │              │       └──────┬──────┘
    ┌───────┴───────┐      │       ┌──────┴──────┐
    │ redeemPositns │◄─────┼───────│ redeemPositns│ ← both get wxDAI back
    └───────┬───────┘      │       └──────┴──────┘
            │              │              │
            │    REALITIO BOND FLOW       │
            │    ~~~~~~~~~~~~~~~~~~~~~~   │
            │              │       ┌──────┴──────┐
            │              │       │claimWinnings│ ← settles bond chain
    ┌───────┴───────┐      │       └──────┬──────┘
    │ claimWinnings │      │       ┌──────┴──────┐
    │ withdraw()    │      │       │  withdraw() │ ← both get xDAI back
    └───────┬───────┘      │       └──────┬──────┘
            │              │              │
    ┌───────┴───────┐      │              │
    │ depositDai    │      │              │
    │ (wrap xDAI)   │      │              │
    └───────┬───────┘      │              │
            │              │              │
    ┌───────┴───────┐      │              │
    │ create new    │      │              │
    │ markets       │      │              │
    └───────────────┘      │              │
```

---

## 9. Subgraph Reference

| Subgraph | URL | Key entities |
|----------|-----|-------------|
| Omen | `https://gateway.thegraph.com/api/[key]/subgraphs/id/9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz` | `fixedProductMarketMakers`, `fpmmPoolMemberships` |
| ConditionalTokens | `https://conditional-tokens.subgraph.autonolas.tech` | `user.userPositions`, `position.conditionIds`, `position.indexSets` |
| Realitio | `https://realitio.subgraph.autonolas.tech` | `responses(user:)`, `question.answerFinalizedTimestamp` |

**Subgraph quirk:** Omen subgraph returns `"0"` (string zero) for unset timestamps, not `null`. Use `answerFinalizedTimestamp_gt: 0` not `_not: null`.

---

## 10. Complete Method Reference

| Stage | Contract | Method | Creates | Currency | Singleton? |
|-------|----------|--------|---------|----------|-----------|
| Create question | Realitio | `askQuestion()` | question_id | — | Yes |
| Create condition | ConditionalTokens | `prepareCondition()` | condition_id | — | Yes |
| Create market | FPMMFactory | `create2FPMM()` | FPMM contract | wxDAI (initial liquidity) | Factory: yes, FPMM: no |
| Buy tokens | FPMM | `buy()` | — | wxDAI → outcome tokens | Per-market |
| Sell tokens | FPMM | `sell()` | — | outcome tokens → wxDAI | Per-market |
| Add liquidity | FPMM | `addFunding()` | LP shares | wxDAI → outcome tokens | Per-market |
| Remove liquidity | FPMM | `removeFunding()` | — | LP shares → outcome tokens | Per-market |
| Merge positions | ConditionalTokens | `mergePositions()` | — | equal outcome tokens → wxDAI | Yes |
| Answer question | Realitio | `submitAnswer()` | — | native xDAI (bond) | Yes |
| Resolve condition | RealitioProxy | `resolve()` | — | — (bridge call) | Yes |
| Redeem positions | ConditionalTokens | `redeemPositions()` | — | winning tokens → wxDAI | Yes |
| Claim bonds | Realitio | `claimWinnings()` | — | → internal balance | Yes |
| Withdraw bonds | Realitio | `withdraw()` | — | internal balance → xDAI | Yes |
| Wrap xDAI | wxDAI (ERC20) | `deposit()` | — | xDAI → wxDAI | Yes |
| Unwrap wxDAI | wxDAI (ERC20) | `withdraw()` | — | wxDAI → xDAI | Yes |
