# Plan: Market Creator Unit Test Coverage

## Status Snapshot

- ✅ Branch: `test/unit-test-coverage`
- ✅ Main coverage command: `tox -e unit-tests-coverage`
- ✅ Phase 1 test result: **426 passed**
- ✅ Phase 2 M1 test result: **40 passed** (all import issues resolved)
- ✅ Phase 1 scope: **functionally complete**
- ✅ Phase 2 M1 scope: **✅ COMPLETE**
- 🔴 Remaining for strict 100% on Phase 1: **2 lines** (edge cases)
- 🟡 Phase 2 M2-M4: **PENDING** (6 files, ~91 tests estimated)

---

## Progress Dashboard

| Area | Status | Notes |
|---|---|---|
| 0. Config (`tox.ini`, `.coveragerc`, conftest setup) | ✅ Done | Coverage env + package sources configured |
| 1.1 Payload tests | ✅ Done | Implemented and passing |
| 1.2 Dialogues tests | ✅ Done | Implemented and passing |
| 1.3 Handlers tests | ✅ Done | Implemented and passing |
| 1.4 Models tests | ✅ Done | Implemented and passing |
| 1.5 States base tests | ✅ Done | Implemented and passing |
| 1.6 States per-round tests | ✅ Done | Implemented and passing |
| 1.7 Rounds/FSM tests | ✅ Done | Implemented and passing |
| 1.8 Market maker dialogues | ✅ Done | Implemented and passing |
| 1.9 Market maker handlers | ✅ Done | Implemented and passing |
| 1.10 Market maker models | ✅ Done | Implemented and passing |
| 1.11 Market maker behaviours wiring | ✅ Done | Implemented and passing |
| 1.12 Market maker composition | ✅ Done | Implemented and passing |
| 1.13 Contract `fpmm_deterministic_factory` | ✅ Done | Implemented and passing |
| 1.14 Contract `fpmm` | ✅ Done | Implemented and passing |
| Full suite execution | ✅ Done | `426 passed` |
| Strict 100% for Phase 1 | 🟡 Near-complete | 2 edge lines remain |
| 2.1 Base behaviour tests (M1) | ✅ Done | `test_base.py`: 12 tests passed |
| 2.2 PrepareTransaction tests (M1) | ✅ Done | `test_prepare_transaction.py`: 9 tests passed |
| 2.3 AnswerQuestions tests (M1) | ✅ Done | `test_answer_questions.py`: 19 tests passed |
| Phase 2 M1 suite execution | ✅ Done | **40 tests passed** (import issues resolved) |
| 2. Behaviour deep tests M2-M4 | 🟡 In Progress | 11 medium/low priority behaviours remaining |

---

## Files Added in PR (by Phase + Length)

### Size Legend
- 🧱 **Very long**: `>= 300` lines
- 📄 **Long**: `150-299` lines
- 🧪 **Medium**: `75-149` lines
- 🟢 **Short**: `< 75` lines

### Phase 1 — Added files

