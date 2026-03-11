# Omen Prediction Market Lifecycle

This document covers the full lifecycle of an Omen prediction market on Gnosis Chain, from both the **Liquidity Provider** (market-creator) and **Trader** perspectives, with the specific contract methods called at each step.

## Contracts involved

| Contract | Gnosis Address | Role |
|----------|---------------|------|
| **ConditionalTokens** | `0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce` | ERC-1155 token system for outcome positions. Manages conditions, position splitting/merging, and redemption. |
| **Realitio** (Reality.eth v3) | configured per deployment | Oracle for question resolution. Holds bonds, accepts answers, and pays out winners. |
| **RealitioProxy** | configured per deployment | Bridge between Realitio answers and ConditionalTokens conditions. Calls `reportPayouts` on CT. |
| **FPMMDeterministicFactory** | configured per deployment | Factory that deploys FPMM market contracts with deterministic addresses (CREATE2). |
| **FPMM** (FixedProductMarketMaker) | per-market address | AMM pool for trading outcome tokens. Implements constant-product formula. |
| **wxDAI** (ERC20) | `0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d` | Wrapped xDAI, used as collateral for all markets on Gnosis chain. |

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

Each trade shifts the pool's token ratio, changing the implied probability (price) of each outcome. This imbalances the pool — one side accumulates more tokens than the other.

## Phase 3: Question Resolution (Oracle)

After the market's `openingTimestamp` passes, anyone can answer the question:

```
1. Realitio.submitAnswer(question_id, answer, max_previous)
   → Submit an answer with a bond (value sent with tx).
   → answer: 0x00...00 = Yes, 0x00...01 = No, 0xff...ff = Invalid
   → Each subsequent answer must double the bond.
   → After timeout with no new answer, the last answer is finalized.
```

The market-creator's `AnswerQuestionsBehaviour` does this using Mech (AI oracle) responses.

## Phase 4: Remove Liquidity (LP)

The market-creator removes its LP position through a multisend:

```
1. FPMM.removeFunding(sharesToBurn)
   → Burn LP tokens, receive proportional outcome tokens for each side.
   → Due to trading activity, the pool is imbalanced — you get MORE tokens
     on the side traders bought (the "heavier" side) and FEWER on the other.

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

Before anyone can redeem positions, the Realitio answer must be reported to ConditionalTokens:

```
RealitioProxy.resolve(question_id, template_id, question, num_outcomes)
  → Reads the finalized answer from Realitio
  → Calls ConditionalTokens.reportPayouts(questionId, payouts)
  → Sets payoutNumerators and payoutDenominator for the condition
  → Example: Yes wins → numerators=[1,0], denominator=1
```

This is typically called by traders during their own redemption flow. The market-creator v1 assumes someone else has already done this.

## Phase 6: Redeem Bond (LP)

The market-creator claims accumulated bonds from answering questions:

```
1. Realitio.balanceOf(safeAddress)  [read-only]
   → Check if there's a withdrawable balance (from winning answer bonds)

2. Realitio.withdraw()
   → Withdraw accumulated bonds to the safe
   → Only called if balance > 0.1 DAI
```

## Phase 7: Redeem Winnings (LP)

The market-creator redeems residual conditional tokens for collateral:

```
ConditionalTokens.redeemPositions(collateralToken, parentCollectionId, conditionId, indexSets)
  → For each outcome: payout = balance[i] * payoutNumerator[i] / payoutDenominator
  → Burns the conditional tokens, transfers collateral (wxDAI) to the caller
  → If the safe's tokens are on the WINNING side → receives collateral
  → If the safe's tokens are on the LOSING side → receives nothing (0 * anything = 0)
  → Safe to call with losing tokens — doesn't revert, just returns 0
  → indexSets = [1, 2] for binary markets (one bit per outcome)
```

## Phase 8: Trader Redemption (Trader)

Traders use a 3-step multisend to claim everything:

```
1. RealitioProxy.resolve(...)        [optional — only if condition not yet resolved]
   → See Phase 5 above

2. Realitio.claimWinnings(question_id, history_hashes[], addrs[], bonds[], answers[])
   → Claim oracle bonds from the question's answer history
   → Parameters reconstructed from LogNewAnswer events
   → Only the final (correct) answerer wins the accumulated bonds

3. ConditionalTokens.redeemPositions(collateralToken, 0x00...00, conditionId, indexSets)
   → Same as LP redemption above — exchange winning outcome tokens for collateral
```

## Phase 9: Deposit DAI (LP)

The market-creator wraps xDAI to wxDAI for the next cycle of market creation:

```
wxDAI.deposit()   [payable]
  → Wrap native xDAI into wxDAI (ERC20)
  → wxDAI is the collateral used for creating new markets
```

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
            │              │       ┌──────┴──────┐
            │              │       │   resolve   │
            │              │       │ claimWinngs │
            │              │       │ redeemPos.  │
            │              │       └──────┬──────┘
    ┌───────┴───────┐      │              │
    │ redeemBond    │      │              │
    │ redeemWinngs  │◄─────┘              │
    │ depositDai    │                     │
    └───────────────┘                     │
```
