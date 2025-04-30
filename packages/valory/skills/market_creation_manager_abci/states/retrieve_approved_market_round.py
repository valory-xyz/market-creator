# RetrieveApprovedMarketRound
from typing import Optional, Tuple, cast
import json
from packages.valory.skills.abstract_round_abci.base import OnlyKeeperSendsRound, BaseSynchronizedData
from packages.valory.skills.market_creation_manager_abci.payloads import RetrieveApprovedMarketPayload
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData
from packages.valory.skills.abstract_round_abci.base import get_name


class RetrieveApprovedMarketRound(OnlyKeeperSendsRound):
    """RetrieveApprovedMarketRound"""
    payload_class = RetrieveApprovedMarketPayload
    payload_attribute = "content"
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"
    NO_MARKETS_RETRIEVED_PAYLOAD = "NO_MARKETS_RETRIEVED_PAYLOAD"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.keeper_payload is None:
            return None

        if self.keeper_payload is None:
            return self.synchronized_data, Event.DID_NOT_SEND

        if (
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
            == self.ERROR_PAYLOAD
        ):
            return self.synchronized_data, Event.ERROR

        if (
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
            == self.NO_MARKETS_RETRIEVED_PAYLOAD
        ):
            return (
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{
                        get_name(SynchronizedData.proposed_markets_count): cast(
                            SynchronizedData, self.synchronized_data
                        ).proposed_markets_count,
                    },
                ),
                Event.NO_MARKETS_RETRIEVED,
            )

        approved_question_data = json.loads(
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
        )

        synchronized_data = self.synchronized_data.update(
            synchronized_data_class=SynchronizedData,
            **{
                get_name(
                    SynchronizedData.approved_question_data
                ): approved_question_data,
            },
        )

        return synchronized_data, Event.DONE