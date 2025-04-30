# A round to be run after a transaction has been settled.
from typing import Optional, Tuple
from packages.valory.skills.abstract_round_abci.base import CollectSameUntilThresholdRound, BaseSynchronizedData
from packages.valory.skills.market_creation_manager_abci.payloads import PostTxPayload
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData


class PostTransactionRound(CollectSameUntilThresholdRound):
    """A round to be run after a transaction has been settled."""

    DONE_PAYLOAD = "DONE_PAYLOAD"
    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MECH_REQUEST_DONE_PAYLOAD = "MECH_REQUEST_DONE_PAYLOAD"
    REDEEM_BOND_DONE_PAYLOAD = "REDEEM_BOND_DONE_PAYLOAD"
    DEPOSIT_DAI_DONE_PAYLOAD = "DEPOSIT_DAI_DONE_PAYLOAD"
    ANSWER_QUESTION_DONE_PAYLOAD = "ANSWER_QUESTION_DONE_PAYLOAD"
    REMOVE_FUNDING_DONE_PAYLOAD = "REMOVE_FUNDING_DONE_PAYLOAD"

    payload_class = PostTxPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            if self.most_voted_payload == self.MECH_REQUEST_DONE_PAYLOAD:
                return self.synchronized_data, Event.MECH_REQUEST_DONE

            if self.most_voted_payload == self.REDEEM_BOND_DONE_PAYLOAD:
                return self.synchronized_data, Event.REDEEM_BOND_DONE

            if self.most_voted_payload == self.DEPOSIT_DAI_DONE_PAYLOAD:
                return self.synchronized_data, Event.DEPOSIT_DAI_DONE

            if self.most_voted_payload == self.ANSWER_QUESTION_DONE_PAYLOAD:
                return self.synchronized_data, Event.ANSWER_QUESTION_DONE

            if self.most_voted_payload == self.REMOVE_FUNDING_DONE_PAYLOAD:
                return self.synchronized_data, Event.REMOVE_FUNDING_DONE

            # no database update is required
            return self.synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None