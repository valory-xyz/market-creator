# RetrieveApprovedMarketRound
import json
from enum import Enum
from typing import Optional, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    OnlyKeeperSendsRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RetrieveApprovedMarketPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


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

    def end_block(
        self,
    ) -> Optional[
        Tuple[BaseSynchronizedData, Enum]
    ]:  # pylint: disable=too-many-return-statements
        """Process the end of the block."""
        if self.keeper_payload is None:
            return None

        # Keeper did not send
        if self.keeper_payload is None:  # pragma: no cover
            return self.synchronized_data, Event.DID_NOT_SEND

        # API error
        if (
            cast(RetrieveApprovedMarketPayload, self.keeper_payload).content
            == self.ERROR_PAYLOAD
        ):
            return self.synchronized_data, Event.ERROR

        # No markets available
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

        # Happy path
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
