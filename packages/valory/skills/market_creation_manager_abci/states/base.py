import json
from enum import Enum
from typing import Any, Dict, List, Optional, cast

from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
    MechMetadata,
)
from packages.valory.skills.transaction_settlement_abci.rounds import (
    SynchronizedData as TxSynchronizedData,
)


class Event(Enum):
    NO_MAJORITY = "no_majority"
    DONE = "done"
    NONE = "none"
    NO_TX = "no_tx"
    ROUND_TIMEOUT = "round_timeout"
    MARKET_PROPOSAL_ROUND_TIMEOUT = "market_proposal_round_timeout"
    ERROR = "api_error"
    DID_NOT_SEND = "did_not_send"
    MAX_PROPOSED_MARKETS_REACHED = "max_markets_reached"
    MAX_APPROVED_MARKETS_REACHED = "max_approved_markets_reached"
    MAX_RETRIES_REACHED = "max_retries_reached"
    MECH_REQUEST_DONE = "mech_request_done"
    NO_MARKETS_RETRIEVED = "no_markets_retrieved"
    REDEEM_BOND_DONE = "redeem_bond_done"
    DEPOSIT_DAI_DONE = "deposit_dai_done"
    ANSWER_QUESTION_DONE = "answer_question_done"
    REMOVE_FUNDING_DONE = "remove_funding_done"
    SKIP_MARKET_PROPOSAL = "skip_market_proposal"
    SKIP_MARKET_APPROVAL = "skip_market_approval"


DEFAULT_PROPOSED_MARKETS_DATA = {"proposed_markets": [], "timestamp": 0}
DEFAULT_COLLECTED_PROPOSED_MARKETS_DATA = json.dumps(
    {
        "proposed_markets": [],
        "fixedProductMarketMakers": [],
        "num_markets_to_approve": 0,
        "timestamp": 0,
    }
)


class SynchronizedData(TxSynchronizedData):
    # ...existing code for SynchronizedData class...
    pass