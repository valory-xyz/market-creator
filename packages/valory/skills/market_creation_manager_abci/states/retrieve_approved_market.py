# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2026 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This module contains the RetrieveApprovedMarketRound of the MarketCreationManagerAbciApp."""

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
    synchronized_data_class = SynchronizedData
    payload_attribute = "content"
    done_event = Event.DONE
    fail_event = Event.ERROR
    payload_key = ""  # TODO placeholder

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
