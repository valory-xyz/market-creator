# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2026 Valory AG
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

"""This module contains the handler for the 'price_estimation_abci' skill."""

import json
import re
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import urlparse

from aea.protocols.base import Message

from packages.valory.connections.http_server.connection import (
    PUBLIC_ID as HTTP_SERVER_PUBLIC_ID,
)
from packages.valory.protocols.http import HttpMessage
from packages.valory.skills.abstract_round_abci.handlers import (
    ABCIRoundHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    ContractApiHandler as BaseContractApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    HttpHandler as BaseHttpHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    IpfsHandler as BaseIpfsHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    LedgerApiHandler as BaseLedgerApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    SigningHandler as BaseSigningHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    TendermintHandler as BaseTendermintHandler,
)
from packages.valory.skills.market_creation_manager_abci.dialogues import (
    HttpDialogue,
    HttpDialogues,
)
from packages.valory.skills.market_creation_manager_abci.rounds import SynchronizedData
from packages.valory.skills.market_maker_abci.models import SharedState

MarketCreatorABCIRoundHandler = ABCIRoundHandler
SigningHandler = BaseSigningHandler
LedgerApiHandler = BaseLedgerApiHandler
ContractApiHandler = BaseContractApiHandler
TendermintHandler = BaseTendermintHandler
IpfsHandler = BaseIpfsHandler

# Health thresholds (mirrored from the mech service for cross-service parity).
LIVENESS_STALL_FACTOR = 3.0  # > 3x the expected pause means the FSM is "stuck"
TRANSITION_TOLERANCE_FACTOR = 2.0  # < 2x the expected pause means "transitioning fast"
DEFAULT_GRACE = 120.0  # readiness/progress grace floor, kept for mech parity
HEALTH_VERSION = 2


class HttpCode(Enum):
    """Http codes"""

    OK_CODE = 200
    NOT_FOUND_CODE = 404
    BAD_REQUEST_CODE = 400
    NOT_READY = 503


class HttpMethod(Enum):
    """Http methods"""

    GET = "get"
    HEAD = "head"
    POST = "post"


