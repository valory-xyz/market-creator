# PrepareTransactionRound
from enum import Enum
from typing import Optional, Tuple
from packages.valory.skills.abstract_round_abci.base import CollectSameUntilThresholdRound, BaseSynchronizedData
from packages.valory.skills.market_creation_manager_abci.payloads import PrepareTransactionPayload
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData

from packages.valory.skills.abstract_round_abci.base import get_name


class PrepareTransactionRound(CollectSameUntilThresholdRound):
    """PrepareTransactionRound"""
    payload_class = PrepareTransactionPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = "content"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """End block."""
        # TODO: incomplete implementation
        if self.threshold_reached and any(
            [val is not None for val in self.most_voted_payload_values]
        ):
            return (
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{
                        get_name(
                            SynchronizedData.most_voted_tx_hash
                        ): self.most_voted_payload,
                        get_name(SynchronizedData.tx_sender): self.round_id,
                    },
                ),
                Event.DONE,
            )
        return None