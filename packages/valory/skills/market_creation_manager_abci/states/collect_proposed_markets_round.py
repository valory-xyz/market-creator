# CollectProposedMarketsRound
from enum import Enum
from typing import Optional, Tuple, cast
from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectProposedMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)

from packages.valory.skills.abstract_round_abci.base import get_name


class CollectProposedMarketsRound(CollectSameUntilThresholdRound):
    """CollectProposedMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    MAX_APPROVED_MARKETS_REACHED_PAYLOAD = "MAX_APPROVED_MARKETS_REACHED_PAYLOAD"
    SKIP_MARKET_APPROVAL_PAYLOAD = "SKIP_MARKET_APPROVAL_PAYLOAD"

    payload_class = CollectProposedMarketsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    none_event = Event.NONE
    collection_key = get_name(SynchronizedData.participant_to_selection)
    selection_key = get_name(SynchronizedData.collected_proposed_markets_data)

    def end_block(self) -> Optional[Tuple[SynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)
        payload = self.most_voted_payload

        if event == Event.DONE and payload == self.ERROR_PAYLOAD:
            return synced_data, Event.ERROR

        if event == Event.DONE and payload == self.MAX_RETRIES_PAYLOAD:
            return synced_data, Event.MAX_RETRIES_REACHED

        if event == Event.DONE and payload == self.MAX_APPROVED_MARKETS_REACHED_PAYLOAD:
            return synced_data, Event.MAX_APPROVED_MARKETS_REACHED

        if event == Event.DONE and payload == self.SKIP_MARKET_APPROVAL_PAYLOAD:
            return synced_data, Event.SKIP_MARKET_APPROVAL

        return synced_data, event
