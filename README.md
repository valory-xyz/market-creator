# Market creator

Market Creator (or Market Maker) is an autonomous service that interacts with news providers and LLMs to **create prediction markets** on the [Omen](https://aiomen.eth.limo/) platform (Gnosis chain). The workflow of the service is as follows:

1. Gather headlines and summaries of recent news through a third-party provider.
2. Interact with an LLM (using the gathered information in the previous step) to obtain a collection of suitable questions to open prediction markets associated to future events.
3. Propose the generated markets to a market approval server. Users interact with this server, review and approve/reject the proposed markets.
4. Collect an user-approved market from the server.
5. Send the necessary transactions to the Gnosis chain to open and fund the market on [Omen](https://aiomen.eth.limo/).
6. Remove liquidity of markets whose closing date is <= 1 day.
7. Repeat.

The Market Creator service is an [agent service](https://docs.autonolas.network/open-autonomy/get_started/what_is_an_agent_service/) (or autonomous service) based on the [Open Autonomy framework](https://docs.autonolas.network/open-autonomy/). Below we show you how to prepare your environment, how to prepare the agent keys, and how to configure and run the service.

## Prepare the environment

- System requirements:

  - Python `== 3.10`
  - [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
  - [Poetry](https://python-poetry.org/docs/) `>=1.4.0`
  - [Docker Engine](https://docs.docker.com/engine/install/)
  - [Docker Compose](https://docs.docker.com/compose/install/)

- Clone this repository:

      git clone https://github.com/valory-xyz/market-creator.git

- Create development environment:

      poetry install && poetry shell
  
- Configure the Open Autonomy framework:

      autonomy init --reset --author valory --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"

- Pull packages required to run the service:

      autonomy packages sync --update-packages

## Prepare the keys and the Safe

You need a **Gnosis keypair** and a **[Safe](https://safe.global/) address** to run the service.

First, prepare the `keys.json` file with the Gnosis keypair of your agent. (Replace the uppercase placeholders below):

    cat > keys.json << EOF
    [
    {
        "address": "YOUR_AGENT_ADDRESS",
        "private_key": "YOUR_AGENT_PRIVATE_KEY"
    }
    ]
    EOF

Next, prepare the [Safe](https://safe.global/). The trader agent runs as part of a **trader service**, 
which is an [autonomous service](https://docs.autonolas.network/open-autonomy/get_started/what_is_an_agent_service/) 
represented on-chain in the [Autonolas Protocol](https://docs.autonolas.network/protocol/) by a [Safe](https://safe.global/) multisig. Follow the next steps to obtain a **Safe address** corresponding to your agent address:

1. Visit https://registry.olas.network/gnosis/services/mint and connect to the Gnosis network. We recommend connecting using a wallet with a Gnosis EOA account that you own.
2. Fill in the following fields:
    - *"Owner address"*: a Gnosis address for which you will be able to sign later using a supported wallet. If you want to use the address you are connected to, click on *"Prefill Address"*.
    - Click on *"Generate Hash & File"* and enter the value corresponding to the `service/valory/trader/0.1.0` key in [`packages.json`](https://github.com/valory-xyz/trader/blob/main/packages/packages.json)
    - *"Canonical agent Ids"*: enter the number `12`
    - *"No. of slots to canonical agent Ids"*: enter the number `1`
    - *"Cost of agent instance bond (wei)"*: enter the number `10000000000000000`
    - *"Threshold"*: enter the number `1`
3. Press the *"Submit"* button. Your wallet will ask you to approve the transaction. Once the transaction is settled, you should see a message indicating that the service NFT has been minted successfully. You should also see that the service is in *Pre-Registration* state.
4. Next, you can navigate to https://registry.olas.network/services#my-services, select your service and go through the steps:
    1. Activate registration
    2. Register agents: **here, you must use your agent address**.
    3. This is the last step. A transaction for the Safe deployment is already prepared and needs to be executed.
5. After completing the process you should see that your service is **Deployed**, and you will be able to retrieve your **Safe contract address** as shown in the image below:

<img src="/img/safe_address_screenshot.png" alt="Safe address field" width="500"/>

**You need to provide some funds both to your agent address (xDAI) and to the Safe address (Wrapped xDAI) in order to open prediction markets in Omen.**

## Configure the service

Set up the following environment variables, which will modify the performance of the trading agent. **Please read their description below**. We provide some defaults, but feel free to experiment with different values. Note that you need to provide `YOUR_AGENT_ADDRESS` and `YOUR_SAFE_ADDRESS` from the section above.

```bash
export ETHEREUM_LEDGER_RPC=INSERT_YOUR_RPC
export ETHEREUM_LEDGER_CHAIN_ID=100

export ALL_PARTICIPANTS='["YOUR_AGENT_ADDRESS"]'
export SAFE_CONTRACT_ADDRESS="YOUR_SAFE_ADDRESS"

export NEWSAPI_ENDPOINT=https://newsapi.org/v2/top-headlines
export NEWSAPI_API_KEY=YOUR_NEWSAPI_API_KEY
export OPENAI_API_KEY=YOUR_OPENAI_API_KEY
export ENGINE="gpt-4.1-2025-04-14"
export MARKET_APPROVAL_SERVER_URL=YOUR_MARKET_APPROVAL_SERVER_URL
export MARKET_APPROVAL_SERVER_API_KEY=YOUR_MARKET_APPROVAL_SERVER_API_KEY

export MIN_MARKET_PROPOSAL_INTERVAL_SECONDS=1800
export TOPICS='["business","science","technology","politics","arts","weather"]'
export MARKET_FEE=2
export INITIAL_FUNDS=1
export MARKET_TIMEOUT=1
export MARKET_IDENTIFICATION_PROMPT=$(sed -e ':a' -e 'N' -e '$!ba' \
  -e 's/"/\\"/g' \
  -e "s/'/\\\'/g" \
  -e 's/:/;/g' \
  -e 's/\n/\\n/g' \
  market_identification_prompt.txt)
```

These are the descriptions of the variables used by the Market Creator service. If you do not define them, they will take their default values:

- `ETHEREUM_LEDGER_RPC`: RPC endpoint for the agent (you can get an RPC endpoint, e.g. [here](https://getblock.io/)).
- `ETHEREUM_LEDGER_CHAIN_ID`: identifier of the chain on which the service is running (Gnosis=100).
- `ALL_PARTICIPANTS`: list of all the agent addresses participating in the service. In this example we only are using a single agent.
- `SAFE_CONTRACT_ADDRESS`: address of the agents multisig wallet created [in the previous section](#prepare-the-keys-and-the-safe).
- `NEWSAPI_ENDPOINT`: [Newsapi](https://newsapi.org/) endpoint to retrieve recent news headlines and summaries.
- `NEWSAPI_API_KEY`: Your [Newsapi](https://newsapi.org/) API key. You can get one for testing purposes for free.
- `OPENAI_API_KEY`: Your [OpenAI](https://openai.com/) API key. You can get one for testing purposes for free.
- `ENGINE`: [OpenAI](https://openai.com/) engine. Default (and recommended) is `gpt-4.1-2025-04-14`.
- `MARKET_APPROVAL_SERVER_URL`: Your market approval server URL. It must be publicly accessible. [See below](#launch-the-market-approval-server).
- `MARKET_APPROVAL_SERVER_API_KEY`: Your market approval server API key. [See below](#launch-the-market-approval-server)
- `MIN_MARKET_PROPOSAL_INTERVAL_SECONDS`: Number of seconds between market proposals (markets are proposed 5 at a time).
- `TOPICS`: Topics to create the markets.
- `MARKET_FEE`: % liquidity provider fees on the market. Default is 2%.
- `INITIAL_FUNDS`: Initial liquidity funds for the market, in cents. Default is 1 cent (0.01 Eth, xDAI, WxDAI, etc...).
- `MARKET_TIMEOUT`: How long people will have to correct incorrect responses after they are posted on [reality.eth](https://realityeth.github.io/). Default is 1 day.
- `MARKET_IDENTIFICATION_PROMPT`: Prompt to create the market proposals on the market approval server. As defined above, it reads the contents of the file `market_identification_prompt.txt`, which you can modify and experiment with different prompts You must include the placeholders `{event_date}`, `{input_news}` and `{topics}` in the prompt.

## Launch the market approval server

The service requires to interact with a *market approval server*, which must be publicly accessible from the Internet. The workflow is as follows:

1. The Market Creator service proposes markets to the market approval server.
2. Users approve/reject the proposed markets (using `curl` commands).
3. The Market Creator service picks a random approved market from the server and creates the market in Omen.

To launch your owns instance of the market approval server:

- Define an arbitrary API key, and compute its SHA-256 hash as a hex string.
- Edit the file [market_approval_server.py](https://github.com/valory-xyz/market-creator/blob/main/market_approval_server/market_approval_server.py) and add the computed hash to the dictionary `DEFAULT_API_KEYS`.
- Run the file [market_approval_server.py](https://github.com/valory-xyz/market-creator/blob/main/market_approval_server/market_approval_server.py) in a server of your choice. Ensure it is publicly accessible from the Internet.

You can access the root address http://server_ip:5000 and examine the different commands you can interact with the server. Please, note that it runs on an unsecured http connection by default.

## Run the service

- Fetch the service:

    ```bash
    autonomy fetch --local --service valory/market_maker && cd market_maker
    ```

- Build the Docker image:

    ```bash
    autonomy build-image
    ```

- Copy your `keys.json` file prepared [in the previous section](#prepare-the-keys-and-the-safe) in the same directory:

    ```bash
    cp path/to/keys.json .
    ```

- Build the deployment with a single agent and run:

    ```bash
    autonomy deploy build --n 1 -ltm
    autonomy deploy run --build-dir abci_build/
    ```

For convenience, we provide a template script [run_service.sh](https://github.com/valory-xyz/market-creator/blob/main/run_service.sh) that you can modify and experiment with different values.

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
   - Add key to `run_service.sh`

3. **The Graph Integration**
   - Generate an API key from The Graph platform
   - Set `SUBGRAPH_API_KEY` in `run_service.sh`

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
   - Configure server URL in `run_service.sh`:
     ```bash
     MARKET_APPROVAL_SERVER_URL=http://host.docker.internal:5000
     ```

5. **Blockchain Connection**
   - Create Tenderly account
   - Generate virtual RPC endpoint
   - Update `ETHEREUM_LEDGER_RPC` in `run_service.sh`

### 2. Launch Services

1. Start market approval server (see section above)
2. Launch market maker service
3. Monitor service operation through logs

Note: Ensure all environment variables in `run_service.sh` are properly set before launching services.

## For advanced users

The market maker agent is configured to work with the Gnosis chain by default, if you want to use the agent with other chains you can figure out what contracts to use from [here](https://github.com/protofire/omen-exchange/blob/a98fff28a71fa53b43e7ae069924564dd597d9ba/README.md)

You can explore the [`service.yaml`](https://github.com/valory-xyz/market-creator/blob/main/packages/valory/services/market_maker/service.yaml) file, which contains all the possible configuration variables for the service.

The Safe of the service holds the collateral token used to provide the initial liquidity to the markets created. By default the service uses `WxDAI` as collateral. This is configured through the environment variable `COLLATERAL_TOKEN_CONTRACT`, which points to the address of the collateral token to be used for market. The default is [WxDAI](https://gnosisscan.io/address/0xe91d153e0b41518a2ce8dd3d7944fa863463a97d).

Finally, if you are experienced with the [Open Autonomy](https://docs.autonolas.network/) framework, you can also modify the internal business logic of the service yourself.