class HttpHandler(BaseHttpHandler):
    """This implements the HTTP handler."""

    SUPPORTED_PROTOCOL = HttpMessage.protocol_id

    def setup(self) -> None:
        """Implement the setup."""

        # Custom hostname (set via params)
        service_endpoint_base = urlparse(
            self.context.params.service_endpoint_base
        ).hostname

        # Propel hostname regex
        propel_uri_base_hostname = (
            r"https?:\/\/[a-zA-Z0-9]{16}.agent\.propel\.(staging\.)?autonolas\.tech"
        )

        # Route regexes
        hostname_regex = rf".*({service_endpoint_base}|{propel_uri_base_hostname}|localhost|127.0.0.1|0.0.0.0)(:\d+)?"
        self.handler_url_regex = rf"{hostname_regex}\/.*"
        health_url_regex = rf"{hostname_regex}\/healthcheck"

        # Routes
        self.routes = {
            (HttpMethod.POST.value,): [],
            (HttpMethod.GET.value, HttpMethod.HEAD.value): [
                (health_url_regex, self._handle_get_health),
            ],
        }

        self.json_content_header = "Content-Type: application/json\n"

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return SynchronizedData(
            db=self.context.state.round_sequence.latest_synchronized_data.db
        )

    def _get_handler(self, url: str, method: str) -> Tuple[Optional[Callable], Dict]:
        """Check if an url is meant to be handled in this handler

        We expect url to match the pattern {hostname}/.*,
        where hostname is allowed to be localhost, 127.0.0.1 or the token_uri_base's hostname.
        Examples:
            localhost:8000/0
            127.0.0.1:8000/100
            https://pfp.staging.autonolas.tech/45
            http://pfp.staging.autonolas.tech/120

        :param url: the url to check
        :param method: the http method
        :returns: the handling method if the message is intended to be handled by this handler, None otherwise, and the regex captures
        """
        # Check base url
        if not re.match(self.handler_url_regex, url):
            self.context.logger.info(
                f"The url {url} does not match the HttpHandler's pattern"
            )
            return None, {}

        # Check if there is a route for this request
        for methods, routes in self.routes.items():
            if method not in methods:
                continue

            for route in routes:  # type: ignore
                # Routes are tuples like (route_regex, handle_method)
                m = re.match(route[0], url)
                if m:
                    return route[1], m.groupdict()

        # No route found
        self.context.logger.info(
            f"The message [{method}] {url} is intended for the HttpHandler but did not match any valid pattern"
        )
        return self._handle_bad_request, {}

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to an envelope.

        :param message: the message
        """
        http_msg = cast(HttpMessage, message)

        # Check if this is a request sent from the http_server skill
        if (
            http_msg.performative != HttpMessage.Performative.REQUEST
            or message.sender != str(HTTP_SERVER_PUBLIC_ID.without_hash())
        ):
            super().handle(message)
            return

        # Check if this message is for this skill. If not, send to super()
        handler, kwargs = self._get_handler(http_msg.url, http_msg.method)
        if not handler:
            super().handle(message)
            return

        # Retrieve dialogues
        http_dialogues = cast(HttpDialogues, self.context.http_dialogues)
        http_dialogue = cast(HttpDialogue, http_dialogues.update(http_msg))

        # Invalid message
        if http_dialogue is None:
            self.context.logger.info(
                "Received invalid http message={}, unidentified dialogue.".format(
                    http_msg
                )
            )
            return

        # Handle message
        self.context.logger.info(
            "Received http request with method={}, url={} and body={!r}".format(
                http_msg.method,
                http_msg.url,
                http_msg.body,
            )
        )
        handler(http_msg, http_dialogue, **kwargs)

    def _handle_bad_request(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """
        Handle a Http bad request.

        :param http_msg: the http message
        :param http_dialogue: the http dialogue
        """
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=HttpCode.BAD_REQUEST_CODE.value,
            status_text="Bad request",
            headers=http_msg.headers,
            body=b"",
        )

        # Send response
        self.context.logger.info("Responding with: {}".format(http_response))
        self.context.outbox.put_message(message=http_response)

    def _send_ok_response(
        self,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
        data: Union[Dict, List],
    ) -> None:
        """Send an OK response with the provided data"""
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=HttpCode.OK_CODE.value,
            status_text="Success",
            headers=f"{self.json_content_header}{http_msg.headers}",
            body=json.dumps(data).encode("utf-8"),
        )

        # Send response
        self.context.logger.info("Responding with: {}".format(http_response))
        self.context.outbox.put_message(message=http_response)

    def _handle_get_health(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """
        Handle GET /healthcheck and compute the agent's health metrics.

        The health is assessed across three dimensions (mech-service parity):

        - **Liveness**: whether the FSM is actively transitioning and Tendermint
          is not in a stalled state. This is the dimension that catches a frozen
          FSM: a missing last-transition timestamp is reported as not-live
          (reason ``no-fsm-data``) instead of being silently treated as healthy.
        - **Readiness**: whether the agent can accept new work.
        - **Progress**: whether the agent is advancing through its backlog.

        market-creator is an FSM-only service with no task backlog or dependency
        read metric (unlike mech), so readiness and progress are always-ok
        placeholders (reason ``idle-ok``) kept for shape parity with mech.

        The endpoint always responds with HTTP 200; a wedge is signalled solely
        via ``is_healthy: false`` in the JSON body.

        :param http_msg: the http message
        :param http_dialogue: the http dialogue
        """
        seconds_since_last_transition: Optional[float] = None
        is_tm_unhealthy: Optional[bool] = None
        is_transitioning_fast: Optional[bool] = None
        current_round: Optional[str] = None
        rounds: Optional[List[str]] = None

        round_sequence = cast(SharedState, self.context.state).round_sequence
        reset_pause = float(self.context.params.reset_pause_duration)

        # Guard A: FSM liveness data is only available once we have transitioned.
        if round_sequence._last_round_transition_timestamp:
            is_tm_unhealthy = cast(
                SharedState, self.context.state
            ).round_sequence.block_stall_deadline_expired

            current_time = datetime.now().timestamp()
            seconds_since_last_transition = current_time - datetime.timestamp(
                round_sequence._last_round_transition_timestamp
            )

            is_transitioning_fast = (not is_tm_unhealthy) and (
                seconds_since_last_transition
                < TRANSITION_TOLERANCE_FACTOR * reset_pause
            )

        # Guard B: round identifiers for observability.
        if round_sequence._abci_app:
            current_round = round_sequence._abci_app.current_round.round_id
            rounds = [
                r.round_id for r in round_sequence._abci_app._previous_rounds[-25:]
            ]
            rounds.append(current_round)

        # Liveness: catches the wedge. No FSM data or unknown tm state -> not live.
        if seconds_since_last_transition is None or is_tm_unhealthy is None:
            liveness_ok, live_reason = False, "no-fsm-data"
        else:
            liveness_ok = (not is_tm_unhealthy) and (
                seconds_since_last_transition <= LIVENESS_STALL_FACTOR * reset_pause
            )
            live_reason = (
                "ok"
                if liveness_ok
                else ("tm-unhealthy" if is_tm_unhealthy else "stuck-no-transition")
            )

        # Readiness/progress: market-creator has no backlog metric, so these are
        # always-ok placeholders kept for mech parity.
        readiness_ok, ready_reason = True, "idle-ok"
        progress_ok, prog_reason = True, "idle-ok"

        is_healthy = bool(liveness_ok and readiness_ok and progress_ok)

        data = {
            "is_healthy": is_healthy,
            "liveness": {"ok": liveness_ok, "reason": live_reason},
            "readiness": {"ok": readiness_ok, "reason": ready_reason},
            "progress": {"ok": progress_ok, "reason": prog_reason},
            "seconds_since_last_transition": seconds_since_last_transition,
            # Three-state: True (healthy), False (unhealthy), None (unknown).
            "is_tm_healthy": (None if is_tm_unhealthy is None else not is_tm_unhealthy),
            "period": self.synchronized_data.period_count,
            "reset_pause_duration": reset_pause,
            "current_round": current_round,
            "rounds": rounds,
            "is_transitioning_fast": is_transitioning_fast,
            "health_version": HEALTH_VERSION,
        }

        self._send_ok_response(http_msg, http_dialogue, data)
