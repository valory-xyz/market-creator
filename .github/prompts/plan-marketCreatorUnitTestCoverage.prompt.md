# Plan: 100% Unit Test Coverage for market-creator

**TL;DR**: Create comprehensive unit tests for the 4 dev packages in market-creator, following the trader repo's testing conventions. Phase 1 covers states/rounds, payloads, handlers, dialogues, models, contracts, and the FSM composition. Phase 2 (follow-up) covers the 14 behaviour files. `propose_questions.py` is excluded from coverage. Tests go inside each package's `tests/` folder. A new `[testenv:unit-tests-coverage]` section is added to `tox.ini`.

---

## Progress Summary

| Phase | Item | Status |
|-------|------|--------|
| 0 | Configuration (`.coveragerc`, `tox.ini`, `conftest.py` x2, `__init__.py` files) | **DONE** |
| 1.1 | `market_creation_manager_abci` — Payloads (`test_payloads.py`) | **DONE** (48 tests verified passing) |
| 1.2 | `market_creation_manager_abci` — Dialogues (`test_dialogues.py`) | **DONE** (48 tests verified passing) |
| 1.3 | `market_creation_manager_abci` — Handlers (`test_handlers.py`) | **DONE** (48 tests verified passing) |
| 1.4 | `market_creation_manager_abci` — Models (`test_models.py`) | **PENDING** — not yet created |
| 1.5 | `market_creation_manager_abci` — States base (`states/test_base.py`) | **DONE** (created, not yet run) |
| 1.6 | `market_creation_manager_abci` — States per-round (13 files) | **DONE** (created, not yet run) |
| 1.7 | `market_creation_manager_abci` — Rounds FSM (`test_rounds.py`) | **DONE** (created, not yet run) |
| 1.8 | `market_maker_abci` — Dialogues (`test_dialogues.py`) | **DONE** (48 tests verified passing) |
| 1.9 | `market_maker_abci` — Handlers (`test_handlers.py`) | **DONE** (created, not yet run) |
| 1.10 | `market_maker_abci` — Models (`test_models.py`) | **DONE** (created, not yet run) |
| 1.11 | `market_maker_abci` — Behaviours (`test_behaviours.py`) | **DONE** (created, not yet run) |
| 1.12 | `market_maker_abci` — Composition (`test_composition.py`) | **DONE** (created, not yet run) |
| 1.13 | Contract `fpmm_deterministic_factory` tests | **DONE** (created, not yet run) |
| 1.14 | Contract `fpmm` tests | **DONE** (created, not yet run) |
| — | Run all tests + fix failures | **PENDING** |
| — | Full coverage report (`tox -e unit-tests-coverage`) | **PENDING** |
| 2 | Behaviours (14 behaviour test files) | **PENDING** — follow-up phase |

**Branch**: `test/unit-test-coverage` — contains all Phase 1 files created so far.

**Next steps**:
1. Run all tests (`pytest` across all 4 package test dirs) and fix any failures
2. Create `market_creation_manager_abci/tests/test_models.py` (the one Phase 1 file not yet created)
3. Run `tox -e unit-tests-coverage` for full coverage report and fill any gaps
4. Phase 2: behaviour test files (14 files)

---

## 0. Configuration

1. Add a `[testenv:unit-tests-coverage]` section to `tox.ini` with the command from the request. Fix the `--cov` target to point at the 4 dev packages (not `operate`):
   ```
   --cov=packages/valory/contracts/fpmm_deterministic_factory
   --cov=packages/valory/contracts/fpmm
   --cov=packages/valory/skills/market_creation_manager_abci
   --cov=packages/valory/skills/market_maker_abci
   ```
   Add `--cov-config=.coveragerc` and deps matching `[deps-packages]` plus `httpx`, `pytest-recording`, `pytest-cov`.

2. Create a `.coveragerc` at the repo root with:
   - `[run]` source pointing to the 4 dev packages
   - `[report]` omit for `propose_questions.py`, `__init__.py` files, and `*/tests/*`
   - `exclude_lines` for `pragma: no cover`, `raise NotImplementedError`, `if TYPE_CHECKING`

---

## Phase 1: States, Rounds, Payloads, Handlers, Dialogues, Models, Contracts

### 1. `market_creation_manager_abci` — Payloads
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/test_payloads.py`

- Parametrize over all 9 payload classes (`CollectRandomnessPayload`, `SelectKeeperPayload`, `RetrieveApprovedMarketPayload`, `SyncMarketsPayload`, `RemoveFundingPayload`, `PostTxPayload`, `CollectProposedMarketsPayload`, `ApproveMarketsPayload`, `GetPendingQuestionsPayload`, `MultisigTxPayload`) with their respective kwargs
- For each: construct, verify attributes, verify `.data`, verify `from_json(payload.json) == payload`
- Pattern from trader: `@pytest.mark.parametrize("payload_class, payload_kwargs", [...])`

### 2. `market_creation_manager_abci` — Dialogues
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/test_dialogues.py`

