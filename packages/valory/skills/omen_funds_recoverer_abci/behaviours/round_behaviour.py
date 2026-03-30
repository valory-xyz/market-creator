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

"""This module contains the round behaviour for the omen_funds_recoverer_abci skill."""

from packages.valory.skills.abstract_round_abci.behaviours import AbstractRoundBehaviour
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.build_multisend import (
    BuildMultisendBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.claim_bonds import (
    ClaimBondsBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.redeem_positions import (
    RedeemPositionsBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.behaviours.remove_liquidity import (
    RemoveLiquidityBehaviour,
)
from packages.valory.skills.omen_funds_recoverer_abci.rounds import (
    OmenFundsRecovererAbciApp,
)


class OmenFundsRecovererRoundBehaviour(AbstractRoundBehaviour):
    """OmenFundsRecovererRoundBehaviour"""

    initial_behaviour_cls = RemoveLiquidityBehaviour
    abci_app_cls = OmenFundsRecovererAbciApp
    behaviours = {
        RemoveLiquidityBehaviour,
        RedeemPositionsBehaviour,
        ClaimBondsBehaviour,
        BuildMultisendBehaviour,
    }
