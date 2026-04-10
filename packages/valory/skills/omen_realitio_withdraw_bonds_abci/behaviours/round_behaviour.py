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

"""Round behaviour wiring for the omen_realitio_withdraw_bonds_abci skill."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.omen_realitio_withdraw_bonds_abci.behaviours.withdraw_bonds import (
    RealitioWithdrawBondsBehaviour,
)
from packages.valory.skills.omen_realitio_withdraw_bonds_abci.rounds import (
    OmenRealitioWithdrawBondsAbciApp,
)


class OmenRealitioWithdrawBondsRoundBehaviour(AbstractRoundBehaviour):
    """OmenRealitioWithdrawBondsRoundBehaviour."""

    initial_behaviour_cls = RealitioWithdrawBondsBehaviour
    abci_app_cls = OmenRealitioWithdrawBondsAbciApp
    behaviours = {RealitioWithdrawBondsBehaviour}
