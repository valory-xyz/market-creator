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

"""This module contains the GetPendingQuestionsRound of the MarketCreationManagerAbciApp."""

from enum import Enum
from typing import Optional, Tuple, cast

import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    GetPendingQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


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
                        SynchronizedData.tx_submitter
                    ): MechRequestStates.MechRequestRound.auto_round_id(),
                },
            ),
        )

        return synced_data, event  # type: ignore
