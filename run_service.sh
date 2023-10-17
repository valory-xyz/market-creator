#!/usr/bin/env bash

# Define environment variables
export ETHEREUM_LEDGER_RPC=INSERT_YOUR_RPC
export ETHEREUM_LEDGER_CHAIN_ID=100

export ALL_PARTICIPANTS='["YOUR_AGENT_ADDRESS"]'
export SAFE_CONTRACT_ADDRESS="YOUR_SAFE_ADDRESS"

export NEWSAPI_ENDPOINT=https://newsapi.org/v2/top-headlines
export NEWSAPI_API_KEY=YOUR_NEWSAPI_API_KEY
export OPENAI_API_KEY=YOUR_OPENAI_API_KEY
export ENGINE="gpt-4"
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


make clean
autonomy packages lock
autonomy push-all

# Fetch the service
autonomy fetch --local --service valory/market_maker && cd market_maker

# Build the image
autonomy build-image

# Copy keys and build the deployment
# MODIFY THIS PATH IF REQUIRED
cp ../keys.json ./keys.json

# Build the deployment
autonomy deploy build -ltm

# Run the deployment
autonomy deploy run --build-dir abci_build/