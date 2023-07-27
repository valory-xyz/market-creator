#!/usr/bin/env bash

# Load env vars
export $(grep -v '^#' .env | xargs)

export MARKET_IDENTIFICATION_PROMPT=$(sed -e ':a' -e 'N' -e '$!ba' \
  -e 's/"/\\"/g' \
  -e "s/'/\\\'/g" \
  -e 's/:/;/g' \
  -e 's/\n/\\n/g' \
  market_identification_prompt.txt)

make clean

autonomy packages lock
autonomy push-all

autonomy fetch --local --service valory/market_maker --alias fetched_service && cd fetched_service

# Build the image
autonomy build-image

# Copy keys and build the deployment
cp $KEY_DIR/keys.json ./keys.json

autonomy deploy build -ltm

# Run the deployment
autonomy deploy run --build-dir abci_build/