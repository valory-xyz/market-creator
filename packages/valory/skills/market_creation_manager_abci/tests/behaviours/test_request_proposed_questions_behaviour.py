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

"""Tests for RequestProposedQuestionsBehaviour (kept as a thin compatibility shim)."""

# The substantive tests for RequestProposedQuestionsBehaviour now live in
# test_approve_markets.py (same directory).  This file is retained so
# that any tooling that discovers tests by filename still finds something
# here, but it intentionally defers to the main test module.

from packages.valory.skills.market_creation_manager_abci.behaviours.request_proposed_questions import (
    RequestProposedQuestionsBehaviour,
)
from packages.valory.skills.market_creation_manager_abci.rounds import (
    RequestProposedQuestionsRound,
)


class TestRequestProposedQuestionsBehaviourShim:
    """Thin shim: ensures the behaviour class is importable and wired."""

    def test_matching_round(self) -> None:
        """Matching round must be RequestProposedQuestionsRound."""
        assert (
            RequestProposedQuestionsBehaviour.matching_round
            is RequestProposedQuestionsRound
        )
