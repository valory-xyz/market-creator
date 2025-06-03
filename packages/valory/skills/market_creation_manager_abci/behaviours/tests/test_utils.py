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

from typing import Generator
from unittest import mock
from unittest.mock import patch
import pytest
from packages.valory.skills.market_creation_manager_abci.behaviours.utils import hacky_retry


@pytest.fixture
def mock_sleep():
    with patch('time.sleep') as _mock:
        yield _mock


def test_hacky_retry(mock_sleep):
    i = 0

    @hacky_retry
    def some_func() -> Generator[int, None, None]:
        nonlocal i
        if i == 0:
            i += 1
            print(f"i: {i}")
            raise ValueError("test")
        else:
            i += 1
            yield i

    assert next(some_func()) == 2  # 1st call raises ValueError, 2nd call returns 2
    mock_sleep.assert_called_once_with(1.0)


def test_hacky_retry_with_connection_error(mock_sleep):
    i = 0

    @hacky_retry
    def some_func() -> Generator[int, None, None]:
        nonlocal i
        if i == 0:
            i += 1
            raise ConnectionError("test")
        else:
            i += 1
            yield i
    
    assert next(some_func()) == 2  # 1st call raises ConnectionError, 2nd call returns 2
    mock_sleep.assert_called_once_with(1.0)


def test_hacky_retry_with_unexpected_error(mock_sleep):
    i = 0
    @hacky_retry
    def some_func() -> Generator[int, None, None]:
        nonlocal i
        if i == 0:
            i += 1
            raise Exception("test")
        else:
            i += 1
            yield i
    
    assert next(some_func()) is None  # 1st call raises Exception, 2nd call returns 2
    mock_sleep.assert_not_called()


def test_hacky_retry_with_no_retries(mock_sleep):
    i = 0

    @hacky_retry
    def some_func() -> Generator[int, None, None]:
        nonlocal i
        i += 1
        yield i

    assert next(some_func()) == 1  # 1st call returns 1
    mock_sleep.assert_not_called()


def test_hacky_max_retries_return_none(mock_sleep):
    @hacky_retry
    def some_func() -> Generator[int, None, None]:
        raise ValueError("test")

    assert next(some_func()) is None
    assert mock_sleep.call_count == 2  # Called with 1.0 and 2.0 seconds
    mock_sleep.assert_has_calls([mock.call(1.0), mock.call(2.0)])