# A round for redeeming Realitio
from typing import Optional, Tuple
from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    BaseSynchronizedData,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RedeemBondPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)
from packages.valory.skills.abstract_round_abci.base import get_name


class RedeemBondRound(CollectSameUntilThresholdRound):
    """A round for redeeming Realitio"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_TX_PAYLOAD = "NO_TX_PAYLOAD"

    payload_class = RedeemBondPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            if self.most_voted_payload == self.NO_TX_PAYLOAD:
                return self.synchronized_data, Event.NO_TX

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.most_voted_tx_hash
                    ): self.most_voted_payload,
                    get_name(SynchronizedData.tx_sender): self.round_id,
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None
