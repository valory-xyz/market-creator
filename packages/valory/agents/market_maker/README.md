# Market Maker agent

Market Maker agent processes worldwide news using an LLM and opens prediction markets on the Gnosis chain. The agent roughly works as follows:

1. Gather headlines and summaries of recent news through a third-party provider.
2. Interact with an LLM (using the gathered information in the previous step) to obtain a collection of suitable questions to open prediction markets associated to future events.
3. Propose questions to a market approval service endpoint. Users manually approve suitable markets using that endpoint.
4. Collect user-approved markets from the market approval service.
5. Send the necessary transactions to the Gnosis chain to open and fund the chosen prediction market.
6. Repeat steps 1-5. When `NUM_MARKETS` (configurable) have been created, the service will cycle in a waiting state.
