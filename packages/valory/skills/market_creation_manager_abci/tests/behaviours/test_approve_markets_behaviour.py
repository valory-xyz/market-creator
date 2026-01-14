# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2025 Valory AG
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

"""This module contains the tests for valory/decision_maker_abci's base behaviour."""

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from packages.valory.skills.abstract_round_abci.test_tools.base import (
    FSMBehaviourBaseCase,
)
from packages.valory.skills.market_creation_manager_abci.behaviours.approve_markets import (
    ApproveMarketsBehaviour,
)


CURRENT_FILE_PATH = Path(__file__).resolve()
PACKAGE_DIR = CURRENT_FILE_PATH.parents[2]


class TestApproveMarketsBehaviour(FSMBehaviourBaseCase):
    """Test `ApproveMarketsBehaviour`."""

    behaviour: ApproveMarketsBehaviour  # type: ignore
    path_to_skill = PACKAGE_DIR
    _skill = MagicMock()

    def setup(self, **kwargs: Any) -> None:
        """Setup."""
        self.round_sequence_mock = MagicMock()
        context_mock = MagicMock(params=MagicMock())
        context_mock.state.round_sequence = self.round_sequence_mock
        context_mock.handlers = MagicMock()
        self.benchmark_dir = MagicMock()
        self.behaviour = ApproveMarketsBehaviour(
            name="ApproveMarketsBehaviour", skill_context=context_mock
        )

    @pytest.mark.parametrize(
        "market, expected_result",
        (
            (
                {
                    "question": "Will James Walkinshaw be sworn in as the U.S. Representative for Virginia's 11th congressional district on or before September 30, 2024?",
                    "resolution_time": 1757894400,
                },
                False,
            ),
            (
                {
                    "question": "Will President Emmanuel Macron publicly announce the appointment of a new French prime minister on or before October 31, 2024?",
                    "resolution_time": 1757808000,
                },
                False,
            ),
            (
                {
                    "question": "Will the Liberal Democratic Party of Japan publicly announce, on or before October 15, 2024, the date of its presidential (party leader) election to select a successor to Shigeru Ishiba?",
                    "resolution_time": 1757635200,
                },
                False,
            ),
            (
                {
                    "question": "Will NASA publicly confirm, on or before September 8, 2024, that the total lunar eclipse on September 7-8, 2024, reached totality as predicted?",
                    "resolution_time": 1757548800,
                },
                False,
            ),
            (
                {
                    "question": "Will a single ticket win the entire Powerball jackpot in the drawing held on Saturday, September 5, 2025?",
                    "resolution_time": 1757030400,
                },
                True,
            ),
            (
                {
                    "question": "Will a single ticket win the entire Powerball jackpot in the drawing held on Saturday, September 05, 2025?",
                    "resolution_time": 1757030400,
                },
                True,
            ),
            (
                {
                    "question": "Will a single ticket win the entire Powerball jackpot in the drawing",
                    "resolution_time": 1757030400,
                },
                False,
            ),
        ),
    )
    def test__is_resolution_date_in_question(
        self,
        market: Dict,
        expected_result: bool,
    ) -> None:
        """Test the `_is_resolution_date_in_question` method."""
        behaviour = self.behaviour

        assert (
            behaviour._is_resolution_date_in_question(market=market) == expected_result
        )
