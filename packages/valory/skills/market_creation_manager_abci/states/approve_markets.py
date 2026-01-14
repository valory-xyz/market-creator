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

"""This module contains the ApproveMarketsRound of the MarketCreationManagerAbciApp."""

from enum import Enum
from typing import Optional, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    OnlyKeeperSendsRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    ApproveMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData
)

class ApproveMarketsRound(OnlyKeeperSendsRound):
    """ApproveMarketsRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    MAX_RETRIES_PAYLOAD = "MAX_RETRIES_PAYLOAD"

    payload_class = ApproveMarketsPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    fail_event = Event.ERROR
    payload_key = (
        get_name(SynchronizedData.approved_markets_data),
        get_name(SynchronizedData.approved_markets_count),
        get_name(SynchronizedData.approved_markets_timestamp),
    )

    def end_block(
        self,
    ) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)
        payload = cast(ApproveMarketsPayload, self.keeper_payload).content

        if event == Event.DONE and payload == self.ERROR_PAYLOAD:
            return synced_data, Event.ERROR

        if event == Event.DONE and payload == self.MAX_RETRIES_PAYLOAD:
            return synced_data, Event.MAX_RETRIES_REACHED

        return synced_data, event