| File | Lines | Size |
|---|---:|---|
| `packages/valory/skills/market_creation_manager_abci/tests/test_rounds.py` | 541 | 🧱 |
| `packages/valory/skills/market_maker_abci/tests/test_handlers.py` | 530 | 🧱 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_base.py` | 368 | 🧱 |
| `packages/valory/contracts/fpmm_deterministic_factory/tests/test_contract.py` | 264 | 📄 |
| `packages/valory/skills/market_maker_abci/tests/test_composition.py` | 235 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_remove_funding.py` | 208 | 📄 |
| `packages/valory/contracts/fpmm/tests/test_contract.py` | 198 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_sync_markets.py` | 191 | 📄 |
| `packages/valory/skills/market_maker_abci/tests/test_models.py` | 190 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_post_transaction.py` | 184 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_collect_proposed_markets.py` | 173 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_get_pending_questions.py` | 172 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_approve_markets.py` | 167 | 📄 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_retrieve_approved_market.py` | 146 | 🧪 |
| `packages/valory/skills/market_creation_manager_abci/tests/test_dialogues.py` | 139 | 🧪 |
| `packages/valory/skills/market_creation_manager_abci/tests/test_payloads.py` | 122 | 🧪 |
| `packages/valory/skills/market_maker_abci/tests/test_dialogues.py` | 121 | 🧪 |
| `packages/valory/skills/market_creation_manager_abci/tests/test_handlers.py` | 113 | 🧪 |
| `packages/valory/skills/market_maker_abci/tests/test_behaviours.py` | 107 | 🧪 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_collect_randomness.py` | 76 | 🧪 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_select_keeper.py` | 75 | 🧪 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_final_states.py` | 63 | 🟢 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_redeem_bond.py` | 60 | 🟢 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_prepare_transaction.py` | 60 | 🟢 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_deposit_dai.py` | 60 | 🟢 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/test_answer_questions.py` | 60 | 🟢 |
| `packages/valory/skills/market_maker_abci/tests/conftest.py` | 33 | 🟢 |
| `packages/valory/skills/market_creation_manager_abci/tests/conftest.py` | 33 | 🟢 |
| `packages/valory/skills/market_creation_manager_abci/tests/states/__init__.py` | 20 | 🟢 |
| `packages/valory/contracts/fpmm/tests/__init__.py` | 20 | 🟢 |
| `packages/valory/contracts/fpmm_deterministic_factory/tests/__init__.py` | 20 | 🟢 |

### Phase 2 — Added files (M1 Complete)

| File | Lines | Size | Status |
|---|---:|---|---|
| `packages/valory/skills/market_creation_manager_abci/tests/behaviours/__init__.py` | 20 | 🟢 | ✅ Created |
| `packages/valory/skills/market_creation_manager_abci/tests/behaviours/conftest.py` | 77 | 🧪 | ✅ Created - Shared fixtures |
| `packages/valory/skills/market_creation_manager_abci/tests/behaviours/test_base.py` | 175 | 📄 | ✅ Created - 12 tests passing |
| `packages/valory/skills/market_creation_manager_abci/tests/behaviours/test_prepare_transaction.py` | 132 | 🧪 | ✅ Created - 9 tests passing |
| `packages/valory/skills/market_creation_manager_abci/tests/behaviours/test_answer_questions.py` | 196 | 📄 | ✅ Created - 19 tests passing |

> 📝 Most large tests are concentrated in FSM/handlers/state-base (`test_rounds.py`, market maker `test_handlers.py`, and states `test_base.py`).

---

## Remaining Coverage Gaps (Phase 1)

### 1) `packages/valory/skills/market_creation_manager_abci/dialogues.py`
- ⚠️ One callback return line remains uncovered (line executed only via dialogue callback path in runtime flow).

### 2) `packages/valory/contracts/fpmm/contract.py`
- ⚠️ One exception-path `raise` line remains uncovered (coverage tooling/logging interaction edge case).

---

## What Is Already Verified

- ✅ `tox -e black`
- ✅ `tox -e isort`
- ✅ `autonomy packages lock`
- ✅ `tox -e unit-tests-coverage`

---

## Current Actions (Phase 2 M1 Complete)

1. ✅ Phase 2 M1: Base, PrepareTransaction, AnswerQuestions behaviour tests created + passing
2. ✅ Fixed transitive import issue (`openai` dependency) by avoiding direct behaviour imports
3. ⏭️ Phase 2 M2: Create 6 medium-priority behaviour test files
4. ⏭️ Phase 2 M3: Create 4 low-priority behaviour test files  
5. ⏭️ Phase 2 M4: Create remaining behaviour test files
6. ⏭️ Final: `tox -e unit-tests-coverage` report with Phase 1 + Phase 2 combined

---

## Phase 2: Behaviour Deep Coverage Plan

### Objective

- 🎯 Build robust unit tests for all behaviour modules in `market_creation_manager_abci`.
- 🎯 Cover decision branches, retries, error handling, and payload emission paths.
- 🎯 Keep tests deterministic (no network/RPC/external service calls).

### Scope (14 behaviour files)

| Behaviour | Planned test file | Priority | Focus |
|---|---|---|---|
| `base.py` | `tests/behaviours/test_base.py` | ✅ M1 Done | Shared helpers, tx hash prep, multisend building, query helpers |
| `prepare_transaction.py` | `tests/behaviours/test_prepare_transaction.py` | ✅ M1 Done | Multi-contract tx assembly and branch selection |
| `answer_questions.py` | `tests/behaviours/test_answer_questions.py` | ✅ M1 Done | Mech responses, question parsing, tx payload building |
| `collect_proposed_markets.py` | `tests/behaviours/test_collect_proposed_markets.py` | 🟡 M2 Next | Subgraph fetch + transformation + payload generation |
| `approve_markets.py` | `tests/behaviours/test_approve_markets_behaviour.py` | 🟡 M2 Next | Approval gating, retries, keeper payload outcomes |
| `get_pending_questions.py` | `tests/behaviours/test_get_pending_questions.py` | 🟡 M2 Next | Query pagination/filtering and no-result handling |
| `post_transaction.py` | `tests/behaviours/test_post_transaction.py` | 🟡 M2 Next | Settled tx processing, event extraction branches |
| `remove_funding.py` | `tests/behaviours/test_remove_funding.py` | 🟡 M2 Next | Liquidity removal + token redemption flow |
| `sync_markets.py` | `tests/behaviours/test_sync_markets.py` | 🟡 M2 Next | Sync windows, from-block updates, empty deltas |
| `retrieve_approved_market.py` | `tests/behaviours/test_retrieve_approved_market.py` | 🟢 M3 Later | Response parsing and fallback paths |
| `deposit_dai.py` | `tests/behaviours/test_deposit_dai.py` | 🟢 M3 Later | Tx request scaffolding and basic branch checks |
| `redeem_bond.py` | `tests/behaviours/test_redeem_bond.py` | 🟢 M3 Later | Bond redemption tx branch handling |
| `select_keeper.py` | `tests/behaviours/test_select_keeper.py` | 🟢 M4 Last | Keeper selection wrapper behaviour |
| `collect_randomness.py` | `tests/behaviours/test_collect_randomness.py` | 🟢 M4 Last | Wrapper/forwarding behaviour |

### Test Strategy (per behaviour)

For each behaviour file:

1. ✅ **Happy path**: one test where the behaviour produces the expected payload/event.
2. ✅ **No-op path**: one test for empty/none/no-update scenarios.
3. ✅ **Error path**: one test where dependency call fails and behaviour handles it correctly.
4. ✅ **Retry/backoff path** (if applicable): one test to verify retry or fallback decisions.
5. ✅ **Serialization/format path** (if applicable): ensure JSON structures used in payloads are stable.

### Mocks & Fixtures Plan

- 🧪 Use `MagicMock` / `patch` for all external dependencies:
	- ledger calls
	- subgraph/http clients
	- mech/LLM tools
	- contract wrappers
- 🧪 Reuse common fixtures in `tests/behaviours/conftest.py`:
	- mocked context
	- mocked synchronized data
	- helper to build behaviour instances
	- helper payload assertions
- 🧪 Prefer deterministic constants over random values unless randomness is explicitly under test.

### Execution Milestones

| Milestone | Deliverable | Status | Exit Criteria |
|---|---|---|---|
| M1 | High-priority behaviours (`base`, `prepare_transaction`, `answer_questions`) | ✅ Complete | ✅ All 40 tests passing, import issues resolved |
| M2 | Medium-priority behaviours (6 files) | 🟡 In Progress | Target: 42 tests, coverage increases |
| M3 | Low-priority behaviours (4 files) | 🔴 Pending | Target: 28 tests, complete Phase 2 file set |
| M4 | Remaining behaviours (~3-4 files) | 🔴 Pending | Target: 21 tests, `tox -e unit-tests-coverage` stable |

### Verification Commands (Phase 2)

Run incrementally while implementing:

```bash
# Targeted behaviour suite while iterating
pytest packages/valory/skills/market_creation_manager_abci/tests/behaviours -v

