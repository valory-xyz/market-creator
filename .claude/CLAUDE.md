# CLAUDE.md — Market Creator

## Project Overview

Market Creator is an **autonomous service** built on the [Open Autonomy](https://stack.olas.network/open-autonomy/) framework. It creates and manages prediction markets on Gnosis Chain using the OLAS stack (AEA + ABCI consensus).

**Reference repo:** [valory-xyz/trader](https://github.com/valory-xyz/trader) (develop branch) — follow the same patterns for CI, tox, and package structure.

## What the Service Does

The service autonomously creates and manages prediction markets on Gnosis Chain. Each period (cycle) it:

1. **Syncs existing markets** (`SyncMarketsRound`) — scans on-chain events to track markets it has created
2. **Removes liquidity** (`RemoveFundingRound`) — withdraws liquidity from expired/resolved markets
3. **Deposits DAI** (`DepositDaiRound`) — wraps xDAI into wxDAI for market funding
4. **Gets pending questions** (`GetPendingQuestionsRound`) — queries Realitio for questions needing answers on markets it created
5. **Requests Mech** — delegates question evaluation to a Mech agent (AI oracle) via `mech_interact_abci`
6. **Answers questions** (`AnswerQuestionsRound`) — submits Mech responses as Realitio answers
7. **Redeems bonds** (`RedeemBondRound`) — claims bonds from answered questions
8. **Proposes new markets** (`CollectProposedMarketsRound`) — fetches market proposals from an external approval server
9. **Approves markets** (`ApproveMarketsRound`) — validates proposals via LLM/Mech
10. **Creates markets on-chain** (`RetrieveApprovedMarketRound` → `PrepareTransactionRound`) — builds multisend transactions to deploy FPMM contracts, add liquidity, and create Realitio questions

### Contracts

- **FPMM** (`fpmm/`): Fixed Product Market Maker — the prediction market AMM contract. Methods: `buy`, `sell`, `add_funding`, `remove_funding`, `merge_positions`, `split_position`
- **FPMM Deterministic Factory** (`fpmm_deterministic_factory/`): Deploys FPMM instances deterministically. Also handles Conditional Tokens condition creation and ERC20 approvals

### Skill architecture

- **`market_creation_manager_abci`**: The core FSM skill with all business logic. Contains 13 active rounds, 8 final states, and corresponding behaviours. The FSM specification is in `fsm_specification.yaml` and the transition graph is in `rounds.py`.
- **`market_maker_abci`**: The composed (chained) ABCI app defined in `composition.py`. It wires together:
  - `AgentRegistrationAbciApp` — agent startup and registration
  - `MarketCreationManagerAbciApp` — the core logic above
  - `TransactionSubmissionAbciApp` — on-chain transaction settlement (multisig safe)
  - `MechInteractAbciApp` — Mech agent request/response cycle
  - `ResetPauseAbciApp` — period reset between cycles
  - `TerminationAbciApp` — graceful shutdown (background app)

  The transition mapping in `composition.py` defines how final states of one sub-app connect to initial states of another. For example, `FinishedMarketCreationManagerRound` → `TransactionSettlementAbci` (to submit the prepared tx), and after settlement `PostTransactionRound` routes back to the appropriate next step based on which transaction type was settled.

## Repository Structure

```text
packages/valory/
├── contracts/
│   ├── fpmm/                            # Fixed Product Market Maker contract wrapper
│   ├── fpmm_deterministic_factory/      # Factory contract for deterministic FPMM creation
│   └── ... (third-party synced contracts)
├── skills/
│   ├── market_creation_manager_abci/    # Core skill: market lifecycle FSM
│   │   ├── behaviours/                  # Round behaviours (one per FSM state)
│   │   ├── states/                      # State definitions
│   │   ├── tests/                       # Unit tests (fully mocked)
│   │   ├── rounds.py                    # FSM round definitions
│   │   ├── payloads.py                  # Consensus payloads
│   │   ├── handlers.py                  # Protocol message handlers
│   │   ├── dialogues.py                 # Dialogue state machines
│   │   └── models.py                    # Skill parameters & models
│   ├── market_maker_abci/               # Composed ABCI app (wires sub-skills)
│   └── ... (third-party synced skills)
├── agents/                              # Agent configurations
└── services/                            # Service configurations
```

### What you own vs. what is synced

Package ownership is defined in `packages/packages.json`:

- **`dev`** section: project-specific packages (owned by this repo, committed to git). These may change over time. Currently:
  - `contract/valory/fpmm/0.1.0`
  - `contract/valory/fpmm_deterministic_factory/0.1.0`
  - `skill/valory/market_creation_manager_abci/0.1.0`
  - `skill/valory/market_maker_abci/0.1.0`
  - `agent/valory/market_maker/0.1.0`
  - `service/valory/market_maker/0.1.0`

- **`third_party`** section: dependencies synced from IPFS via `autonomy packages sync --all`. Do not modify these directly — they are not committed to git.

## Development Commands

### Prerequisites

- Python 3.10–3.14
- [Poetry](https://python-poetry.org/)
- [tox](https://tox.wiki/)
- [tomte](https://github.com/valory-xyz/tomte) (installed via tox deps)

### Setup

```bash
poetry install --no-root
```

### Syncing third-party packages

Before running tests, sync all AEA packages from IPFS:

```bash
autonomy init --reset --author ci --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"
autonomy packages sync --all
```

This is done automatically by tox test environments.

### Running tests

```bash
# Run all unit tests (Linux, Python 3.11)
tox -e py3.11-linux

# Convenience: run all unit tests in one pytest invocation with combined coverage
tox -e unit-tests

# Recreate tox virtualenv (clear cache)
tox -e py3.11-linux -r
```

Test environments follow the pattern `py{version}-{platform}` where platform is `linux`, `win`, or `darwin`.

### Formatting (auto-fix)

```bash
tox -e black && tox -e isort
```

### Locking packages

After modifying any dev package, update the package hashes:

```bash
autonomy packages lock
```

### Linting & static analysis

```bash
tox -e black-check    # Code formatting check
tox -e isort-check    # Import sorting check
tox -e flake8         # Linting
tox -e mypy           # Type checking
tox -e pylint         # Pylint
tox -e darglint       # Docstring linting
tox -e bandit         # Security linting
tox -e safety         # Dependency vulnerability check
tox -e liccheck       # License compliance check
```

### Package integrity

```bash
tox -e check-hash           # Verify package hashes
tox -e check-packages       # Validate package structure
tox -e check-abciapp-specs  # Validate FSM specifications
```

## Testing

### Coverage enforcement

All test environments enforce **100% statement + branch coverage** via `--cov-fail-under=100`. Coverage is configured in `.coveragerc`.

Coverage is measured per-package (4 separate pytest invocations in CI) with `--cov-append` to accumulate results:

1. `market_creation_manager_abci` (first, no append)
2. `market_maker_abci` (append)
3. `fpmm_deterministic_factory` (append)
4. `fpmm` (append)

### Test conventions

- All external boundaries are mocked (`MagicMock` / `patch`): ledger, subgraph, mech/LLM, contract wrappers
- Shared fixtures in `conftest.py` files
- No network/RPC calls — fully deterministic
- Tests assert on public outcomes (payloads, events), not implementation details
- Total: **568 tests**

### Adding new tests

Place tests in the `tests/` directory of each package. Follow existing patterns in `conftest.py` for mocked context, synchronized data, and behaviour builders.

## CI

CI workflow: `.github/workflows/common_checks.yml`

- Cross-platform matrix: Ubuntu, macOS, Windows
- Python versions: 3.10–3.14
- Uses `tomte[tox]==0.6.2` for test orchestration

## Key Gotchas

### `packages/valory/__init__.py` must exist

This file is required for Python to resolve `packages.valory.*` imports from the local directory rather than site-packages. Without it, Windows CI fails with `ModuleNotFoundError` because Python falls back to namespace package resolution from installed wheels.

### `PYTHONPATH` uses `{env:PWD:%CD%}`

The tox config sets `PYTHONPATH={env:PWD:%CD%}` for cross-platform compatibility (`PWD` on Unix, `%CD%` on Windows). This is the standard pattern from the trader repo — do not change it to `{toxinidir}`.

### Third-party packages are not committed

Packages synced via `autonomy packages sync --all` are fetched from IPFS at test time. They appear in `packages/` but are in `.gitignore`. Do not commit them.

### `propose_questions.py` is excluded from coverage

This file is omitted in `.coveragerc` because it contains Mech tool logic that runs inside the Mech agent, not inside the market-creator service.

### liccheck and setuptools

`setuptools` is added to `[Authorized Packages]` in `tox.ini` because its license metadata (`UNKNOWN`) is not auto-detected by liccheck.

### tox cache

If you get stale dependency errors, clear tox cache: `rm -rf .tox` or use `tox -e <env> -r`.

## Claude Skills

- **[audit-fsm](https://github.com/valory-xyz/open-autonomy/tree/main/claude-skills/audit-fsm)**: Claude skill for auditing FSM specifications in Open Autonomy services. Use it to validate FSM transition graphs, detect unreachable states, and check consistency between `rounds.py` and `fsm_specification.yaml`.

## FSM Change Discipline

FSM definitions are tightly coupled across multiple files. When modifying events, rounds, or transitions, **all** of the following must stay in sync:

1. **`states/base.py`** — `Event` enum members
2. **`rounds.py`** — `transition_function` entries and the class docstring (transition table)
3. **`fsm_specification.yaml`** — `alphabet_in` and `transition_func` entries
4. **Test files** — parametrized transition test cases (e.g., `TestRetrieveApprovedMarketTransitions`)

After any FSM change, run:

```bash
# Validate FSM specs match rounds.py (both skills)
autonomy analyse fsm-specs --package packages/valory/skills/market_creation_manager_abci
autonomy analyse fsm-specs --package packages/valory/skills/market_maker_abci

# If the yaml is out of date, regenerate it:
autonomy analyse fsm-specs --update --package packages/valory/skills/market_creation_manager_abci

# Validate docstrings and handlers
autonomy analyse docstrings
autonomy analyse handlers
```

### Common FSM pitfalls

- **Unused events**: Every event in the `Event` enum must appear in at least one round's `transition_function`. The FSM spec validator will reject unreferenced events.
- **Composition completeness**: In `market_maker_abci/composition.py`, the `abci_app_transition_mapping` must map **every** final state of each sub-app. Missing mappings cause runtime errors. When third-party skills add new final states (e.g., `MechInteractAbciApp` adding `FinishedMarketplaceLegacyDetectedRound`), the composition must be updated.
- **`OnlyKeeperSendsRound` overrides**: Rounds extending `OnlyKeeperSendsRound` (like `RetrieveApprovedMarketRound`) have `done_event`, `fail_event`, `payload_key`, and `payload_attribute`. If `end_block()` is fully overridden, placeholder values for `payload_key` are harmless but should be noted.
- **`selection_key` types**: The framework accepts both `str` and `Tuple[str, ...]` for `selection_key` — it uses `isinstance()` internally. Both forms are valid.
- **Cascading removals**: Removing an event or round cascades through enum → transition_function → yaml → docstring → tests. Miss one and CI breaks.

### Completed audit baseline

See [FSM_AUDIT.md](FSM_AUDIT.md) for the full audit report with all findings and their resolution status.

## Open Autonomy Concepts

- **ABCI App**: FSM-based application where agents reach consensus on state transitions via Tendermint
- **Round**: A consensus round where agents submit payloads and vote
- **Behaviour**: Logic executed by each agent during a round (collects data, builds transactions)
- **Skill**: An AEA skill containing rounds, behaviours, handlers, payloads, and models
- **Composed app**: `market_maker_abci` composes `market_creation_manager_abci` with framework skills (registration, reset/pause, transaction settlement, termination)
- **`autonomy packages sync --all`**: Fetches all third-party dependencies declared in `packages.json` from IPFS

## Commit Conventions

Follow conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
