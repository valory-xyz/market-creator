# CLAUDE.md — Market Creator

## Project Overview

Market Creator is an **autonomous service** built on the [Open Autonomy](https://stack.olas.network/open-autonomy/) framework. It creates and manages prediction markets on Gnosis Chain using the OLAS stack (AEA + ABCI consensus).

**Reference repo:** [valory-xyz/trader](https://github.com/valory-xyz/trader) (develop branch) — follow the same patterns for CI, tox, and package structure.

## What the Service Does

The service autonomously creates prediction markets on Gnosis Chain. The composed
app runs registration, then an ownership check, a funds-forwarder pass, and the
three Omen recovery skills (FPMM liquidity removal, Conditional Tokens
redemption, Realitio bond withdrawal), before entering the market-creation logic.

`MarketCreationManagerAbciApp` starts at `CollectRandomnessRound` and proceeds:

1. `CollectRandomnessRound` then `SelectKeeperRound` pick the agent that drives the cycle.
2. `CollectProposedMarketsRound` asks the approval server for already-approved
   markets and the Omen subgraph for markets opening in the window. Four gates can
   short-circuit to `RetrieveApprovedMarketRound`: the `max_approved_markets` cap,
   two `min_approve_markets_epoch_seconds` timers, and unprocessed approved markets
   already waiting. A wxDAI balance below `initial_funds * 1e16` emits
   `INSUFFICIENT_FUNDS` instead.
3. `RequestProposedQuestionsRound` builds a Mech request for the
   `propose-question` tool, passing `topics`, `news_sources`, `num_questions` and
   `resolution_time` as `extra_attributes`. Question generation, the LLM calls and
   the NewsAPI fetch all happen inside the Mech tool, not in this service.
4. `ProcessProposedQuestionsRound` parses the Mech response and posts the
   questions to the approval server.
5. `RetrieveApprovedMarketRound` claims one approved market, and
   `CreateMarketTxRound` builds the multisend that deploys the FPMM, adds
   liquidity and creates the Realitio question.

`DepositDaiRound` wraps xDAI into wxDAI and is reached from `PostTransactionRound`
on `ERROR`, not on the main path. `PostTransactionRound` is the multiplexer after
every settlement: it reads which transaction type was submitted and routes to the
matching final state.

### Contracts

- **FPMM Deterministic Factory** (`fpmm_deterministic_factory/`): Deploys FPMM instances deterministically. Also handles Conditional Tokens condition creation and ERC20 approvals
- The **FPMM** contract wrapper is sourced from the [omen-protocol](https://github.com/valory-xyz/omen-protocol) upstream (third-party).

### Skill architecture

- **`market_creation_manager_abci`**: The core FSM skill with all business logic. Its `fsm_specification.yaml` declares 18 states: 9 rounds (`CollectRandomnessRound`, `SelectKeeperRound`, `CollectProposedMarketsRound`, `RequestProposedQuestionsRound`, `ProcessProposedQuestionsRound`, `RetrieveApprovedMarketRound`, `CreateMarketTxRound`, `DepositDaiRound`, `PostTransactionRound`) and 9 final states. The transition graph lives in `rounds.py` and must stay in sync with the yaml.
- **`market_maker_abci`**: The composed (chained) ABCI app defined in `composition.py`. It wires together:
  - `AgentRegistrationAbciApp`: agent startup and registration
  - `IdentifyServiceOwnerAbciApp`: checks the on-chain service owner
  - `FundsForwarderAbciApp`: forwards funds per `funds_forwarder_token_config`
  - `OmenFpmmRemoveLiquidityAbciApp`: withdraws LP from closed markets
  - `OmenCtRedeemTokensAbciApp`: redeems Conditional Tokens positions
  - `OmenRealitioWithdrawBondsAbciApp`: claims Realitio answer bonds
  - `MarketCreationManagerAbciApp`: the core logic above
  - `TransactionSubmissionAbciApp`: on-chain transaction settlement (multisig safe)
  - `MechInteractAbciApp`: Mech agent request/response cycle
  - `ResetPauseAbciApp`: period reset between cycles
  - `TerminationAbciApp`: graceful shutdown (background app)

  The transition mapping in `composition.py` defines how final states of one sub-app connect to initial states of another. For example, `FinishedMarketCreationManagerRound` → `TransactionSettlementAbci` (to submit the prepared tx), and after settlement `PostTransactionRound` routes back to the appropriate next step based on which transaction type was settled.

## Repository Structure

```text
packages/valory/
├── contracts/
│   ├── fpmm_deterministic_factory/      # Factory contract for deterministic FPMM creation
│   └── ... (third-party synced contracts, incl. fpmm from omen-protocol)
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
  - `contract/valory/fpmm_deterministic_factory/0.1.0`
  - `skill/valory/market_creation_manager_abci/0.1.0`
  - `skill/valory/market_maker_abci/0.1.0`
  - `agent/valory/market_maker/0.1.0`
  - `service/valory/market_maker/0.1.0`

- **`third_party`** section: dependencies synced from IPFS via `autonomy packages sync --all`. Do not modify these directly — they are not committed to git.

## Development Commands

### Prerequisites

- Python 3.10 to 3.14 (`requires-python = ">=3.10,<3.15"`)
- [uv](https://docs.astral.sh/uv/)
- [tomte](https://github.com/valory-xyz/tomte), pinned by git SHA in `[dependency-groups].dev` and `[tool.tomte].tomte_dep_pin`

This repo is on the tomte 0.7.0 generation, so every environment is invoked as
`tomte tox -e <env>`, not bare `tox -e <env>`. tomte renders the canonical
tox.ini from `[tool.tomte]` in `pyproject.toml` plus `[tomte-extensions]` in
`tox.ini`; the repo's own `tox.ini` only supplies extension points. Run
`tomte tox --show` to see the rendered config and the real env list.

### Setup

```bash
uv sync --all-groups
source .venv/bin/activate
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
# Run all unit tests with coverage
tomte tox -e py

# Recreate the tox virtualenv (clear cache)
tomte tox -e py -r
```

The old `py{version}-{platform}` and `unit-tests` environments no longer exist;
`py` is the single test environment, and CI varies the interpreter through its
own matrix rather than through env names.

### Formatting (auto-fix)

```bash
tomte tox -e black && tomte tox -e isort
```

### Locking packages

After modifying any dev package, update the package hashes:

```bash
autonomy packages lock
```

### Linting & static analysis

```bash
tomte tox -e black-check    # Code formatting check
tomte tox -e isort-check    # Import sorting check
tomte tox -e flake8         # Linting
tomte tox -e mypy           # Type checking
tomte tox -e pylint         # Pylint
tomte tox -e darglint       # Docstring linting
tomte tox -e bandit         # Security linting
tomte tox -e safety         # Dependency vulnerability check
tomte tox -e liccheck       # License compliance check
```

### Package integrity

```bash
tomte tox -e check-hash           # Verify package hashes
tomte tox -e check-packages       # Validate package structure
tomte tox -e check-abciapp-specs  # Validate FSM specifications
```

## Testing

### Coverage enforcement

All test environments enforce **100% statement + branch coverage** via `--cov-fail-under=100`. Coverage is configured in `.coveragerc`.

Coverage is measured per-package (3 separate pytest invocations in CI) with `--cov-append` to accumulate results:

1. `market_creation_manager_abci` (first, no append) - 276 tests
2. `market_maker_abci` (append) - 58 tests
3. `fpmm_deterministic_factory` (append) - 11 tests

### Test conventions

- All external boundaries are mocked (`MagicMock` / `patch`): ledger, subgraph, mech/LLM, contract wrappers
- Shared fixtures in `conftest.py` files
- No network/RPC calls — fully deterministic
- Tests assert on public outcomes (payloads, events), not implementation details
- Total: **345 tests**

### Adding new tests

Place tests in the `tests/` directory of each package. Follow existing patterns in `conftest.py` for mocked context, synchronized data, and behaviour builders.

## CI

CI workflow: `.github/workflows/common_checks.yml`

- The `test` job matrix is `[ubuntu-24.04, macos-15, windows-2025]` x Python 3.10 to 3.14, so 15 jobs
- The `lock_check`, `copyright_and_dependencies_check` and `linter_checks` jobs run on Python 3.10 only
- `test` declares `needs: [lock_check, copyright_and_dependencies_check, linter_checks]`, so a single failing check makes every `test (...)` row report `skipping` rather than running
- tomte is pinned by git SHA (see `[tool.tomte].tomte_dep_pin`), not by a released version

## Key Gotchas

### `packages/valory/__init__.py` must exist

This file is required for Python to resolve `packages.valory.*` imports from the local directory rather than site-packages. Without it, Windows CI fails with `ModuleNotFoundError` because Python falls back to namespace package resolution from installed wheels.

### `PYTHONPATH` uses `{env:PWD:%CD%}`

`PYTHONPATH={env:PWD:%CD%}` gives cross-platform compatibility (`PWD` on Unix, `%CD%` on Windows). It now comes from tomte's rendered canonical tox.ini rather than from this repo's `tox.ini`, so there is nothing to edit here; do not try to change it to `{toxinidir}`.

### Third-party packages are not committed

Packages synced via `autonomy packages sync --all` are fetched from IPFS at test time. They appear in `packages/` but are in `.gitignore`. Do not commit them.

### Question generation lives in the Mech, not here

`propose_questions.py` used to sit in this skill and was excluded from coverage.
It moved to the `propose-question` Mech tool in `mech-predict` (2026-06), and the
`newsapi`, `openai` and `serperapi` keys it used are configured on the Mech. This
service only sends `topics` and `news_sources` in the Mech request. There is no
coverage exclusion for it any more.

### liccheck and `[Authorized Packages]`

Packages whose license metadata PARANOID liccheck cannot accept are listed under
`[Authorized Packages]` in `tox.ini`: `setuptools` and `flask-cors` report
`UNKNOWN`, `open-autonomy` reports `Other/Proprietary`, `anchorpy` / `based58` /
`jsonalias` publish no License field, `blake3` uses a dual-license string, and
`dnspython` is ISC. A package that RELICENSED is a different case and is pinned
in `pyproject.toml` instead, so the tree keeps an approved license: `cffi<2.1.0`
plus `override-dependencies = ["cffi<2.1"]` under `[tool.uv]`, because cffi 2.1.0
moved from MIT to MIT-0. See the `oa-linters` skill.

### tox cache

If you get stale dependency errors, clear the tox cache: `rm -rf .tox` or use `tomte tox -e <env> -r`. A stale `.tox/liccheck` in particular can pass locally while CI fails, because CI always resolves fresh.

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
- **Composed app**: `market_maker_abci` chains 11 sub-apps, from `AgentRegistrationAbciApp` through the three `omen_*` recovery skills and `MarketCreationManagerAbciApp` to `MechInteractAbciApp`, `TransactionSubmissionAbciApp` and `ResetPauseAbciApp`, with `TerminationAbciApp` as a background app
- **`autonomy packages sync --all`**: Fetches all third-party dependencies declared in `packages.json` from IPFS

## Third-party Dependency Repositories

This repo depends on third-party AEA packages sourced from these upstream repositories. When bumping the open-autonomy framework version, each upstream repo must be checked for a compatible release tag:

| Repository | What it provides |
|------------|-----------------|
| [open-autonomy](https://github.com/valory-xyz/open-autonomy) | Core framework: abstract_round_abci, registration, transaction_settlement, reset_pause, termination |
| [open-aea](https://github.com/valory-xyz/open-aea) | AEA framework: protocols (contract_api, ledger_api, http, signing, etc.), connections, base contracts (gnosis_safe, multisend, service_registry) |
| [mech-interact](https://github.com/valory-xyz/mech-interact) | mech_interact_abci skill, mech/mech_mm/ierc1155 contracts |
| [genai](https://github.com/valory-xyz/genai) | GenAI-related packages (NVM contracts, subscription, etc.) |
| [omen-protocol](https://github.com/valory-xyz/omen-protocol) | realitio, realitio_proxy, conditional_tokens, fpmm contracts; omen_ct_redeem_tokens_abci, omen_fpmm_remove_liquidity_abci, omen_realitio_withdraw_bonds_abci skills |

## Commit Conventions

Follow conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
