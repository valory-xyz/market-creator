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

"""This module contains the transaction payloads of the MarketCreationManagerAbciApp."""

from dataclasses import dataclass

from packages.valory.skills.abstract_round_abci.base import BaseTxPayload


@dataclass(frozen=True)
class CollectRandomnessPayload(BaseTxPayload):
    """Represent a transaction payload for the CollectRandomnessRound."""

    round_id: int
    randomness: str


@dataclass(frozen=True)
class DataGatheringPayload(BaseTxPayload):
    """Represent a transaction payload for the DataGatheringRound."""

    gathered_data: str


@dataclass(frozen=True)
class SelectKeeperPayload(BaseTxPayload):
    """Represent a transaction payload of type 'select_keeper'."""

    keeper: str


@dataclass(frozen=True)
class MarketProposalPayload(BaseTxPayload):
    """Represent a transaction payload for the MarketProposalRound."""

    content: str


@dataclass(frozen=True)
class RetrieveApprovedMarketPayload(BaseTxPayload):
    """Represent a transaction payload for the RetrieveApprovedMarketRound."""

    content: str


@dataclass(frozen=True)
class PrepareTransactionPayload(BaseTxPayload):
    """Represent a transaction payload for the PrepareTransactionRound."""

    content: str


@dataclass(frozen=True)
class SyncMarketsPayload(BaseTxPayload):
    """Represent a transaction payload for the PrepareTransactionRound."""

    content: str


@dataclass(frozen=True)
class RemoveFundingPayload(BaseTxPayload):
    """Represent a transaction payload for the PrepareTransactionRound."""

    content: str


@dataclass(frozen=True)
class DepositDaiPayload(BaseTxPayload):
    """Represent a transaction payload for the PrepareTransactionRound."""

    content: str


@dataclass(frozen=True)
class PostTxPayload(BaseTxPayload):
    """Represent a transaction payload for the PrepareTransactionRound."""

    content: str


@dataclass(frozen=True)
class CollectProposedMarketsPayload(BaseTxPayload):
    """Represent a transaction payload for the CollectProposedMarketsRound."""

    content: str


@dataclass(frozen=True)
class ApproveMarketsPayload(BaseTxPayload):
    """Represent a transaction payload for the ApproveMarketsRound."""

    content: str
    approved_markets_count: int


@dataclass(frozen=True)
class CloseMarketsPayload(BaseTxPayload):
    """Represent a transaction payload for the ApproveMarketsRound."""

    content: str
