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

"""This module contains the RequestProposedQuestionsRound of the MarketCreationManagerAbciApp."""

from enum import Enum
from typing import Optional, Tuple

from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RequestProposedQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


class RequestProposedQuestionsRound(CollectSameUntilThresholdRound):
    """RequestProposedQuestionsRound — builds a Mech request for question generation."""

    payload_class = RequestProposedQuestionsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.MECH_REQUEST_DONE
    none_event = Event.SKIP
    no_majority_event = Event.NO_MAJORITY
    selection_key = (get_name(SynchronizedData.mech_requests),)
    collection_key = get_name(SynchronizedData.participant_to_votes)

    def end_block(
        self,
    ) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            if payload is None or payload == "null":
                return self.synchronized_data, Event.SKIP
            new_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{get_name(SynchronizedData.mech_requests): payload},
            )
            return new_data, Event.MECH_REQUEST_DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None
