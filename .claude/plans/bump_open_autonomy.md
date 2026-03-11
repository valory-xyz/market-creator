# Plan: Bump open-autonomy Framework

Procedure to bump the open-autonomy framework version in an Open Autonomy service repository. This plan is service-agnostic and can be reused across repositories.

---

## Phase 1 — Inputs

The user provides:

1. **Target open-autonomy version** (e.g., `0.21.13`)
2. **Third-party dependency repository tags** — read the "Third-party Dependency Repositories" section in `CLAUDE.md` to know which upstream repos this service depends on. Identify the release tag of each repo that corresponds to the target open-autonomy version.

---

## Phase 2 — Resolve Dependency Versions

Go to the [open-autonomy releases](https://github.com/valory-xyz/open-autonomy/releases) page and find the target version tag. From its `pyproject.toml` (or `setup.cfg`), extract the pinned versions of:

| Library | Description |
| ------- | ----------- |
| `open-aea` | AEA framework core |
| `open-aea-ledger-ethereum` | Ethereum ledger plugin |
| `open-aea-ledger-cosmos` | Cosmos ledger plugin |
| `open-aea-cli-ipfs` | IPFS CLI plugin |
| `open-aea-test-autonomy` | Test utilities (version tracks open-autonomy) |
| `tomte` | Linter/tooling orchestrator |

Also note any transitive dependency changes (e.g., `protobuf`, `grpcio`, `requests`, `web3`, `openapi-core`, `jsonschema`, `typing_extensions`). These often change between major bumps.

Record all resolved versions — they will be used in every file below.

---

## Phase 3 — Bump Version Pins

### 3.1 `pyproject.toml`

Update all version pins in `[tool.poetry.dependencies]`:

```toml
open-autonomy = "==<TARGET>"
open-aea-ledger-ethereum = "==<AEA_LEDGER>"
open-aea-ledger-cosmos = "==<AEA_LEDGER>"
open-aea-cli-ipfs = "==<AEA_CLI>"
open-aea-test-autonomy = "==<TARGET>"
tomte = {version = "==<TOMTE>", extras = ["cli", "tests"]}
```

Also:
- Bump transitive deps to match open-autonomy's requirements
- Update the Python version constraint if the new framework supports additional versions (e.g., `>=3.10,<3.15`)
- Update classifiers to list all supported Python versions
- Use `poetry lock` to let the solver resolve compatible versions where possible

### 3.2 `tox.ini`

Update **all** occurrences (there are many). Key sections:

- `[deps-packages]`: `open-autonomy`, `open-aea-*`, `open-aea-test-autonomy`
- `[extra-deps]`: `open-aea-test-autonomy` (if present)
- `[deps-tests]`: `tomte[tests]`
- `[testenv:check-hash]`: `open-autonomy[all]` (may also need `jsonschema` pin — see Pitfalls)
- All linter environments: `tomte[bandit]`, `tomte[black]`, `tomte[isort]`, `tomte[flake8]`, `tomte[mypy]`, `tomte[pylint]`, `tomte[safety]`, `tomte[darglint]`, `tomte[liccheck,cli]`, `tomte[cli]`

**Tip**: Use find-and-replace for the old version string → new version string.

#### Tox 4 compatibility (if upgrading tomte)

Newer tomte versions pull tox 4, which has breaking changes:

- **`whitelist_externals` → `allowlist_externals`**: Renamed in tox 4. Search-and-replace all occurrences.
- **`extras = all` breaks** if `pyproject.toml` doesn't define any extras. Remove from `[testenv]` if not applicable.
- **`pkg_resources` removed from setuptools**: `liccheck` and `pylint` need `setuptools` as an explicit dep:
  ```ini
  [testenv:pylint]
  deps =
      {[deps-packages]deps}
      tomte[pylint]==<TOMTE>
      setuptools<=81.0.0
  ```
- **Test envlist**: If adding Python versions, add individual `[testenv:py3.X-platform]` sections for each new version × platform combination.
- **Verbose output**: Tox 4 shows packaging steps by default. Add `-qq` to tox calls in Makefile if applicable.

#### isort/black conflict

Newer tomte ships black that enforces 1 blank line after imports. Set isort to defer:
```ini
[isort]
lines_after_imports=-1
```

#### flake8 cleanup

Remove old pins (e.g., `snowballstemmer`, `pycodestyle`) from `[testenv:flake8]` deps if present — they conflict with newer tomte's flake8.

#### mypy duplicate module names

If mypy reports "Source file found twice under different module names", add:
```ini
[mypy]
namespace_packages = True
explicit_package_bases = True
```

### 3.3 `.github/workflows/*.yml` — ALL workflow files

**Important**: Check ALL workflow files, not just the main one. `release.yaml` is easy to miss.

Update in **every** workflow file:
- GitHub Actions versions: `actions/checkout@v4` → `@v6`, `actions/setup-python@v4` → `@v6`, `actions/setup-go` → `@v5`, `actions/upload-artifact` → `@v7`, `actions/download-artifact` → `@v8`
- OS runners: `ubuntu-latest`/`ubuntu-22.04` → `ubuntu-24.04`, `macos-latest`/`macos-14` → `macos-15`, `windows-latest` → `windows-2025`
- `tomte` version pins in `pip install` steps
- Python test matrix: add new Python versions if supported
- Docker image tags in release workflows: `valory/open-autonomy-user:<OLD>` → `<NEW>`
- `open-autonomy==<OLD>` in `autonomy build-image` commands

### 3.4 Dev package YAMLs — Component version pins

Dev package YAMLs (`skill.yaml`, `contract.yaml`, `agent.yaml`, `service.yaml`, `aea-config.yaml`) under `packages/<author>/` contain pinned dependency versions that must be updated.

Search for old versions:
```bash
grep -r "==<OLD_AEA>\|==<OLD_AUTONOMY>" packages/<author>/ --include="*.yaml"
```

Common fields to update: `open-aea-ledger-ethereum`, `open-aea-test-autonomy`, `requests`, `typing_extensions`.

**Only update dev packages** (listed in `packages.json` under `"dev"`). Third-party packages are managed by upstream repos.

### 3.5 Third-party packages in `packages/` folder

Third-party packages (listed in `packages.json` under `"third_party"`) have their own YAML configs with pinned dependency versions. These are updated automatically by `autonomy packages sync --update-packages` — do not edit them manually.

### 3.6 `packages/packages.json` — Third-party hashes

Third-party package hashes must be updated to match the versions published by the upstream repos at the target open-autonomy version.

Steps:
1. Read `CLAUDE.md` for the list of upstream repos this service depends on
2. Identify which tag/release of each upstream repo corresponds to the target version
3. **Option A** — If you have upstream repos cloned locally, use a `compare_hashes.py` script (see Appendix) to identify mismatches, then update hashes manually
4. **Option B** — Run `autonomy packages sync --update-packages` to fetch correct hashes from IPFS

**Critical**: Packages come from MULTIPLE upstream repos, not just open-autonomy. Running against only one repo will leave packages with stale hashes.

### 3.7 Test file compatibility

If upgrading across a major open-aea version, test base classes may have changed:

- **`BaseSkillTestCase`**: `setup()` → `setup_method()`, must set `path_to_skill` explicitly
- **`BaseContractTestCase`**: `setup()` → `setup_class()`, must set `path_to_contract` and `ledger_identifier` explicitly

Check the [open-aea upgrading guide](https://github.com/valory-xyz/open-aea/blob/main/docs/upgrading.md) for API changes.

---

## Phase 4 — Finalize

Run in order:

```bash
# 1. Lock and install poetry deps
poetry lock
poetry install --no-root

# 2. Sync all packages (resolves and downloads third-party)
autonomy init --reset --author ci --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"
autonomy packages sync --all

# 3. Format code
tox -e black
tox -e isort

# 4. Lock package hashes
autonomy packages lock
```

**Hash cascade**: After `autonomy packages sync`, third-party package files are updated on disk. Since dev packages depend on these, their hashes change too. You MUST run `autonomy packages lock` after sync — otherwise `lock --check` fails.

---

## Phase 5 — Verify

Run in this order (each step may require fixes before proceeding):

```bash
# 1. Poetry resolution
poetry lock
poetry install --no-root

# 2. Package hash integrity
autonomy packages lock --check

# 3. Formatting
tox -e black-check
tox -e isort-check

# 4. Linting
tox -e flake8
tox -e mypy
tox -e pylint
tox -e darglint
tox -e bandit

# 5. Unit tests (adjust Python version and platform)
tox -e py3.11-linux

# 6. Package checks
tox -e check-hash
tox -e check-packages
tox -e check-abciapp-specs
tox -e check-abci-docstrings

# 7. Security and compliance
tox -e safety          # add -i <ID> for new vulnerabilities
tox -e liccheck        # add new license strings if needed
tox -e copyright-check
tox -e spell-check     # may need .spelling file updates
```

**Important**: If any step modifies files under `packages/` (e.g., linter auto-fixes, adding `# nosec` comments), re-run `autonomy packages lock` before proceeding.

---

## Files Modified (Summary)

| File | What changes |
| ---- | ------------ |
| `pyproject.toml` | `open-autonomy`, `open-aea-*`, `tomte`, transitive deps, Python constraint, classifiers |
| `tox.ini` | Version pins (~15 sections), tox 4 compat, test envlist, isort/mypy config |
| `.github/workflows/*.yml` | Actions versions, OS runners, tomte pins, Docker image tags, Python matrix |
| `packages/packages.json` | Third-party IPFS hashes (+ dev hashes after re-lock) |
| `packages/<author>/**/*.yaml` | Dependency version pins in dev package YAMLs |
| `poetry.lock` | Auto-generated by `poetry lock` |
| `Makefile` | Add `-qq` to tox calls (tox 4 verbosity) |
| `.spelling` | Add repo-specific terms if `spell-check` fails |
| Test files | `setup` → `setup_method`/`setup_class` if base class API changed |

---

## Common Pitfalls

- **Forgetting a `tox.ini` section**: The old version string appears in ~15 places. A global find-and-replace is safest.
- **Hash mismatch after sync**: After `autonomy packages sync`, dev hashes cascade-change. Always re-run `autonomy packages lock`.
- **Poetry solver conflicts**: If `poetry lock` fails, check that transitive deps are compatible with the new open-autonomy. Widen constraints if needed.
- **Third-party repo tags**: Each upstream repo may not have a release for every open-autonomy version. Check which tag is compatible before updating.
- **Multiple upstream repos**: Packages come from several repos (see `CLAUDE.md`). Syncing against only open-autonomy will leave stale hashes.
- **`check-hash` needs jsonschema**: If `check-hash` fails with `ModuleNotFoundError: No module named 'jsonschema._keywords'`, add `jsonschema>=4.23.0,<5.0.0` to the `[testenv:check-hash]` deps.
- **release.yaml**: The release workflow has its own version pins (Docker images, autonomy version, action versions). Always search ALL `.github/workflows/*.yml` files.
- **CI env name mismatch**: In tox 4, if a named env doesn't exist, it falls back to `[testenv]` base which runs the wrong commands silently. Verify that tox env names in CI match actual `[testenv:*]` sections.
- **Dev YAML pins**: Dev package YAMLs contain version pins that must match pyproject.toml/tox.ini. Easy to forget.
- **Bandit false positives**: Bandit B105 flags dict keys containing "password"/"secret"/"token" even with `None` values. Add `# nosec` inline, then re-lock.
- **Safety vulnerabilities**: New deps may introduce new CVE IDs. Add `-i <ID>` to the safety command as needed.
- **License compliance**: New transitive deps may introduce licenses not in `[Licenses] authorized_licenses`. Add the license string (e.g., `PSF-2.0`) rather than adding the package to `[Authorized Packages]`.
- **Copyright check**: The `--author` flag scans `packages/<author>/` — only use authors whose packages have matching copyright headers.

---

## Appendix: Hash Comparison Script

A local-only script (not committed) to compare third-party hashes against upstream source repos. Adapt `SOURCE_REPOS` per repository — read `CLAUDE.md` for the list of upstream repos.

```python
#!/usr/bin/env python3
"""Compare package hashes between source-of-truth repos and this repo."""

import json
from pathlib import Path

# Adjust per repo — read CLAUDE.md for upstream dependency repos
SOURCE_REPOS = [
    Path("/path/to/open-autonomy/packages/packages.json"),
    Path("/path/to/open-aea/packages/packages.json"),
    # Add other upstream repos as listed in CLAUDE.md
]

TARGET_PACKAGES_JSON = Path("packages/packages.json")


def main() -> None:
    """Compare hashes."""
    source_all = {}
    for repo_path in SOURCE_REPOS:
        if not repo_path.exists():
            print(f"WARNING: {repo_path} not found, skipping")
            continue
        with open(repo_path, encoding="utf-8") as f:
            source = json.load(f)
        source_all.update(source.get("third_party", {}))
        source_all.update(source.get("dev", {}))

    with open(TARGET_PACKAGES_JSON, encoding="utf-8") as f:
        target = json.load(f)

    target_third = target.get("third_party", {})

    mismatches = []
    missing = []
    for pkg, target_hash in target_third.items():
        if pkg in source_all:
            if target_hash != source_all[pkg]:
                mismatches.append((pkg, target_hash, source_all[pkg]))
        else:
            missing.append(pkg)

    if not mismatches and not missing:
        print("All hashes match!")
        return

    if mismatches:
        print(f"Found {len(mismatches)} mismatched hashes:\n")
        for pkg, _, new in mismatches:
            print(f'  "{pkg}": "{new}",')
        print(f"\nReplace these in {TARGET_PACKAGES_JSON}")

    if missing:
        print(f"\n{len(missing)} packages not found in any source repo:")
        for pkg in missing:
            print(f"  {pkg}")


if __name__ == "__main__":
    main()
```
