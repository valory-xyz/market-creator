# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

# AnswerQuestionsRound
from typing import Optional, Tuple
from packages.valory.skills.abstract_round_abci.base import CollectSameUntilThresholdRound, BaseSynchronizedData
from packages.valory.skills.market_creation_manager_abci.payloads import AnswerQuestionsPayload
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData
from packages.valory.skills.abstract_round_abci.base import get_name


class AnswerQuestionsRound(CollectSameUntilThresholdRound):
    """AnswerQuestionsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_TX_PAYLOAD = "NO_TX_PAYLOAD"

    payload_class = AnswerQuestionsPayload
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