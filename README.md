# Market Creator

Market Creator is an autonomous service that uses news feeds and LLMs to **create and manage prediction markets** on [Omen](https://aiomen.eth.limo/) (Gnosis chain). It is an [agent service](https://stack.olas.network/open-autonomy/get_started/what_is_an_agent_service/) built on the [Open Autonomy](https://stack.olas.network/open-autonomy/) framework.

## What the service does

Each cycle, the agent runs an ABCI FSM that goes through these phases:

1. **Deposit DAI** — wrap xDAI into wxDAI for market funding.
2. **Collect proposed markets** — decide how many new markets are needed per upcoming opening timestamp.
3. **Propose and approve markets** — call the `propose-question` Mech tool to generate candidate questions from current news, then push approved candidates to a market approval server.
4. **Create markets on-chain** — pull approved markets from the server and multisend:
   - FPMM deployment via `FPMMDeterministicFactory`
   - Liquidity funding
   - Realitio question creation
5. **Recover funds from closed markets** — via three dedicated sub-skills:
   - `omen_fpmm_remove_liquidity_abci` — remove LP from expired markets
   - `omen_realitio_withdraw_bonds_abci` — reclaim Realitio bonds
   - `omen_ct_redeem_tokens_abci` — redeem winning conditional tokens


## Prepare the environment

- System requirements:

  - Python `>=3.10, <3.15`
  - [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
  - [uv](https://docs.astral.sh/uv/)
  - [Docker Engine](https://docs.docker.com/engine/install/)
  - [Docker Compose](https://docs.docker.com/compose/install/)

Clone and install:

      git clone https://github.com/valory-xyz/market-creator.git

- Create development environment:

      uv sync --all-groups
      source .venv/bin/activate
  
- Configure the Open Autonomy framework:

      autonomy init --reset --author valory --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"

- Pull packages required to run the service:

      autonomy packages sync --update-packages

## Prepare the keys and the Safe

You need a Gnosis keypair and a [Safe](https://safe.global/) address.

Create `keys.json`:

```bash
cat > keys.json << EOF
[
  {
    "address": "YOUR_AGENT_ADDRESS",
    "private_key": "YOUR_AGENT_PRIVATE_KEY"
  }
]
EOF
```

For the Safe, you can register the service on the [OLAS Protocol](https://registry.olas.network/gnosis/services/mint) ((canonical agent id `12`) or set up your own Safe.

## Configure the service

Set these environment variables (defaults in [service.yaml](packages/valory/services/market_maker/service.yaml)):

```bash
# Chain
export GNOSIS_LEDGER_RPC=YOUR_RPC
export ALL_PARTICIPANTS='["YOUR_AGENT_ADDRESS"]'
export SAFE_CONTRACT_ADDRESS=YOUR_SAFE_ADDRESS

# News + LLM
export NEWSAPI_ENDPOINT=https://newsapi.org/v2
export NEWSAPI_API_KEY=YOUR_NEWSAPI_KEY
export OPENAI_API_KEY=YOUR_OPENAI_KEY
export SERPER_API_KEY=YOUR_SERPER_KEY
export SUBGRAPH_API_KEY=YOUR_THEGRAPH_KEY

# Market approval server (see below)
export MARKET_APPROVAL_SERVER_URL=http://127.0.0.1:5000
export MARKET_APPROVAL_SERVER_API_KEY=YOUR_SERVER_API_KEY

# Market generation tuning
export MARKETS_TO_APPROVE_PER_DAY=10
export APPROVE_MARKET_EVENT_DAYS_OFFSET=5
export MARKET_FEE=2.0
export INITIAL_FUNDS=1.0
export MARKET_TIMEOUT=1
export MIN_MARKET_PROPOSAL_INTERVAL_SECONDS=7200
export TOPICS='["business","science","technology","politics","finance","international"]'
```

Key variables:

| Variable | Purpose |
|---|---|
| `ALL_PARTICIPANTS` | JSON list of agent addresses (single-agent setup: one entry) |
| `SAFE_CONTRACT_ADDRESS` | Multisig for the service |
| `NEWSAPI_API_KEY` | [NewsAPI](https://newsapi.org/) key for news ingestion |
| `OPENAI_API_KEY` | Key used by the `propose-question` Mech tool |
| `SERPER_API_KEY` | Google Serper key used by the tool for supplementary search |
| `SUBGRAPH_API_KEY` | The Graph API key (Omen/Realitio subgraphs) |
| `MARKET_APPROVAL_SERVER_URL` | Approval server endpoint (publicly reachable in production) |
| `MARKETS_TO_APPROVE_PER_DAY` | Target count of approved markets per opening timestamp |
| `APPROVE_MARKET_EVENT_DAYS_OFFSET` | How far in the future markets are opened (default 5 days) |
| `MARKET_FEE` | LP fee, percent |
| `INITIAL_FUNDS` | Initial liquidity in wxDAI |
| `MARKET_TIMEOUT` | Realitio challenge window, days |
| `TOPICS` | JSON list of news topics to draw from |

## Launch the market approval server

The service proposes markets to a separate approval server before creating them on-chain.

1. Pick an API key and compute its SHA-256:
   ```bash
   echo -n "your_api_key" | sha256sum
   ```
2. Create `market_approval_server/server_config.json`:
   ```json
   {
     "proposed_markets": {},
     "approved_markets": {},
     "rejected_markets": {},
     "processed_markets": {},
     "api_keys": {
       "YOUR_SHA256_HASH": "default_user"
     }
   }
   ```
3. Run the server ([market_approval_server.py](market_approval_server/market_approval_server.py)):
   ```bash
   python market_approval_server/market_approval_server.py
   ```
4. Explore endpoints at `http://localhost:5000/`.

## Run the service

### As a Docker deployment

```bash
autonomy fetch --local --service valory/market_maker && cd market_maker
autonomy build-image
cp path/to/keys.json .
autonomy deploy build --n 1 -ltm
autonomy deploy run --build-dir abci_build/
```

### As a local agent (development)

The repo provides a Make target that wraps `aea-helpers run-agent`:

```bash
pip install open-aea-helpers
```

### Run as a local agent (development)

1. Set up your `.env` file with required environment variables
2. Place your `ethereum_private_key.txt` in the repo root
3. Run:

```bash
aea-helpers run-agent \
  --name valory/market_maker \
  --connection-key
```

To run multiple agents on the same machine, add `--free-ports`.

### Run as a service (Docker deployment)

```bash
aea-helpers run-service --name valory/market_maker --env-file .env
```

## Local Testing Setup

### 1. Essential Credentials

1. **Agent Setup**
   - You only need a signer key pair and agent address
   - You can reuse existing trader agent credentials
   - No need for full service registration

2. **OpenAI Configuration**
   - Create an OpenAI account
   - Generate an API key
   - Fund account with minimum $5
   - Add key to `.env`

3. **The Graph Integration**
   - Generate an API key from The Graph platform
   - Set `SUBGRAPH_API_KEY` in `.env`

4. **Market Approval Server**
   - Generate a server API key
   - Create its SHA-256 hash:
     ```bash
     echo -n "your_api_key_here" | sha256sum
     ```
   - Create a file `market_approval_server/server_config.json` with content of
   ```json
    {
        "proposed_markets": {},
        "approved_markets": {},
        "rejected_markets": {},
        "processed_markets": {},
        "api_keys": {
            "7b97e2b52334e1da7a395ae53ebdbd42382fa77f4dac9017569579d58db42d08": "default_user"
        }
    }
   ```
   - Add hash to `market_approval_server/server_config.json`
   - Configure server URL in `.env`:
     ```bash
     MARKET_APPROVAL_SERVER_URL=http://host.docker.internal:5000
     ```

5. **Blockchain Connection**
   - Create Tenderly account
   - Generate virtual RPC endpoint
   - Update `GNOSIS_LEDGER_RPC` in `.env`

### 2. Launch Services

1. Start market approval server (see section above)
2. Launch market maker service
3. Monitor service operation through logs

Note: Ensure all environment variables in `.env` are properly set before launching services.

## Third-party Dependencies

This service depends on third-party AEA packages sourced from the following upstream repositories (all under [valory-xyz](https://github.com/valory-xyz) on GitHub):

| Repository | What it provides |
| ---------- | --------------- |
| [open-aea](https://github.com/valory-xyz/open-aea) | AEA framework: protocols (contract_api, ledger_api, http, signing, etc.), connections, base contracts (gnosis_safe, multisend, service_registry) |
| [open-autonomy](https://github.com/valory-xyz/open-autonomy) | Core framework: abstract_round_abci, registration, transaction_settlement, reset_pause, termination |
| [mech-interact](https://github.com/valory-xyz/mech-interact) | mech_interact_abci skill, mech/mech_mm/ierc1155 contracts |
| [genai](https://github.com/valory-xyz/genai) | GenAI-related packages (NVM contracts, subscription, etc.) |
| [trader](https://github.com/valory-xyz/trader) | realitio, realitio_proxy, conditional_tokens contracts |

These packages are synced from IPFS via `autonomy packages sync --all` and are not committed to the repository.

## For advanced users

The market maker agent is configured to work with the Gnosis chain by default, if you want to use the agent with other chains you can figure out what contracts to use from [here](https://github.com/protofire/omen-exchange/blob/a98fff28a71fa53b43e7ae069924564dd597d9ba/README.md)

You can explore the [`service.yaml`](https://github.com/valory-xyz/market-creator/blob/main/packages/valory/services/market_maker/service.yaml) file, which contains all the possible configuration variables for the service.

The Safe of the service holds the collateral token used to provide the initial liquidity to the markets created. By default the service uses `WxDAI` as collateral. This is configured through the environment variable `COLLATERAL_TOKEN_CONTRACT`, which points to the address of the collateral token to be used for market. The default is [WxDAI](https://gnosisscan.io/address/0xe91d153e0b41518a2ce8dd3d7944fa863463a97d).

Finally, if you are experienced with the [Open Autonomy](https://stack.olas.network/) framework, you can also modify the internal business logic of the service yourself.
