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

"""This module contains the RemoveFundingRound of the MarketCreationManagerAbciApp."""

import json
from typing import Optional, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    get_name,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    RemoveFundingPayload,
)
from packages.valory.skills.market_creation_manager_abci.states.base import (
    Event,
    SynchronizedData
)


class RemoveFundingRound(CollectSameUntilThresholdRound):
    """RemoveFundingRound"""

    ERROR_PAYLOAD = "ERROR_PAYLOAD"
    NO_UPDATE_PAYLOAD = "NO_UPDATE"

    payload_class = RemoveFundingPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    none_event = Event.NONE
    selection_key: Tuple[str, ...] = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )
    collection_key = get_name(SynchronizedData.participant_to_tx_prep)

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            if self.most_voted_payload == self.NO_UPDATE_PAYLOAD:
                return self.synchronized_data, Event.NO_TX

            payload = json.loads(self.most_voted_payload)
            tx_data, market_address = payload["tx"], payload["market"]

            # Note that popping the markets_to_remove_liquidity here
            # is optimistically assuming that the transaction will be successful.
            markets_to_remove_liquidity = cast(
                SynchronizedData,
                self.synchronized_data,
            ).markets_to_remove_liquidity
            markets_to_remove_liquidity = [
                market
                for market in markets_to_remove_liquidity
                if market["address"] != market_address
            ]
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.markets_to_remove_liquidity
                    ): markets_to_remove_liquidity,
                    get_name(SynchronizedData.most_voted_tx_hash): tx_data,
                    get_name(SynchronizedData.tx_submitter): self.round_id,
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None
