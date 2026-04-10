# Omen Prediction Market Lifecycle

This document covers the full lifecycle of an Omen prediction market on Gnosis Chain, from both the **Liquidity Provider** (market-creator) and **Trader** perspectives, with the specific contract methods called at each step.

## Contracts involved

| Contract | Gnosis Address | Role |
|----------|---------------|------|
| **ConditionalTokens** | `0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce` | ERC-1155 token system for outcome positions. Manages conditions, position splitting/merging, and redemption. |
| **Realitio** (Reality.eth v2.1) | `0x79e32aE03fb27B07C89c0c568F80287C01ca2E57` | Oracle for question resolution. Holds bonds, accepts answers, and pays out bond winners. Has its own internal balance per address. |
| **RealitioProxy** | configured per deployment | Bridge between Realitio answers and ConditionalTokens conditions. Reads finalized answers from Realitio and calls `reportPayouts` on CT. |
| **FPMMDeterministicFactory** | configured per deployment | Factory that deploys FPMM market contracts with deterministic addresses (CREATE2). |
| **FPMM** (FixedProductMarketMaker) | per-market address | AMM pool for trading outcome tokens. Implements constant-product formula. |
| **wxDAI** (ERC20) | `0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d` | Wrapped xDAI, used as collateral for all markets on Gnosis chain. |

## Two independent value flows

There are **two completely separate pots of money** in an Omen market. They use different contracts and different recovery mechanisms:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONDITIONAL TOKENS FLOW                          │
│                    (outcome token redemption)                       │
│                                                                     │
│  Source: LP residual tokens / Trader bought tokens                  │
│  Contract: ConditionalTokens                                        │
│  Currency: wxDAI (collateral)                                       │
│  Prerequisite: resolve() must be called first                       │
│  Recovery: redeemPositions() → wxDAI to caller                     │
│                                                                     │
│  resolve()  ──────────→  redeemPositions()  ──────→  wxDAI         │
│  (RealitioProxy)         (ConditionalTokens)                        │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    REALITIO BOND FLOW                                │
│                    (answer bond settlement)                          │
│                                                                     │
│  Source: Bonds posted when answering questions                      │
│  Contract: Realitio                                                  │
│  Currency: native xDAI                                               │
│  Prerequisite: claimWinnings() must be called first                 │
│  Recovery: claimWinnings() → internal balance → withdraw() → xDAI  │
│                                                                     │
│  claimWinnings()  ──→  Realitio.balanceOf()  ──→  withdraw()       │
│  (Realitio)            (internal balance)          (Realitio)        │
└─────────────────────────────────────────────────────────────────────┘
```

These flows are **completely independent**. You can do one without the other. They unlock different funds from different contracts.

### `resolve()` vs `claimWinnings()` — the key distinction

| | `resolve()` | `claimWinnings()` |
|---|---|---|
| **Contract** | RealitioProxy → ConditionalTokens | Realitio |
| **What it does** | Reports the finalized Realitio answer to ConditionalTokens (`reportPayouts`) | Settles the bond chain for a question, credits the winner's internal Realitio balance |
| **Event emitted** | `ConditionResolution` (on CT) | `LogClaim` (on Realitio) |
| **Unlocks** | `redeemPositions()` — exchange outcome tokens for wxDAI | `withdraw()` — transfer xDAI from Realitio to caller |
| **Who needs it** | Anyone holding conditional tokens (LPs with residual tokens, traders with bought tokens) | Anyone who posted bonds when answering (typically the market creator, sometimes challengers) |
| **Currency recovered** | wxDAI (collateral from the market pool) | native xDAI (bond refunds + loser's bonds) |
| **Parameters** | `question_id, template_id, question_data, num_outcomes` | `question_id, history_hashes[], addrs[], bonds[], answers[]` |
| **Complexity** | Simple — 4 params from the subgraph | Complex — requires reconstructing the full answer history chain from `LogNewAnswer` events |

### Who calls what in practice

| Caller | `resolve()` | `claimWinnings()` | `redeemPositions()` | `withdraw()` |
|--------|---|---|---|---|
| **Trader** | Yes (to unlock their token redemption) | Sometimes (if they also answered) | Yes (to get their winning bet back) | Sometimes |
| **Market creator (LP)** | Yes (to unlock LP residual token redemption) | Yes (to recover the bonds it posted) | Yes (to redeem LP excess tokens) | Yes (to extract the claimed bonds) |
| **External answerer** | No | Yes (to recover their bonds) | No | Yes |

## Phase 1: Market Creation (LP)

The market-creator builds a single multisend transaction with these steps:

```
1. ERC20.approve(FPMMFactory, initialFunds)
   → Allow the factory to spend wxDAI for initial liquidity

2. Realitio.askQuestion(template_id, question, arbitrator, timeout, opening_ts, nonce)
   → Create an oracle question. Returns question_id.
   → template_id=2 for binary Yes/No questions
   → timeout: time after last answer before finalization

3. ConditionalTokens.prepareCondition(oracle, questionId, outcomeSlotCount)
   → Register a condition. The condition_id = keccak256(oracle, questionId, outcomeSlotCount).
   → Internally creates outcomeSlotCount payout slots (typically 2: Yes/No).

4. FPMMDeterministicFactory.create2FixedProductMarketMaker(
       saltNonce, conditionalTokens, collateralToken, conditionIds, fee, initialFunds, distributionHint)
   → Deploy an FPMM contract and fund it in one atomic step.
   → The factory splits collateral into outcome tokens via CT, then deposits them into the AMM pool.
   → Returns pool shares (LP tokens) to the creator.
```

After this, the market is live and tradeable on Omen.

## Phase 2: Trading (Trader)

Traders interact with the FPMM to buy/sell outcome tokens:

```
Buy:
  1. ERC20.approve(FPMM, investmentAmount)
     → Allow the FPMM to pull collateral
  2. FPMM.buy(investmentAmount, outcomeIndex, minOutcomeTokensToBuy)
     → Deposit collateral, receive outcome tokens for the chosen side
     → The AMM adjusts prices based on the constant-product invariant

Sell:
  1. ConditionalTokens.setApprovalForAll(FPMM, true)
     → Allow the FPMM to pull outcome tokens (ERC-1155)
  2. FPMM.sell(returnAmount, outcomeIndex, maxOutcomeTokensToSell)
     → Return outcome tokens, receive collateral back
```

Each trade shifts the pool's token ratio, changing the implied probability (price) of each outcome. This imbalances the pool — one side accumulates more tokens than the other. Trading fees stay in the pool and are captured by the LP when removing liquidity.

## Phase 3: Question Resolution (Oracle)

After the market's `openingTimestamp` passes, anyone can answer the question:

```
Realitio.submitAnswer(question_id, answer, max_previous)
  → Submit an answer with a bond (native xDAI sent as tx value).
  → answer: 0x00...00 = Yes, 0x00...01 = No, 0xff...ff = Invalid
  → Each subsequent answer must at least double the bond.
  → After timeout with no new answer, the last answer is finalized.
  → The bond is held in the Realitio contract until claimWinnings is called.
```

The market-creator's `AnswerQuestionsBehaviour` does this using Mech (AI oracle) responses. It unwraps wxDAI to xDAI before posting the bond.

## Phase 4: Remove Liquidity (LP)

The market-creator removes its LP position through a multisend:

```
1. FPMM.removeFunding(sharesToBurn)
   → Burn LP tokens, receive proportional outcome tokens for each side.
   → Due to trading activity, the pool is imbalanced — you get MORE tokens
     on the side traders bought (the "heavier" side) and FEWER on the other.
   → Accumulated trading fees are included (no separate fee claim needed).

2. ConditionalTokens.mergePositions(collateralToken, parentCollectionId, conditionId, partition, amount)
   → Merge equal amounts of ALL outcome tokens back into collateral.
   → amount = min(balance_outcome_0, balance_outcome_1, ...)
   → This converts the "balanced" portion back to wxDAI.
   → The EXCESS tokens on the heavier side remain as residual conditional tokens.

3. ERC20.withdraw(amount)   [wxDAI specific — unwraps to native xDAI]
   → Convert recovered wxDAI back to native xDAI in the safe.
```

**After this step**: The safe holds residual conditional tokens on exactly one side (the heavier side). These cannot be converted to collateral until the condition is resolved.

## Phase 5: Condition Resolution (Bridge Oracle → CT)

Before anyone can redeem conditional tokens, the Realitio answer must be reported to ConditionalTokens:

```
RealitioProxy.resolve(question_id, template_id, question, num_outcomes)
  → Reads the finalized answer from Realitio
  → Calls ConditionalTokens.reportPayouts(questionId, payouts)
  → Emits ConditionResolution event
  → Sets payoutNumerators and payoutDenominator for the condition
  → Example: Yes wins → numerators=[1,0], denominator=1