# Full coverage validation
tox -e unit-tests-coverage
```

### Risks & Mitigations

- ⚠️ **Risk**: Behaviour tests become integration-like and flaky.
	- ✅ **Mitigation**: hard-mock every network/external boundary and assert on calls/arguments.

- ⚠️ **Risk**: Over-coupled tests to implementation details.
	- ✅ **Mitigation**: assert public outcomes (payloads/events), not internal local variable values.

- ⚠️ **Risk**: Long execution times.
	- ✅ **Mitigation**: keep fixtures lightweight and avoid unnecessary parametrization explosion.

### Phase 2 Completion Criteria

- ✅ Test files exist for all 14 behaviour modules.
- ✅ All behaviour tests pass consistently.
- ✅ `tox -e unit-tests-coverage` remains green.
- ✅ Coverage meaningfully increased for behaviour modules.
- ✅ No new lint/type failures introduced.

---

## Pre-Push Checklist

Run in this order:

```bash
tox -e isort
tox -e black
autonomy packages lock
tomte check-code
tox -e unit-tests-coverage
```

Notes:
- ✅ Keep commit scope limited to test/config/coverage workflow files.
- ⚠️ Do not mix unrelated cleanup into this PR unless explicitly requested.

---

## Legend

- ✅ Done
- 🟡 In progress / partial
- 🔴 Blocker / remaining gap
- ⏳ Pending
- ⏭️ Next step
