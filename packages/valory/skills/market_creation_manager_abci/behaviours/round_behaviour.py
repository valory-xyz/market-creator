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

"""This package contains round behaviours of MarketCreationManagerAbciApp."""

import json
import random
import time
from abc import ABC
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from string import Template
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    cast,
)

import packages.valory.skills.market_creation_manager_abci.propose_questions as mech_tool_propose_questions
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
from packages.valory.contracts.conditional_tokens.contract import (
    ConditionalTokensContract,
)
from packages.valory.contracts.fpmm.contract import FPMMContract
from packages.valory.contracts.fpmm_deterministic_factory.contract import (
    FPMMDeterministicFactory,
)
from packages.valory.contracts.gnosis_safe.contract import (
    GnosisSafeContract,
    SafeOperation,
)
from packages.valory.contracts.multisend.contract import (
    MultiSendContract,
    MultiSendOperation,
)
from packages.valory.contracts.realitio.contract import RealitioContract
from packages.valory.contracts.wxdai.contract import WxDAIContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.protocols.llm.message import LlmMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.common import (
    RandomnessBehaviour,
    SelectKeeperBehaviour,
)
from packages.valory.skills.abstract_round_abci.models import Requests
from packages.valory.skills.market_creation_manager_abci import (
    PUBLIC_ID as MARKET_CREATION_MANAGER_PUBLIC_ID,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.base import (
    CollectRandomnessBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.collect_proposed_markets import (
    CollectProposedMarketsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.dialogues import LlmDialogue
from packages.valory.skills.market_creation_manager_abci.models import (
    MarketCreationManagerParams,
    SharedState,
)
from packages.valory.skills.market_creation_manager_abci.payloads import (
    AnswerQuestionsPayload,
    ApproveMarketsPayload,
    CollectProposedMarketsPayload,
    DepositDaiPayload,
    GetPendingQuestionsPayload,
    PostTxPayload,
    RedeemBondPayload,
    RemoveFundingPayload,
    SyncMarketsPayload,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    AnswerQuestionsRound,
    ApproveMarketsRound,
    CollectProposedMarketsRound,
    CollectRandomnessPayload,
    CollectRandomnessRound,
    DepositDaiRound,
    GetPendingQuestionsRound,
    MarketCreationManagerAbciApp,
    PostTransactionRound,
    PrepareTransactionPayload,
    PrepareTransactionRound,
    RedeemBondRound,
    RemoveFundingRound,
    RetrieveApprovedMarketPayload,
    RetrieveApprovedMarketRound,
    SelectKeeperPayload,
    SelectKeeperRound,
    SyncMarketsRound,
    SynchronizedData,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
    MechMetadata,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
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
