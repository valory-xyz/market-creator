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

"""Tests for verify_state_is_resolvable in propose_questions.py."""

import json
import sys
from unittest.mock import MagicMock, patch

from packages.valory.skills.market_creation_manager_abci.propose_questions import (
    verify_state_is_resolvable,
)

_MODULE = "packages.valory.skills." "market_creation_manager_abci.propose_questions"


class TestVerifyStateIsResolvable:
    """Tests for verify_state_is_resolvable."""

    def test_empty_query_keeps(self) -> None:
        """Empty source+metric should fail open."""
        ok, reason = verify_state_is_resolvable("key", "", "")
        assert ok is True
        assert reason == "empty_query"

    @patch(f"{_MODULE}.requests.post")
    def test_serper_non_200_fails_open(self, mock_post: MagicMock) -> None:
        """Non-200 Serper response should fail open."""
        mock_post.return_value.status_code = 500
        ok, reason = verify_state_is_resolvable("key", "CDC", "volunteers")
        assert ok is True
        assert "fail_open_serper_status_500" in reason

    @patch(f"{_MODULE}.requests.post")
    def test_serper_request_exception_fails_open(self, mock_post: MagicMock) -> None:
        """Serper network error should fail open."""
        import requests

        mock_post.side_effect = requests.RequestException("timeout")
        ok, reason = verify_state_is_resolvable("key", "CDC", "volunteers")
        assert ok is True
        assert reason == "fail_open_serper_error"

    @patch(f"{_MODULE}.requests.post")
    def test_serper_no_organic_key_fails_open(self, mock_post: MagicMock) -> None:
        """Serper 200 with no organic key should fail open."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"searchParameters": {}}
        ok, reason = verify_state_is_resolvable("key", "Freddie Mac", "rate")
        assert ok is True
        assert reason == "fail_open_serper_unexpected_shape"

    @patch(f"{_MODULE}.requests.post")
    def test_serper_empty_organic_drops(self, mock_post: MagicMock) -> None:
        """Serper 200 with empty organic list should drop."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"organic": []}
        ok, reason = verify_state_is_resolvable("key", "fictional corp", "metric")
        assert ok is False
        assert reason == "no_hits"

    @patch(f"{_MODULE}.client", None)
    @patch(f"{_MODULE}.requests.post")
    def test_no_client_fails_open(self, mock_post: MagicMock) -> None:
        """No OpenAI client available should fail open."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "organic": [{"title": "hit", "snippet": "data"}]
        }
        ok, reason = verify_state_is_resolvable("key", "Freddie Mac", "rate")
        assert ok is True
        assert reason == "fail_open_no_client"

    @patch(f"{_MODULE}.client")
    @patch(f"{_MODULE}.requests.post")
    def test_judge_says_yes_keeps(
        self, mock_post: MagicMock, mock_client: MagicMock
    ) -> None:
        """Judge returning YES should keep the state."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "organic": [{"title": "PMMS", "snippet": "6.5%"}]
        }
        body = {"answer": "YES", "reason": "publishes weekly"}
        choice = MagicMock()
        choice.message.content = json.dumps(body)
        mock_client.chat.completions.create.return_value.choices = [choice]
        ok, reason = verify_state_is_resolvable("key", "Freddie Mac", "mortgage rate")
        assert ok is True
        assert "publishes weekly" in reason

    @patch(f"{_MODULE}.client")
    @patch(f"{_MODULE}.requests.post")
    def test_judge_says_no_drops(
        self, mock_post: MagicMock, mock_client: MagicMock
    ) -> None:
        """Judge returning NO should drop the state."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "organic": [{"title": "tangential", "snippet": "x"}]
        }
        body = {"answer": "NO", "reason": "not published"}
        choice = MagicMock()
        choice.message.content = json.dumps(body)
        mock_client.chat.completions.create.return_value.choices = [choice]
        ok, reason = verify_state_is_resolvable("key", "Tesla", "repair records")
        assert ok is False
        assert "not published" in reason

    @patch(f"{_MODULE}.client")
    @patch(f"{_MODULE}.requests.post")
    def test_judge_null_reason_no_crash(
        self, mock_post: MagicMock, mock_client: MagicMock
    ) -> None:
        """Judge null reason should not crash."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "organic": [{"title": "hit", "snippet": "d"}]
        }
        body = {"answer": "YES", "reason": None}
        choice = MagicMock()
        choice.message.content = json.dumps(body)
        mock_client.chat.completions.create.return_value.choices = [choice]
        ok, reason = verify_state_is_resolvable("key", "Freddie Mac", "rate")
        assert ok is True
        assert isinstance(reason, str)

    @patch(f"{_MODULE}.client")
    @patch(f"{_MODULE}.requests.post")
    def test_judge_llm_error_fails_open(
        self, mock_post: MagicMock, mock_client: MagicMock
    ) -> None:
        """Judge LLM error should fail open."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "organic": [{"title": "hit", "snippet": "d"}]
        }
        mock_client.chat.completions.create.side_effect = sys.modules[
            "openai"
        ].OpenAIError("API down")
        ok, reason = verify_state_is_resolvable("key", "Freddie Mac", "rate")
        assert ok is True
        assert reason == "fail_open_llm_error"

    @patch(f"{_MODULE}.client")
    @patch(f"{_MODULE}.requests.post")
    def test_cache_hit_skips_serper_and_llm(
        self, mock_post: MagicMock, mock_client: MagicMock
    ) -> None:
        """Second call with same (source, metric) should hit cache; not re-issue Serper / LLM."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "organic": [{"title": "PMMS", "snippet": "6.5%"}]
        }
        body = {"answer": "YES", "reason": "publishes weekly"}
        choice = MagicMock()
        choice.message.content = json.dumps(body)
        mock_client.chat.completions.create.return_value.choices = [choice]
        ok1, reason1 = verify_state_is_resolvable("k", "Freddie Mac", "mortgage rate")
        ok2, reason2 = verify_state_is_resolvable("k", "Freddie Mac", "mortgage rate")
        assert ok1 is True and ok2 is True
        assert "[cached]" in reason2
        # Cache hit must NOT re-issue Serper or LLM call
        assert mock_post.call_count == 1
        assert mock_client.chat.completions.create.call_count == 1

    @patch(f"{_MODULE}.client")
    @patch(f"{_MODULE}.requests.post")
    def test_fail_open_not_cached(
        self, mock_post: MagicMock, mock_client: MagicMock
    ) -> None:
        """Fail-open paths (transient errors) must NOT be cached."""
        import requests as _requests

        mock_post.side_effect = _requests.RequestException("timeout")
        ok1, reason1 = verify_state_is_resolvable("k", "Freddie Mac", "rate")
        # Second call should re-issue (not cached)
        ok2, reason2 = verify_state_is_resolvable("k", "Freddie Mac", "rate")
        assert ok1 is True and ok2 is True
        assert reason1 == "fail_open_serper_error"
        assert reason2 == "fail_open_serper_error"
        assert "[cached]" not in reason2
        assert mock_post.call_count == 2
