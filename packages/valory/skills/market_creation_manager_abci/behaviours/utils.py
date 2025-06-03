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


import functools
import logging
from typing import Callable, Generator

from aea.configurations.base import PublicId

PUBLIC_ID = PublicId.from_str("valory/market_creation_manager_abci:0.1.0")

_logger = logging.getLogger(
    f"aea.packages.{PUBLIC_ID.author}.skills.{PUBLIC_ID.name}.behaviours.utils"
)


def hacky_retry(func: Callable, n_retries: int = 3) -> Callable:
    """Apply a retry strategy to a generator-based request function.

    Args:
        func: The input request function that returns a generator.
        n_retries: Maximum number of attempts (initial try + retries).
    Returns:
        The wrapped function with retry support.
    """
    @functools.wraps(func)
    def wrapper_hacky_retry(*args, **kwargs) -> Generator:
        attempts: int = 0
        while attempts < n_retries:  
            try:
                if attempts > 0:
                    _logger.info(f"Retrying {attempts}/{n_retries-1}...")

                gen = func(*args, **kwargs)
                return (yield from gen)

            except (ValueError, ConnectionError) as e:
                _logger.error("Error occurred while fetching data.", exc_info=True)
                if attempts == n_retries - 1:  
                    yield None
                attempts += 1
            except Exception as e:
                _logger.error("Unexpected error occurred while fetching data.", exc_info=True)
                yield None

    return wrapper_hacky_retry
