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

"""This module contains the shared state for the abci skill of MarketCreationManagerAbciApp."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Type
from hexbytes import HexBytes

from aea.skills.base import SkillContext

from packages.valory.skills.abstract_round_abci.base import AbciApp
from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    MarketCreationManagerAbciApp,
)
from packages.valory.contracts.multisend.contract import MultiSendOperation


@dataclass
class MultisendBatch:
    """A structure representing a single transaction of a multisend."""

    to: str
    data: HexBytes
    value: int = 0
    operation: MultiSendOperation = MultiSendOperation.CALL


@dataclass
class RedeemingProgress:
    """A structure to keep track of the redeeming check progress."""

    trades: Set[Trade] = field(default_factory=lambda: set())
    utilized_tools: Dict[str, int] = field(default_factory=lambda: {})
    policy: Optional[EGreedyPolicy] = None
    claimable_amounts: Dict[HexBytes, int] = field(default_factory=lambda: {})
    earliest_block_number: int = 0
    event_filtering_batch_size: int = 0
    check_started: bool = False
    check_from_block: BlockIdentifier = "earliest"
    check_to_block: BlockIdentifier = "latest"
    cleaned: bool = False
    payouts: Dict[str, int] = field(default_factory=lambda: {})
    unredeemed_trades: Dict[str, int] = field(default_factory=lambda: {})
    claim_started: bool = False
    claim_from_block: BlockIdentifier = "earliest"
    claim_to_block: BlockIdentifier = "latest"
    answered: list = field(default_factory=lambda: [])
    claiming_condition_ids: List[str] = field(default_factory=lambda: [])
    claimed_condition_ids: List[str] = field(default_factory=lambda: [])

    @property
    def check_finished(self) -> bool:
        """Whether the check has finished."""
        return self.check_started and self.check_from_block == self.check_to_block

    @property
    def claim_finished(self) -> bool:
        """Whether the claiming has finished."""
        return self.claim_started and self.claim_from_block == self.claim_to_block

    @property
    def claim_params(self) -> Optional[ClaimParamsType]:
        """The claim parameters, prepared for the `claimWinnings` call."""
        history_hashes = []
        addresses = []
        bonds = []
        answers = []
        try:
            for i, answer in enumerate(reversed(self.answered)):
                # history_hashes second-last-to-first, the hash of each history entry, calculated as described here:
                # https://realitio.github.io/docs/html/contract_explanation.html#answer-history-entries.
                if i == len(self.answered) - 1:
                    history_hashes.append(ZERO_BYTES)
                else:
                    history_hashes.append(self.answered[i + 1]["args"]["history_hash"])

                # last-to-first, the address of each answerer or commitment sender
                addresses.append(answer["args"]["user"])
                # last-to-first, the bond supplied with each answer or commitment
                bonds.append(answer["args"]["bond"])
                # last-to-first, each answer supplied, or commitment ID if the answer was supplied with commit->reveal
                answers.append(answer["args"]["answer"])
        except KeyError:
            return None

        return history_hashes, addresses, bonds, answers


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls: Type[AbciApp] = MarketCreationManagerAbciApp

    def __init__(self, *args: Any, skill_context: SkillContext, **kwargs: Any) -> None:
        """Initialize the shared state object."""
        self.questions_requested_mech: Dict[str, Any] = {}
        self.questions_responded: Set[str] = set()
        self.redeeming_progress: RedeemingProgress = RedeemingProgress()
        super().__init__(*args, skill_context=skill_context, **kwargs)


class MarketCreationManagerParams(BaseParams):
    """Parameters."""

    # These parameters are from other ABCI skills, and are added
    # here to avoid subclassing and avoid MyPy linter issues.
    multisend_address: str
    multisend_batch_size: int

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""

        self.market_approval_server_url = self._ensure(
            key="market_approval_server_url", kwargs=kwargs, type_=str
        )
        self.market_approval_server_api_key = self._ensure(
            key="market_approval_server_api_key", kwargs=kwargs, type_=str
        )
        self.newsapi_api_key = self._ensure(
            key="newsapi_api_key", kwargs=kwargs, type_=str
        )
        self.newsapi_endpoint = self._ensure(
            key="newsapi_endpoint", kwargs=kwargs, type_=str
        )
        self.market_identification_prompt = self._ensure(
            key="market_identification_prompt", kwargs=kwargs, type_=str
        )
        self.topics = self._ensure(key="topics", kwargs=kwargs, type_=List[str])
        self.news_sources = self._ensure(
            key="news_sources", kwargs=kwargs, type_=List[str]
        )
        self.max_proposed_markets = self._ensure(
            "max_proposed_markets", kwargs, type_=int
        )
        self.max_approved_markets = self._ensure(
            "max_approved_markets", kwargs, type_=int
        )
        self.markets_to_approve_per_day = self._ensure(
            "markets_to_approve_per_day", kwargs, type_=int
        )
        self.markets_to_approve_per_epoch = self._ensure(
            "markets_to_approve_per_epoch", kwargs, type_=int
        )
        self.questions_to_close_batch_size = self._ensure(
            "questions_to_close_batch_size", kwargs, type_=int
        )
        self.close_question_bond = self._ensure(
            "close_question_bond", kwargs, type_=int
        )
        self.min_approve_markets_epoch_seconds = self._ensure(
            "min_approve_markets_epoch_seconds", kwargs, type_=int
        )
        self.approve_market_event_days_offset = self._ensure(
            "approve_market_event_days_offset", kwargs, type_=int
        )
        self.approve_market_creator = self._ensure(
            key="approve_market_creator",
            kwargs=kwargs,
            type_=str,
        )
        self.realitio_contract = self._ensure(
            key="realitio_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.realitio_oracle_proxy_contract = self._ensure(
            key="realitio_oracle_proxy_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.conditional_tokens_contract = self._ensure(
            key="conditional_tokens_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.fpmm_deterministic_factory_contract = self._ensure(
            key="fpmm_deterministic_factory_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.collateral_tokens_contract = self._ensure(
            key="collateral_tokens_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.arbitrator_contract = self._ensure(
            key="arbitrator_contract",
            kwargs=kwargs,
            type_=str,
        )
        self.market_fee = self._ensure("market_fee", kwargs, type_=float)
        self.market_timeout = self._ensure("market_timeout", kwargs, type_=int)
        self.event_offset_start_days = self._ensure(
            "event_offset_start_days", kwargs, type_=int
        )
        self.event_offset_end_days = self._ensure(
            "event_offset_end_days", kwargs, type_=int
        )
        self.min_market_proposal_interval_seconds = self._ensure(
            "min_market_proposal_interval_seconds", kwargs, type_=int
        )
        self.market_proposal_round_timeout_seconds_per_day = self._ensure(
            "market_proposal_round_timeout_seconds_per_day", kwargs, type_=int
        )
        self.market_closing_newsapi_api_key = self._ensure(
            "market_closing_newsapi_api_key", kwargs, type_=str
        )
        self.google_api_key = self._ensure("google_api_key", kwargs, type_=str)
        self.google_engine_id = self._ensure("google_engine_id", kwargs, type_=str)
        self.openai_api_key = self._ensure("openai_api_key", kwargs, type_=str)
        self.initial_funds = self._ensure("initial_funds", kwargs, type_=float)
        self.xdai_threshold = self._ensure("xdai_threshold", kwargs, type_=int)

        self.use_subgraph_for_redeeming = self._ensure("use_subgraph_for_redeeming", kwargs, type_=bool)
        self.contract_timeout = self._ensure("contract_timeout", kwargs, type_=float)
        self.max_filtering_retries = self._ensure("max_filtering_retries", kwargs, type_=int)
        self.reduce_factor = self._ensure("reduce_factor", kwargs, type_=float)
        self.redeeming_batch_size = self._ensure("redeeming_batch_size", kwargs, type_=int)
        self.dust_threshold = self._ensure("dust_threshold", kwargs, type_=int)
        self.minimum_batch_size = self._ensure("minimum_batch_size", kwargs, type_=int)

        # TODO These variables are re-defined with names compatible with trader service
        self.conditional_tokens_address = self.conditional_tokens_contract
        self.realitio_address = self.realitio_contract
        self.realitio_proxy_address = self.realitio_oracle_proxy_contract

        super().__init__(*args, **kwargs)


class RandomnessApi(ApiSpecs):
    """A model for randomness api specifications."""


class OmenSubgraph(ApiSpecs):
    """A model that wraps ApiSpecs for the OMEN's subgraph specifications."""


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool
