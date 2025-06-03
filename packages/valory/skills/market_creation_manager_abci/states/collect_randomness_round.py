# A round for generating collecting randomness
from enum import Enum
from typing import Optional, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    CollectRandomnessPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


class CollectRandomnessRound(CollectSameUntilThresholdRound):
    """A round for generating collecting randomness"""

    payload_class = CollectRandomnessPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_randomness)
    selection_key = ("ignored", get_name(SynchronizedData.most_voted_randomness))

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)

        # Fix to ensure properties are present on the SynchronizedData
        # before ResetAndPause round.
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
        synced_data = synced_data.ensure_property_is_set(
            get_name(SynchronizedData.mech_responses)
        )

        # End fix

        return synced_data, event
