from packages.valory.skills.market_creation_manager_abci.payloads import SelectKeeperPayload
from packages.valory.skills.abstract_round_abci.base import CollectSameUntilThresholdRound
from packages.valory.skills.market_creation_manager_abci.states.base import Event, SynchronizedData
from packages.valory.skills.abstract_round_abci.base import get_name


class SelectKeeperRound(CollectSameUntilThresholdRound):
    payload_class = SelectKeeperPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_selection)
    selection_key = get_name(SynchronizedData.most_voted_keeper_address)