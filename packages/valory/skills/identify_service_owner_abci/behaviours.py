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

"""This module contains the behaviours of the IdentifyServiceOwnerAbciApp."""

from abc import ABC
from typing import Generator, Optional, Set, Type, cast

from packages.valory.contracts.service_registry.contract import (
    ServiceRegistryContract,
)
from packages.valory.contracts.service_staking_token.contract import (
    ServiceStakingTokenContract,
)
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.identify_service_owner_abci.models import IdentifyServiceOwnerParams
from packages.valory.skills.identify_service_owner_abci.payloads import IdentifyServiceOwnerPayload
from packages.valory.skills.identify_service_owner_abci.rounds import (
    IdentifyServiceOwnerAbciApp,
    IdentifyServiceOwnerRound,
    SynchronizedData,
)


class IdentifyServiceOwnerBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the identify_service_owner_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> IdentifyServiceOwnerParams:
        """Return the params."""
        return cast(IdentifyServiceOwnerParams, super().params)


class IdentifyServiceOwnerBehaviour(IdentifyServiceOwnerBaseBehaviour):
    """Behaviour that resolves the real service owner, handling staking indirection."""

    matching_round = IdentifyServiceOwnerRound

    def async_act(self) -> Generator:
        """Resolve the service owner."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            service_owner = yield from self._resolve_service_owner()
            payload = IdentifyServiceOwnerPayload(
                sender=self.context.agent_address,
                service_owner=service_owner,
            )
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
        self.set_done()

    def _resolve_service_owner(self) -> Generator[None, None, Optional[str]]:
        """Resolve the real service owner, handling staking contract indirection."""
        service_id = self.params.on_chain_service_id
        registry_address = self.params.service_registry_address

        if service_id is None or registry_address is None:
            self.context.logger.warning(
                "on_chain_service_id or service_registry_address not configured. "
                "Skipping service owner resolution."
            )
            return None

        # Step 1: Get the registry owner (may be a staking contract)
        registry_owner = yield from self._get_registry_owner(
            service_id, registry_address
        )
        if registry_owner is None:
            return None

        # Step 2: Check if the registry owner is a staking contract
        is_staking = yield from self._is_staking_contract(
            registry_owner, service_id
        )

        if not is_staking:
            self.context.logger.info(
                f"Service {service_id} is not staked. "
                f"Owner: {registry_owner}"
            )
            return registry_owner

        # Step 3: Resolve real owner from staking contract
        real_owner = yield from self._get_owner_from_staking(
            registry_owner, service_id
        )
        if real_owner is None:
            self.context.logger.error(
                f"Service {service_id} is staked at {registry_owner} "
                f"but could not resolve real owner."
            )
            return None

        self.context.logger.info(
            f"Service {service_id} is staked at {registry_owner}. "
            f"Real owner: {real_owner}"
        )
        return real_owner

    def _get_registry_owner(
        self, service_id: int, registry_address: str
    ) -> Generator[None, None, Optional[str]]:
        """Get the service owner from the ServiceRegistry."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=registry_address,
            contract_id=str(ServiceRegistryContract.contract_id),
            contract_callable="get_service_owner",
            service_id=service_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get service owner from registry. "
                f"Expected {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None
        return cast(str, response.state.body["service_owner"])

    def _is_staking_contract(
        self, address: str, service_id: int
    ) -> Generator[None, None, bool]:
        """Check if an address is a staking contract by calling getStakingState."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=address,
            contract_id=str(ServiceStakingTokenContract.contract_id),
            contract_callable="get_service_staking_state",
            service_id=service_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            # Call failed — address is NOT a staking contract
            return False
        return True

    def _get_owner_from_staking(
        self, staking_address: str, service_id: int
    ) -> Generator[None, None, Optional[str]]:
        """Get the real service owner from the staking contract."""
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=staking_address,
            contract_id=str(ServiceStakingTokenContract.contract_id),
            contract_callable="get_service_info",
            service_id=service_id,
        )
        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get service info from staking contract. "
                f"Expected {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None
        # getServiceInfo returns ServiceInfo(multisig, owner, nonces[], ...)
        # owner is at index 1
        info = response.state.body["data"]
        return cast(str, info[1])


class IdentifyServiceOwnerRoundBehaviour(AbstractRoundBehaviour):
    """This behaviour manages the consensus stages for the identify_service_owner_abci skill."""

    initial_behaviour_cls = IdentifyServiceOwnerBehaviour
    abci_app_cls = IdentifyServiceOwnerAbciApp
    behaviours: Set[Type[BaseBehaviour]] = {
        IdentifyServiceOwnerBehaviour,  # type: ignore
    }
