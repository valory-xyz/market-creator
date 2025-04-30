# ApproveMarketsRound
from typing import Optional, Tuple, cast
from packages.valory.skills.abstract_round_abci.base import OnlyKeeperSendsRound, BaseSynchronizedData
from packages.valory.skills.market_creation_manager_abci.payloads import ApproveMarketsPayload
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData

from packages.valory.skills.abstract_round_abci.base import get_name


class ApproveMarketsRound(OnlyKeeperSendsRound):
    """ApproveMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"

    payload_class = ApproveMarketsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    fail_event = Event.ERROR
    payload_key = (
        get_name(SynchronizedData.approved_markets_data),
        get_name(SynchronizedData.approved_markets_count),
        get_name(SynchronizedData.approved_markets_timestamp),
    )
    collection_key = get_name(SynchronizedData.participant_to_selection)

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Event], res)
        payload = cast(ApproveMarketsPayload, self.keeper_payload).content

        if event == Event.DONE and payload == self.ERROR_PAYLOAD:
            return synced_data, Event.ERROR

        if event == Event.DONE and payload == self.MAX_RETRIES_PAYLOAD:
            return synced_data, Event.MAX_RETRIES_REACHED

        return synced_data, event