- Import test: verify `import packages.valory.skills.market_creation_manager_abci.dialogues` works
- Test `LlmDialogues.__init__` with a `MagicMock` kwargs and verify it instantiates, and that `role_from_first_message` returns `LlmDialogue.Role.SKILL`

### 3. `market_creation_manager_abci` — Handlers
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/test_handlers.py`

- Parametrized `isinstance` test for all 7 handler aliases (`ABCIHandler`, `HttpHandler`, `SigningHandler`, `LedgerApiHandler`, `ContractApiHandler`, `TendermintHandler`, `IpfsHandler`) against their base classes
- Test `LlmHandler`: instantiate, verify `SUPPORTED_PROTOCOL == LlmMessage.protocol_id`, verify `allowed_response_performatives` contains the correct performatives

### 4. `market_creation_manager_abci` — Models
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/test_models.py`

- Test `SharedState.__init__`: verify `abci_app_cls == MarketCreationManagerAbciApp`, verify `questions_requested_mech` and `questions_responded` are initialized
- Test `MarketCreationManagerParams.__init__`: construct with all required kwargs, assert each attribute is set correctly. Use `MagicMock` for the skill context
- Test `RandomnessApi`, `OmenSubgraph` as import/isinstance checks
- Test `Requests`, `BenchmarkTool` aliases

### 5. `market_creation_manager_abci` — States (base)
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/states/__init__.py` (empty)
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/states/test_base.py`

- Test `Event` enum: verify all 18 enum members exist and have correct values
- Test `SynchronizedData` properties (18 properties): use `MagicMock` db, set `get_strict`/`get` return values, assert each property returns the correct type/value. Key properties: `gathered_data`, `proposed_markets_count`, `approved_markets_count`, `mech_requests` (JSON deserialization), `mech_responses` (JSON deserialization), `markets_to_remove_liquidity`, `market_from_block`, `settled_tx_hash`, `tx_submitter`, `participant_to_tx_prep`, `is_approved_question_data_set`
- Test `TxPreparationRound` class attributes: `payload_class`, `synchronized_data_class`, `done_event`, `none_event`, `no_majority_event`, `selection_key`, `collection_key`

### 6. `market_creation_manager_abci` — States (per-round)
**Files to create**: One test file per state module with custom `end_block` logic:

- `tests/states/test_approve_markets.py`: Test `ApproveMarketsRound.end_block` — 3 paths: `super().end_block()` returns None, ERROR_PAYLOAD → `Event.ERROR`, MAX_RETRIES_PAYLOAD → `Event.MAX_RETRIES_REACHED`, happy path → `Event.DONE`
- `tests/states/test_collect_proposed_markets.py`: Test 5 paths: None, ERROR_PAYLOAD, MAX_RETRIES_PAYLOAD, MAX_APPROVED_MARKETS_REACHED_PAYLOAD, SKIP_MARKET_APPROVAL_PAYLOAD, happy path
- `tests/states/test_collect_randomness.py`: Verify class attributes match expected values
- `tests/states/test_deposit_dai.py`: Verify it's a subclass of `TxPreparationRound`
- `tests/states/test_get_pending_questions.py`: Test 3 custom paths in `end_block`: ERROR_PAYLOAD → `Event.ERROR`, NO_TX_PAYLOAD → `Event.NO_TX`, happy path with `tx_submitter` update
- `tests/states/test_post_transaction.py`: Test 7 payload-to-event mappings + no_majority path
- `tests/states/test_prepare_transaction.py`: Verify subclass of `TxPreparationRound`
- `tests/states/test_redeem_bond.py`: Verify subclass of `TxPreparationRound`
- `tests/states/test_remove_funding.py`: Test 4 paths: ERROR_PAYLOAD, NO_UPDATE_PAYLOAD → `Event.NO_TX`, happy path with JSON parsing and `markets_to_remove_liquidity` update, no_majority
- `tests/states/test_retrieve_approved_market.py`: Test 4 paths: keeper_payload None, ERROR_PAYLOAD, NO_MARKETS_RETRIEVED_PAYLOAD, happy path with JSON parse + `approved_question_data` update
- `tests/states/test_select_keeper.py`: Verify class attributes
- `tests/states/test_sync_markets.py`: Test 4 paths: ERROR_PAYLOAD, NO_UPDATE_PAYLOAD, happy path with JSON markets/from_block update, no_majority
- `tests/states/test_answer_questions.py`: Verify subclass of `TxPreparationRound`
- `tests/states/test_final_states.py`: Verify all 8 classes are subclasses of `DegenerateRound`

