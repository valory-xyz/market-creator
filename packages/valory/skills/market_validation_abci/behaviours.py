# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023 Valory AG
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

"""This package contains round behaviours of MarketValidationAbciApp."""


from abc import ABC
from typing import Generator, Set, Type

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.market_validation_abci.payloads import (
    MarketValidationPayload,
)
from packages.valory.skills.market_validation_abci.rounds import (
    MarketValidationAbciApp,
    MarketValidationRound,
)


class MarketValidationBehaviour(BaseBehaviour, ABC):
    """DataGatheringBehaviour"""

    matching_round: Type[AbstractRound] = MarketValidationRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            payload = MarketValidationPayload(
                sender=self.context.agent_address,
                market_created=True,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()


class MarketVerificationRoundBehaviour(AbstractRoundBehaviour):
    """MarketVerificationRoundBehaviour"""

    initial_behaviour_cls = MarketValidationBehaviour
    abci_app_cls = MarketValidationAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = {
        MarketValidationBehaviour,
    }
