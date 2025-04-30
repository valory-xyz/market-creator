# GetPendingQuestionsRound
from typing import Optional, Tuple, cast
from packages.valory.skills.abstract_round_abci.base import CollectSameUntilThresholdRound, BaseSynchronizedData
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData
from packages.valory.skills.market_creation_manager_abci.payloads import GetPendingQuestionsPayload
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.skills.abstract_round_abci.base import get_name


class GetPendingQuestionsRound(CollectSameUntilThresholdRound):
    """GetPendingQuestionsRound"""
    payload_class = GetPendingQuestionsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    none_event = Event.NONE
    collection_key = get_name(SynchronizedData.participant_to_selection)
    selection_key = get_name(SynchronizedData.mech_requests)

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_TX_PAYLOAD = "NO_TX_PAYLOAD"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """End block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)
        payload = self.most_voted_payload

        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.approved_markets_count)
        )
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.proposed_markets_count)
        )
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.proposed_markets_data)
        )
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.approved_markets_timestamp)
        )

        if event == Event.DONE and payload == self.ERROR_PAYLOAD:
            return synced_data, Event.ERROR

        if event == Event.DONE and payload == self.NO_TX_PAYLOAD:
            return synced_data, Event.NO_TX

        synced_data = cast(
            SynchronizedData,
            synced_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.tx_sender
                    ): MechRequestStates.MechRequestRound.auto_round_id(),
                },
            ),
        )

        return synced_data, event # type: ignore