### 7. `market_creation_manager_abci` — Rounds (FSM transitions)
**File to create**: `packages/valory/skills/market_creation_manager_abci/tests/test_rounds.py`

- Instantiate `MarketCreationManagerAbciApp` with mocked `synchronized_data`, `logger`, `context`
- Verify `initial_round_cls == CollectRandomnessRound`
- Verify `initial_states` contains all 6 expected states
- Verify `final_states` contains all 8 `Finished*Round` classes
- Verify `transition_function` mappings for each round: parametrize `(source_round, event, target_round)` over all entries in the transition function dict
- Verify `cross_period_persisted_keys` contains the 5 expected keys
- Verify `db_pre_conditions` and `db_post_conditions` dicts

### 8. `market_maker_abci` — Dialogues
**File to create**: `packages/valory/skills/market_maker_abci/tests/test_dialogues.py`

- Import test: verify `import packages.valory.skills.market_maker_abci.dialogues` works
- Verify all aliases point to correct base classes

### 9. `market_maker_abci` — Handlers
**File to create**: `packages/valory/skills/market_maker_abci/tests/test_handlers.py`

- Parametrized `isinstance` test for all handler aliases (`MarketCreatorABCIRoundHandler`, `SigningHandler`, `LedgerApiHandler`, `ContractApiHandler`, `TendermintHandler`, `IpfsHandler`, `LlmHandler`)
- Test `HttpHandler` extensively (310 lines, the largest handler):
  - `test_setup`: verify `handler_url_regex`, routes, `json_content_header`
  - `test__get_handler` with matching/non-matching URLs and methods
  - `test_handle` dispatching: request from http_server → routes, non-request → `super().handle()`, invalid dialogue → log
  - `test__handle_bad_request`: returns 400 with empty body
  - `test__send_ok_response`: returns 200 with JSON body
  - `test__handle_get_health`: mock `round_sequence` with/without `_last_round_transition_timestamp`, with/without `_abci_app`, verify JSON response structure
  - Test `HttpCode` and `HttpMethod` enum values

### 10. `market_maker_abci` — Models
**File to create**: `packages/valory/skills/market_maker_abci/tests/test_models.py`

- Test `SharedState.abci_app_cls == MarketCreatorAbciApp`
- Test `SharedState.setup()`: mock `context.params` with all required attributes, verify all `event_to_timeout` entries are set correctly
- Test `Params` is a subclass of `MarketCreationManagerParams`, `MechInteractParams`, `TerminationParams`
- Verify `MARGIN` and `MULTIPLIER` constants

### 11. `market_maker_abci` — Behaviours
**File to create**: `packages/valory/skills/market_maker_abci/tests/test_behaviours.py`

- Verify `MarketCreatorRoundBehaviour.initial_behaviour_cls == RegistrationStartupBehaviour`
- Verify `MarketCreatorRoundBehaviour.abci_app_cls == MarketCreatorAbciApp`
- Verify `behaviours` set contains all expected behaviour classes
- Verify `background_behaviours_cls == {BackgroundBehaviour}`

### 12. `market_maker_abci` — Composition
**File to create**: `packages/valory/skills/market_maker_abci/tests/test_composition.py`

- Verify `MarketCreatorAbciApp` is a valid chained AbciApp
- Verify `abci_app_transition_mapping` has all expected entries (test each key-value pair)
- Verify `termination_config` attributes: `round_cls == BackgroundRound`, `start_event == Event.TERMINATE`, `abci_app == TerminationAbciApp`

### 13. Contract: `fpmm_deterministic_factory`
**Files to create**:
- `packages/valory/contracts/fpmm_deterministic_factory/tests/__init__.py` (empty)
- `packages/valory/contracts/fpmm_deterministic_factory/tests/test_contract.py`

Tests:
- `test_get_logs`: mock `eth`, `contract_instance`, verify `filter_params` are constructed correctly and `eth.get_logs` is called
- `test_get_raw_transaction_raises`: call `FPMMDeterministicFactory.get_raw_transaction` → assert `NotImplementedError`
- `test_get_raw_message_raises`: same for `get_raw_message`
- `test_get_state_raises`: same for `get_state`
- `test_get_create_fpmm_tx`: mock `ledger_api` with `api.to_checksum_address`, `api.to_wei`, `build_transaction`; verify correct args passed
- `test_get_create_fpmm_tx_data`: mock `ledger_api` + `get_instance` + `encode_abi`; verify returned dict has `data` (bytes) and `value` keys
- `test_get_market_creation_events`: mock `ledger_api.api.eth`, `get_instance`, `get_logs`, `get_event_data`; verify returned `data` list structure
- `test_parse_market_creation_event`: mock `ledger_api.api.eth.get_transaction_receipt`, `process_receipt`; verify returned dict structure

