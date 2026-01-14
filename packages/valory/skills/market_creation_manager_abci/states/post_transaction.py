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

"""This module contains the PostTransactionRound of the MarketCreationManagerAbciApp."""

from typing import Optional, Tuple, cast

import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import PostTxPayload
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


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
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    none_event = Event.NONE
    collection_key = get_name(SynchronizedData.participant_to_votes)
    selection_key: Tuple[str, ...] = ("ignored",)

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
