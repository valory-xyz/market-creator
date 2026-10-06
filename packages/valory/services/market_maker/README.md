## Market Maker Service

Market Maker service processes worldwide news using an LLM and opens prediction markets on the Gnosis chain. The service roughly works as follows:

1. Gather headlines and summaries of recent news through a third-party provider.
2. Interact with an LLM (using the gathered information in the previous step) to obtain a collection of suitable questions to open prediction markets associated to future events.
3. Propose questions to a market approval service endpoint. Users manually approve suitable markets using that endpoint.
4. Collect user-approved markets from the market approval service.
5. Send the necessary transactions to the Gnosis chain to open and fund the chosen prediction market.
6. Repeat steps 1-5. When `NUM_MARKETS` (configurable) have been created, the service will cycle in a waiting state.

### Metrics

The agent serves Prometheus metrics on port 9000 by default, and `PROMETHEUS_PORT` overrides it. The same variable sets the container side of the `deployment.agent.ports` mapping in `service.yaml`, so the published port follows the override when the variable is set while the deployment is built. The host side of the mapping stays 9000.
