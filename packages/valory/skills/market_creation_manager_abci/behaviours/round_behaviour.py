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

"""This module contains the MarketCreationManagerRoundBehaviour of the 'market_creation_manager_abci' skill."""

from typing import Set, Type

from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.answer_questions import (
    AnswerQuestionsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets import (
    ApproveMarketsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.collect_proposed_markets import (
    CollectProposedMarketsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.collect_randomness import (
    CollectRandomnessBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.deposit_dai import (
    DepositDaiBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.get_pending_questions import (
    GetPendingQuestionsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.post_transaction import (
    PostTransactionBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.prepare_transaction import (
    PrepareTransactionBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.redeem_bond import (
    RedeemBondBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.remove_funding import (
    RemoveFundingBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.retrieve_approved_market import (
    RetrieveApprovedMarketBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.select_keeper import (
    SelectKeeperMarketProposalBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.sync_markets import (
    SyncMarketsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    MarketCreationManagerAbciApp,
)


class MarketCreationManagerRoundBehaviour(AbstractRoundBehaviour):
    """MarketCreationManagerRoundBehaviour"""

    initial_behaviour_cls = CollectRandomnessBehaviour
    abci_app_cls = MarketCreationManagerAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = {
        CollectRandomnessBehaviour,
        CollectProposedMarketsBehaviour,
        GetPendingQuestionsBehaviour,
        AnswerQuestionsBehaviour,
        ApproveMarketsBehaviour,
        SelectKeeperMarketProposalBehaviour,
        RetrieveApprovedMarketBehaviour,
        PrepareTransactionBehaviour,
        SyncMarketsBehaviour,
        RemoveFundingBehaviour,
        DepositDaiBehaviour,
        RedeemBondBehaviour,
        PostTransactionBehaviour,
    }