### 14. Contract: `fpmm`
**Files to create**:
- `packages/valory/contracts/fpmm/tests/__init__.py` (empty)
- `packages/valory/contracts/fpmm/tests/test_contract.py`

Tests:
- `test_get_raw_transaction_raises`, `test_get_raw_message_raises`, `test_get_state_raises`: verify `NotImplementedError`
- `test_get_balance`: mock `get_instance` → `functions.balanceOf().call()`, verify returned dict
- `test_get_total_supply`: mock `get_instance` → `functions.totalSupply().call()`, verify returned dict
- `test_build_remove_funding_tx`: mock `get_instance` → `encode_abi`, verify returned dict has `data`
- `test_get_markets_with_funds`: mock `ledger_api.api.eth.contract`, `ledger_api.api.codec.encode/decode`, `ledger_api.api.eth.call`, `ledger_api.api.to_checksum_address`; test happy path and exception path

### 15. conftest.py files
**Files to create**:
- `packages/valory/skills/market_creation_manager_abci/tests/conftest.py`: Define `PACKAGE_DIR = Path(__file__).parent.parent`, Hypothesis CI profile
- `packages/valory/skills/market_maker_abci/tests/conftest.py`: Same pattern with `PACKAGE_DIR`

---

## Phase 2: Behaviours (Follow-up)

Create test files for each of the 14 behaviours in `packages/valory/skills/market_creation_manager_abci/tests/behaviours/`:

| Behaviour | Test file | Key test strategy |
|---|---|---|
| `base.py` | `test_base.py` | Test shared helpers: `_get_safe_tx_hash`, `_build_multisend_data`, subgraph query methods, LLM request methods. Use `FSMBehaviourBaseCase` |
| `answer_questions.py` | `test_answer_questions.py` | Mock mech responses, Realitio tx building |
| `approve_markets.py` | Extend existing `test_approve_markets_behaviour.py` | Add coverage for `async_act`, HTTP calls to approval server, time-gating logic |
| `collect_proposed_markets.py` | `test_collect_proposed_markets.py` | Mock subgraph query + LLM response |
| `collect_randomness.py` | `test_collect_randomness.py` | Thin wrapper — verify class attributes |
| `deposit_dai.py` | `test_deposit_dai.py` | Mock DAI wrapping tx |
| `get_pending_questions.py` | `test_get_pending_questions.py` | Mock Omen query, mech request creation |
| `post_transaction.py` | `test_post_transaction.py` | Mock settled_tx_hash parsing, market creation event processing |
| `prepare_transaction.py` | `test_prepare_transaction.py` | Mock Realitio + ConditionalTokens + FPMM multisend |
| `redeem_bond.py` | `test_redeem_bond.py` | Mock Realitio bond redemption tx |
| `remove_funding.py` | `test_remove_funding.py` | Mock FPMM remove funding + conditional token redemption |
| `retrieve_approved_market.py` | `test_retrieve_approved_market.py` | Mock HTTP fetch from approval server |
| `select_keeper.py` | `test_select_keeper.py` | Thin wrapper — verify class attributes |
| `sync_markets.py` | `test_sync_markets.py` | Mock subgraph market sync query |
| `round_behaviour.py` | `test_round_behaviour.py` | Verify `MarketCreationManagerRoundBehaviour` wiring |

---

## Verification

1. Run `tox -e unit-tests-coverage` to execute all tests
2. Check coverage report: target 100% (excluding `propose_questions.py`, `__init__.py`, `raise NotImplementedError` lines)
3. Verify no tests require network access or external APIs — all external calls must be mocked
4. Run `pytest tests/ -m "not integration" --co` to ensure all tests are discovered

## Decisions

- **`--cov` targets**: 4 dev packages explicitly (not `operate` or `packages`)
- **`propose_questions.py`**: Excluded from coverage (mech tool with heavy external deps)
- **Phasing**: Phase 1 = everything except behaviours; Phase 2 = behaviours
- **Test location**: Inside each package's `tests/` folder (not root `tests/`)
- **Pattern source**: Trader repo conventions (parametrized payloads, isinstance handlers, mocked-db SynchronizedData, FSM transition assertions)
