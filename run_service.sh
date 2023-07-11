#!/usr/bin/env bash

# Load env vars
export $(grep -v '^#' .env | xargs)

make clean

autonomy push-all

autonomy fetch --local --service valory/market-maker && cd market-maker

# Build the image
autonomy build-image

# Copy keys and build the deployment
cp $KEY_DIR/market-maker-key.json ./keys.json

autonomy deploy build -ltm

# Run the deployment
autonomy deploy run --build-dir abci_build/