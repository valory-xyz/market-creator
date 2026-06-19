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

"""This module contains the ProcessProposedQuestionsRound of the MarketCreationManagerAbciApp."""

from packages.valory.skills.abstract_round_abci.base import (
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ProcessProposedQuestionsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData,
)


class ProcessProposedQuestionsRound(CollectSameUntilThresholdRound):
    """ProcessProposedQuestionsRound -- consume Mech response and approve markets.

    Entered after MechInteract delivers question proposals. Reads
    ``mech_responses`` from SynchronizedData, matches by nonce, parses
    the tool JSON, and calls the approval server for each valid question.

    Payload fields mirror RequestProposedQuestionsPayload:
    - content: JSON of proposed markets (or ``{}`` on failure)
    - approved_markets_count: running total (cross-period)
    - timestamp: last_synced_timestamp
    """

    ERROR_PAYLOAD = "ERROR_PAYLOAD"

    payload_class = ProcessProposedQuestionsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    none_event = Event.NONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_votes)
    selection_key = (
        "content",
        get_name(SynchronizedData.approved_markets_count),
        get_name(SynchronizedData.approved_markets_timestamp),
    )
