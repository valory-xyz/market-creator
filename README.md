# Market creator

MArket creator is an autonomous service that processes worlwide news using an LLM and creates bets on prediction markets on the Gnosis chain.

## Developers

- Clone the repository:

      git clone https://github.com/valory-xyz/market-creator.git

- System requirements:

    - Python `== 3.10`
    - [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
    - [Poetry](https://python-poetry.org/docs/) `>=1.4.0`
    - [Docker Engine](https://docs.docker.com/engine/install/)
    - [Docker Compose](https://docs.docker.com/compose/install/)

- Create development environment:

      poetry install && poetry shell

- Configure command line:

      autonomy init --reset --author valory --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"

- Pull packages:

      autonomy packages sync --update-packages

## Testing the service against Gnosis Mainnet

* Prepare the agent keys:
    ```
    cat > keys.json << EOF
    [
    {
        "address": "<your_agent_address>",
        "private_key": "<your_agent_private_key>"
    }
    ]
    EOF
    ```

* Prepare an .env file like the following:
    ```
    MULTISEND_ADDRESS=<your_multisend_address>
    NUM_MARKETS=1  # markets to create
    NEWSAPI_ENDPOINT=https://newsapi.org/v2/everything
    NEWSAPI_API_KEY=<your_news_api_key>
    KEY_DIR=<path_to_the_folder_containing_your_keys>
    OPENAI_API_KEY=<your_openai_api_key>
    ETHEREUM_LEDGER_RPC=http://host.docker.internal:8545
    RESET_PAUSE_DURATION=10
    ETHEREUM_LEDGER_CHAIN_ID=1
    ALL_PARTICIPANTS='["<your_agent_address>"]'
    ```

* Build and run the service:
    ```
    bash run_service.sh
    ```