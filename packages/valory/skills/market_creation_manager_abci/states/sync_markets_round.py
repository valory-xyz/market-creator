# SyncMarketsRound
from typing import Optional, Tuple
import json
from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    BaseSynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    SyncMarketsPayload,
)

from packages.valory.skills.abstract_round_abci.base import get_name


class SyncMarketsRound(CollectSameUntilThresholdRound):
    """SyncMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_UPDATE_PAYLOAD = "NO_UPDATE"

    payload_class = SyncMarketsPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR
            if self.most_voted_payload == self.NO_UPDATE_PAYLOAD:
                return self.synchronized_data, Event.DONE
            payload = json.loads(self.most_voted_payload)
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.markets_to_remove_liquidity): payload[
                        "markets"
                    ],
                    get_name(SynchronizedData.market_from_block): payload["from_block"],
                },
            )
            return synchronized_data, Event.DONE
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None