```

**Who calls this?** Typically traders as part of their redemption flow. The market-creator's `RedeemWinningsBehaviour` also calls it for conditions not yet resolved ("lazy resolution").

**Important:** This only unlocks `redeemPositions`. It has nothing to do with bonds.

## Phase 6: Redeem Conditional Tokens (LP and Trader)

Exchange outcome tokens for collateral. Works for both LP residual tokens and trader-bought tokens:

```
ConditionalTokens.redeemPositions(collateralToken, parentCollectionId, conditionId, indexSets)
  → For each outcome: payout = balance[i] * payoutNumerator[i] / payoutDenominator
  → Burns the conditional tokens (TransferSingle to 0x000...000)
  → Transfers collateral (wxDAI) to the caller
  → If the caller's tokens are on the WINNING side → receives collateral
  → If the caller's tokens are on the LOSING side → receives nothing (payout = 0)
  → Safe to call with losing tokens — doesn't revert, just burns them
  → Emits PayoutRedemption event with the payout amount
  → indexSets = [1, 2] for binary markets (one bit per outcome)
```

**Prerequisite:** `resolve()` must have been called (Phase 5). Without it, `payoutDenominator == 0` and payout is always 0.

## Phase 7: Claim Bond Winnings (Answerer)

Settle the Realitio bond chain and credit the winner's internal balance:

```
Realitio.claimWinnings(question_id, history_hashes[], addrs[], bonds[], answers[])
  → Processes the answer history chain in reverse chronological order
  → The final (correct) answerer receives all accumulated bonds
  → Credits the winner's INTERNAL Realitio balance (not a transfer!)
  → Emits LogClaim event
  → Parameters must be reconstructed from LogNewAnswer events

  For uncontested answers (sole answerer, common for market-creator):
    history_hashes = [bytes32(0)]
    addrs = [answerer_address]
    bonds = [bond_amount]
    answers = [answer_bytes]

  For contested answers (multiple answerers):
    Full history chain needed from LogNewAnswer events, reverse-chronological
```

**Important:** This only credits the Realitio internal balance. The xDAI is NOT transferred yet.

## Phase 8: Withdraw Bonds (Answerer)

Transfer the claimed bonds from Realitio's internal balance to the caller:

```
1. Realitio.balanceOf(address)  [read-only]
   → Check the internal balance (credited by claimWinnings)

2. Realitio.withdraw()
   → Transfer the entire internal balance as native xDAI to the caller
   → Emits LogWithdraw event
```

**Prerequisite:** `claimWinnings()` must have been called (Phase 7). Without it, `balanceOf == 0`.

## Phase 9: Deposit DAI (LP)

The market-creator wraps xDAI to wxDAI for the next cycle of market creation:

```
wxDAI.deposit()   [payable]
  → Wrap native xDAI into wxDAI (ERC20)
  → wxDAI is the collateral used for creating new markets
```

## Market-Creator FSM mapping

| FSM Round | Lifecycle Phase | What it does |
|-----------|----------------|---|
| `SyncMarketsRound` | — | Query subgraph for existing markets |
| `RemoveFundingRound` | Phase 4 | removeFunding + mergePositions + withdraw |
| `RedeemWinningsRound` | Phase 5 + 6 | resolve (if needed) + redeemPositions |
| `DepositDaiRound` | Phase 9 | wxDAI.deposit() |
| `GetPendingQuestionsRound` | — | Query subgraph for unanswered questions |
| `MechInteract` | — | Get AI answers from Mech |
| `AnswerQuestionsRound` | Phase 3 | wxDAI.withdraw() + submitAnswer |
| `RedeemBondRound` | Phase 8 | Realitio.withdraw() (claimWinnings not yet implemented) |
| `CollectProposedMarketsRound` | — | Fetch market proposals |
| `ApproveMarketsRound` | — | Validate via LLM |
| `PrepareTransactionRound` | Phase 1 | approve + askQuestion + prepareCondition + create2FPMM |

**Known gap:** `claimWinnings` (Phase 7) is not yet implemented. The `RedeemBondRound` only calls `withdraw()`, which depends on others (traders) having called `claimWinnings`. For uncontested answers, bonds remain locked until claimed. See plan: `.claude/plans/claim_winnings.md`.

## Visual Summary

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
    └───────┬───────┘      │       └──────┬──────┘
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
