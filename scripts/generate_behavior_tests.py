#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2025 Valory AG
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
"""Script to generate test scaffolding for Valory framework behaviors using AST parsing."""

import argparse
import ast
import importlib
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type, cast
import pkgutil

TEST_STYLE_UNITTEST = "unittest"
TEST_STYLE_PYTEST = "pytest"

# Templates for test files - using raw triple-quoted strings to avoid escape issues
UNITTEST_FILE_TEMPLATE = r'''# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2025 Valory AG
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

"""Tests for the {module_name} module."""

import json
import unittest
from typing import Any, Generator, cast
from unittest.mock import MagicMock, PropertyMock, patch

{imports}

# --------------------------------------------------------------------------- #
# Helper to create a generator that first yields (for the "yield from") and   #
# then returns a prepared response.                                           #
# --------------------------------------------------------------------------- #
def make_generator(response):
    def _gen(*_args, **_kwargs):
        yield
        return response

    return _gen


# =========================================================================== #
#  Dummy behaviour for tests                                                  #
# =========================================================================== #
class Dummy{behavior_name}({behavior_class}):
    """A minimal concrete subclass so we can instantiate & test."""

    matching_round = {matching_round}  # satisfies BaseBehaviourInternalError

    def __init__(self):
        # Don't call super().__init__ to avoid dependency on name and skill_context
        self._params = MagicMock()
        self._synchronized_data = MagicMock()
        self._shared_state = MagicMock()
        
    # --- async helpers the Base uses (all mocked) ------------------------- #
    {mock_methods}
    
    async def async_act(self):
        pass


class Test{behavior_name}(unittest.TestCase):
    """Test {behavior_name} class."""

    def setUp(self):
        """Set up the test."""
        self.behaviour = Dummy{behavior_name}()

        # centralized context patch
        patcher = patch.object(Dummy{behavior_name}, "context", new_callable=PropertyMock)
        self.addCleanup(patcher.stop)
        self.mock_context = patcher.start()

        # Create a mock for the context
        ctx = MagicMock()
        ctx.state = MagicMock()
        ctx.logger = MagicMock()
        ctx.outbox = MagicMock()
        ctx.benchmark_tool = MagicMock()
        ctx.benchmark_tool.measure.return_value = MagicMock()
        ctx.benchmark_tool.measure.return_value.local.return_value = MagicMock()
        ctx.benchmark_tool.measure.return_value.consensus.return_value = MagicMock()
        ctx.agent_address = "agent_address"

        # Assign the mock context to the behaviour
        self.mock_context.return_value = ctx

        # Mock the synchronized data
        sync_data = MagicMock()
        
        # Add commonly used properties
        {sync_data_mocks}

        # Mock the behaviour's properties
        patcher_sync_data = patch.object(
            Dummy{behavior_name}, "synchronized_data", new_callable=PropertyMock
        )
        self.addCleanup(patcher_sync_data.stop)
        self.mock_sync_data = patcher_sync_data.start()
        self.mock_sync_data.return_value = sync_data

        # Mock the params
        params = MagicMock()
        {params_mocks}

        patcher_params = patch.object(
            Dummy{behavior_name}, "params", new_callable=PropertyMock
        )
        self.addCleanup(patcher_params.stop)
        self.mock_params = patcher_params.start()
        self.mock_params.return_value = params

        # Setup common mocks
        self.behaviour.send_a2a_transaction = MagicMock(
            side_effect=make_generator(None)
        )
        self.behaviour.wait_until_round_end = MagicMock(
            side_effect=make_generator(None)
        )
        
        # Store the original method and create a spy version of get_payload if it exists
        if hasattr(self.behaviour, 'get_payload'):
            self.original_get_payload = self.behaviour.get_payload
        
        # Set done mock
        self.behaviour.set_done = MagicMock()

        # Handy aliases
        self.ctx = self.behaviour.context
        self.sync_data = self.behaviour.synchronized_data

    {method_tests}
    
if __name__ == "__main__":
    unittest.main()
'''

PYTEST_FILE_TEMPLATE = r'''# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2025 Valory AG
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

"""Tests for the {behavior_name}."""

import json
from types import SimpleNamespace
from typing import Any, Dict, Generator, List, Optional

import pytest
from hypothesis import given
from hypothesis import strategies as st
from unittest.mock import MagicMock, PropertyMock, patch

{imports}

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def gen_side_effect(resp):
    """Return a generator object that yields once then returns *resp*."""
    def _g(*_a, **_kw):
        yield
        return resp
    return _g()


def dummy_ctx() -> MagicMock:
    """Create a standard mock context for behaviour testing."""
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.logger = MagicMock()
    ctx.benchmark_tool = MagicMock()
    ctx.benchmark_tool.measure.return_value = MagicMock()
    ctx.benchmark_tool.measure.return_value.local.return_value = MagicMock()
    ctx.benchmark_tool.measure.return_value.consensus.return_value = MagicMock()
    ctx.agent_address = "agent_address"
    ctx.outbox = MagicMock()
    ctx.requests = MagicMock()
    ctx.requests.request_id_to_callback = {{}}
    return ctx


class Dummy{behavior_name}({behavior_class}):
    """A minimal concrete subclass so we can instantiate & test."""

    matching_round = {matching_round}  # satisfy framework requirement

    def __init__(self):
        self._params = SimpleNamespace({params_namespace})
        self._synchronized_data = SimpleNamespace({sync_data_namespace})
        self._shared_state = MagicMock()

    # Mock generator methods
    {mock_methods}
    
    async def async_act(self):
        pass


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def behaviour(request):
    """Provide a behaviour instance with mocked context."""
    beh = Dummy{behavior_name}()
    ctx_patch = patch.object(Dummy{behavior_name}, "context", new_callable=PropertyMock)
    mock_ctx_prop = ctx_patch.start()
    mock_ctx_prop.return_value = dummy_ctx()
    
    # Add finalizer to clean up after the test
    request.addfinalizer(ctx_patch.stop)
    
    return beh


# --------------------------------------------------------------------------- #
# Basic functionality tests                                                   #
# --------------------------------------------------------------------------- #
def test_basic_functionality(behaviour):
    """Test basic functionality of the {behavior_name}."""
    # Verify that necessary attributes and methods are available
    assert hasattr(behaviour, "matching_round")
    assert behaviour.matching_round == {matching_round}
    
    # Check main behavior methods exist
    assert callable(getattr(behaviour, "async_act", None))
    {basic_method_assertions}
    
    # Verify parameters were initialized correctly from our SimpleNamespace
    {basic_param_assertions}
    
    # Test the __init__ method set up the synchronized data correctly
    assert behaviour._synchronized_data.safe_contract_address == "0xSAFE"
    assert behaviour._synchronized_data.most_voted_keeper_address == "agent_address"
    {basic_sync_data_assertions}


{method_tests}
'''

UNITTEST_METHOD_TEST_TEMPLATE = r'''
    def test_{method_name}(self):
        """Test {method_name} method."""
        # Setup
        {expected_result_setup}
        
        # Mock dependencies
        {mock_dependencies}
        
        # Call the method
        gen = self.behaviour.{method_name}({method_args})
        # Start the generator
        next(gen)
        # Complete the generator and check result
        with self.assertRaises(StopIteration) as stop:
            next(gen)
        {assert_result}
        
        # Verify the expected calls
        {verify_calls}
'''

PYTEST_METHOD_TEST_TEMPLATE = r'''
# --------------------------------------------------------------------------- #
# {method_name}                                                                #
# --------------------------------------------------------------------------- #
def test_{method_name}(behaviour):
    """Test {method_name} method."""
    # Setup
    {expected_result_setup}
    
    # Mock dependencies
    {mock_dependencies}
    
    # Call the method
    gen = behaviour.{method_name}({method_args})
    
    # Start the generator
    next(gen)
    
    # Complete the generator and check result
    with pytest.raises(StopIteration) as exc:
        next(gen)
    {assert_result}
    
    # Verify the expected calls
    {verify_calls}
'''

PYTEST_PROPERTY_BASED_TEST_TEMPLATE = r'''
@given({strategy})
def test_{method_name}_property_based({args}):
    """Property-based test for {method_name} with various inputs."""
    # Create a fresh behavior for each test case
    behaviour = Dummy{behavior_name}()
    with patch.object(Dummy{behavior_name}, "context", PropertyMock(return_value=dummy_ctx())):
        # Set up mocks
        {mock_setup}
        
        # Call method and check result
        gen = behaviour.{method_name}({method_args})
        with pytest.raises(StopIteration) as exc:
            while True:
                next(gen)
                
        {assert_result}
'''


class ASTYieldVisitor(ast.NodeVisitor):
    """Find all yield and yield from statements in a function."""

    def __init__(self):
        self.yields = []
        self.yield_froms = []

    def visit_Yield(self, node):
        self.yields.append(node)
        self.generic_visit(node)

    def visit_YieldFrom(self, node):
        self.yield_froms.append(node)
        self.generic_visit(node)


class BehaviorASTAnalyzer(ast.NodeVisitor):
    """AST-based analyzer for behavior classes."""

    def __init__(self, behavior_class: Type):
        """Initialize the analyzer."""
        super().__init__()
        self.behavior_class = behavior_class
        self.source_code = inspect.getsource(behavior_class)
        self.generator_methods = []
        self.dependencies = set()
        self.accessed_properties = set()
        self.round_constants = set()
        self.tree = ast.parse(self.source_code)
        self.current_method = None
        self.current_class = None

        # Run the analysis
        self.visit(self.tree)

        # Get actual methods
        self._resolve_generator_methods()

    def _resolve_generator_methods(self) -> None:
        """Convert AST generator methods to actual method objects."""
        resolved_methods = []
        for method_name in self.generator_methods:
            if hasattr(self.behavior_class, method_name):
                method = getattr(self.behavior_class, method_name)
                if callable(method):
                    resolved_methods.append((method_name, method))

        self.generator_methods = resolved_methods

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        old_class = self.current_class
        self.current_class = node.name

        for stmt in node.body:
            self.visit(stmt)

        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        old_method = self.current_method
        self.current_method = node.name

        # Check if this is a generator function by finding yield statements
        visitor = ASTYieldVisitor()
        visitor.visit(node)

        if visitor.yields or visitor.yield_froms:
            self.generator_methods.append(node.name)

            # Extract dependencies from yield from statements
            for yield_from in visitor.yield_froms:
                if isinstance(yield_from.value, ast.Call):
                    call = yield_from.value
                    if isinstance(call.func, ast.Attribute) and isinstance(
                        call.func.value, ast.Name
                    ):
                        if call.func.value.id == "self":
                            self.dependencies.add(call.func.attr)

        # Visit all nodes in the function
        for stmt in node.body:
            self.visit(stmt)

        self.current_method = old_method

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Visit attribute access."""
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            # Accessing self.attribute
            self.accessed_properties.add(node.attr)

        # Handle self.synchronized_data.property
        if isinstance(node.value, ast.Attribute) and isinstance(
            node.value.value, ast.Name
        ):
            if node.value.attr == "synchronized_data" and node.value.value.id == "self":
                self.accessed_properties.add(f"synchronized_data.{node.attr}")
            elif node.value.attr == "params" and node.value.value.id == "self":
                self.accessed_properties.add(f"params.{node.attr}")

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Visit constants to find round constants."""
        if self.current_method and isinstance(node.value, str):
            # Look for constants that might be round payloads
            if node.value.endswith("_PAYLOAD"):
                self.round_constants.add(node.value)

        self.generic_visit(node)

    def visit_Str(self, node: ast.Str) -> None:
        """Visit string nodes for Python < 3.8 compatibility."""
        if self.current_method and isinstance(node.s, str):
            # Look for constants that might be round payloads
            if node.s.endswith("_PAYLOAD"):
                self.round_constants.add(node.s)

        self.generic_visit(node)

    def get_matching_round(self) -> str:
        """Get the matching round for the behavior class."""
        try:
            # First try to get the matching_round from the class itself
            for name, attr in inspect.getmembers(self.behavior_class):
                if name == "matching_round":
                    if isinstance(attr, str):
                        return attr
                    elif hasattr(attr, "__name__"):
                        return attr.__name__
                    else:
                        return str(attr)
            # Fallback to the class name + "Round"
            return f"{self.behavior_class.__name__}Round"
        except AttributeError:
            return "MagicMock()"


class TestGenerator:
    """Generates test scaffolding for behavior classes using AST analysis."""

    def __init__(
        self,
        behavior_class: Type,
        style: str = TEST_STYLE_PYTEST,
        package_prefix: str = "packages.valory.skills",
    ):
        """Initialize the test generator."""
        self.behavior_class = behavior_class
        self.style = style
        self.package_prefix = package_prefix
        self.analyzer = BehaviorASTAnalyzer(behavior_class)

    def _should_add_property_test(self, method_name: str, param_names: list) -> bool:
        """Determine if a property-based test should be added for this method."""
        # Only add property tests for methods with parameters
        if not param_names:
            return False

        # Methods that deal with text or queries are good candidates
        good_candidates = [
            "get",
            "search",
            "find",
            "query",
            "parse",
            "format",
            "calculate",
        ]
        return any(candidate in method_name.lower() for candidate in good_candidates)

    def _generate_basic_method_assertions(self) -> str:
        """Generate assertions for methods in the basic functionality test."""
        assertions = []

        # Find important methods to test for existence
        important_methods = []

        # Add common generator methods
        for method_name, _ in self.analyzer.generator_methods:
            if method_name != "async_act" and not method_name.startswith("_"):
                important_methods.append(method_name)

        # Add key dependency methods that might be overridden
        key_dependencies = {
            "get_payload",
            "send_a2a_transaction",
            "wait_until_round_end",
        }
        for dep in key_dependencies.intersection(self.analyzer.dependencies):
            important_methods.append(dep)

        # Add sender/non-sender methods if found
        sender_methods = {"_sender_act", "_not_sender_act", "_i_am_not_sending"}
        for method in sender_methods:
            if method in [
                name
                for name, _ in inspect.getmembers(
                    self.behavior_class, predicate=inspect.ismethod
                )
            ]:
                important_methods.append(method)

        # Generate the assertions
        for method_name in sorted(set(important_methods)):
            assertions.append(
                f'assert callable(getattr(behaviour, "{method_name}", None))'
            )

        return "\n    ".join(assertions)

    def _generate_basic_param_assertions(self) -> str:
        """Generate assertions for params in the basic functionality test."""
        assertions = []

        # Find important params to test
        important_params = set()

        # Add parameters from AST analysis
        for prop in self.analyzer.accessed_properties:
            if prop.startswith("params."):
                prop_name = prop.split(".")[1]
                important_params.add(prop_name)

        # Limit to at most 5 parameters to avoid overly verbose tests
        if len(important_params) > 5:
            # Prioritize contract addresses and important configuration
            priority_keywords = ["contract", "address", "api_key", "url", "timeout"]
            prioritized = set()

            for keyword in priority_keywords:
                for param in important_params:
                    if keyword in param.lower() and len(prioritized) < 5:
                        prioritized.add(param)

            important_params = (
                prioritized if prioritized else set(list(important_params)[:5])
            )

        # Generate assertions
        for param in sorted(important_params):
            assertions.append(f'assert hasattr(behaviour._params, "{param}")')

        return "\n    ".join(assertions)

    def _generate_basic_sync_data_assertions(self) -> str:
        """Generate assertions for synchronized_data in the basic functionality test."""
        assertions = []

        # Find important synchronized_data to test
        important_sync_data = set()

        # Add synchronized_data from AST analysis
        for prop in self.analyzer.accessed_properties:
            if prop.startswith("synchronized_data."):
                prop_name = prop.split(".")[1]
                important_sync_data.add(prop_name)

        # Limit to at most 5 to avoid overly verbose tests
        if len(important_sync_data) > 5:
            important_sync_data = set(list(important_sync_data)[:5])

        # Generate assertions
        for sync_data in sorted(important_sync_data):
            assertions.append(
                f'assert hasattr(behaviour._synchronized_data, "{sync_data}")'
            )

        return "\n    ".join(assertions)

    def _generate_mock_response_for_dependency(self, dependency_name: str) -> str:
        """Generate appropriate mock response based on dependency type."""
        if dependency_name == "get_contract_api_response":
            return 'MagicMock(performative=ContractApiMessage.Performative.RESPONSE, response={"status": True, "data": {"result": "0x1234"}})'
        elif dependency_name == "get_http_response":
            return 'MagicMock(body=json.dumps({"result": "success"}).encode("utf-8"), status_code=200)'
        elif dependency_name == "get_ledger_api_response":
            return 'MagicMock(performative=LedgerApiMessage.Performative.RESPONSE, response={"block_hash": "0xblockhash1234"})'
        elif dependency_name == "get_subgraph_result":
            return '{"data": {"markets": [{"id": "market1", "title": "Test Market"}]}}'
        elif dependency_name == "send_a2a_transaction":
            return "None"
        else:
            return "MagicMock()"

    def _generate_method_tests_pytest(self) -> str:
        """Generate pytest style test methods for behavior methods."""
        method_tests = []

        # Always test async_act method for sender and non-sender cases
        is_sender_check = False
        for prop in self.analyzer.accessed_properties:
            if "most_voted_keeper_address" in prop:
                is_sender_check = True

        # Enhanced async_act test with proper response handling
        if is_sender_check:
            # Create tests for both sender and non-sender cases
            async_act_sender_test = PYTEST_METHOD_TEST_TEMPLATE.format(
                method_name="async_act_sender",
                expected_result_setup="# Mock behaviour as sender\nbehaviour._i_am_not_sending = MagicMock(return_value=False)\nbehaviour._sender_act = MagicMock(side_effect=gen_side_effect(None))",
                mock_dependencies="behaviour.set_done = MagicMock()",
                method_args="",
                assert_result="# Verify sender path taken",
                verify_calls="behaviour._sender_act.assert_called_once()\nbehaviour.set_done.assert_called_once()\nbehaviour._not_sender_act.assert_not_called() if hasattr(behaviour, '_not_sender_act') else None",
            )
            method_tests.append(async_act_sender_test)

            async_act_non_sender_test = PYTEST_METHOD_TEST_TEMPLATE.format(
                method_name="async_act_non_sender",
                expected_result_setup="# Mock behaviour as non-sender\nbehaviour._i_am_not_sending = MagicMock(return_value=True)\nbehaviour._not_sender_act = MagicMock(side_effect=gen_side_effect(None))",
                mock_dependencies="behaviour.set_done = MagicMock()",
                method_args="",
                assert_result="# Verify non-sender path taken",
                verify_calls="behaviour._not_sender_act.assert_called_once()\nbehaviour.set_done.assert_called_once()\nbehaviour._sender_act.assert_not_called() if hasattr(behaviour, '_sender_act') else None",
            )
            method_tests.append(async_act_non_sender_test)

        else:
            # Test basic functionality only - don't try to simulate async behavior
            async_act_test = """
# --------------------------------------------------------------------------- #
# async_act - basic test                                                      #
# --------------------------------------------------------------------------- #
def test_async_act_basic(behaviour):
    \"\"\"Basic test for async_act - verifies it exists but doesn't simulate execution.\"\"\"
    # Simply verify the method exists and is callable
    assert callable(getattr(behaviour, "async_act", None))
    
    # Mock dependencies typically used in async_act
    behaviour.send_a2a_transaction = MagicMock()
    behaviour.wait_until_round_end = MagicMock()
    behaviour.set_done = MagicMock()
    
    # For more comprehensive tests of async_act, manual testing is recommended"""
            method_tests.append(async_act_test)

        # Generate tests for each generator method
        for method_name, method in self.analyzer.generator_methods:
            if method_name == "async_act" or method_name.startswith("_"):
                continue  # Already handled or private method

            # Get parameters for the method
            sig = inspect.signature(method)
            param_names = [p for p in sig.parameters if p != "self"]

            method_args = ", ".join(f'"{p}"' for p in param_names)
            mock_deps = []
            verify_calls = []

            # Add dependency mocks based on yield froms in the method
            for dep in self.analyzer.dependencies:
                if dep in {
                    "get_contract_api_response",
                    "get_http_response",
                    "get_ledger_api_response",
                    "wait_for_message",
                    "wait_until_round_end",
                    "get_subgraph_result",
                    "send_a2a_transaction",
                }:
                    # Create more realistic mock responses based on the dependency type
                    response = self._generate_mock_response_for_dependency(dep)
                    mock_deps.append(
                        f"behaviour.{dep} = MagicMock(side_effect=gen_side_effect({response}))"
                    )
                    verify_calls.append(f"behaviour.{dep}.assert_called_once()")

            if not mock_deps:
                mock_deps = ["# No dependencies to mock"]

            if not verify_calls:
                verify_calls = ["# No specific verifications needed"]

            # Create expected results based on constants found in the method
            expected_result = f'expected_result = "test_result"'

            # If there are round constants in the behavior, use one as the expected result
            if self.analyzer.round_constants:
                round_constant = list(self.analyzer.round_constants)[0]
                expected_result = f'expected_result = "{round_constant}"'

            assert_stmt = f"assert exc.value.value == expected_result"

            method_test = PYTEST_METHOD_TEST_TEMPLATE.format(
                method_name=method_name,
                expected_result_setup=expected_result,
                mock_dependencies="\n    ".join(mock_deps),
                method_args=method_args,
                assert_result=assert_stmt,
                verify_calls="\n    ".join(verify_calls),
            )
            method_tests.append(method_test)

            # Add a property-based test for methods with string parameters
            if self._should_add_property_test(method_name, param_names):
                strategy = "st.text(min_size=1)"
                args = param_names[0] if param_names else "query"
                method_args = args
                mock_setup = "\n        ".join(mock_deps)
                assert_result = "# Check the result type is as expected\n        assert exc.value is not None"

                if len(param_names) > 1:
                    strategy = ", ".join(f"st.text(min_size=1)" for _ in param_names)
                    args = ", ".join(param_names)

                property_test = PYTEST_PROPERTY_BASED_TEST_TEMPLATE.format(
                    method_name=method_name,
                    strategy=strategy,
                    args=args,
                    behavior_name=self.behavior_class.__name__,
                    mock_setup=mock_setup,
                    method_args=method_args,
                    assert_result=assert_result,
                )
                method_tests.append(property_test)

        return "\n".join(method_tests)

    def generate_test_file(self) -> str:
        """Generate the full test file content based on the selected style."""
        if self.style == TEST_STYLE_UNITTEST:
            return self._generate_unittest_test_file()
        else:  # Default to pytest style
            return self._generate_pytest_test_file()

    def _generate_params_namespace(self) -> str:
        """Generate a SimpleNamespace initialization for parameters used by the behavior."""
        params = []

        # Find important parameters the behavior accesses
        for prop in self.analyzer.accessed_properties:
            if prop.startswith("params."):
                param_name = prop.split(".")[1]
                if param_name.endswith("_contract"):
                    params.append(f'{param_name}="0x{param_name.upper()}"')
                elif "address" in param_name:
                    params.append(f'{param_name}="0x{param_name.upper()}"')
                elif "api_key" in param_name:
                    params.append(f'{param_name}="{param_name}_value"')
                elif "url" in param_name:
                    params.append(f'{param_name}="https://example.com/{param_name}"')
                else:
                    params.append(f'{param_name}="{param_name}_value"')

        return ", ".join(params)

    def _generate_sync_data_namespace(self) -> str:
        """Generate a SimpleNamespace initialization for synchronized data used by the behavior."""
        sync_data = []

        # Include common sync_data properties needed for testing
        sync_data.append('safe_contract_address="0xSAFE"')
        sync_data.append('most_voted_keeper_address="agent_address"')

        # Add specific properties the behavior accesses
        for prop in self.analyzer.accessed_properties:
            if prop.startswith("synchronized_data."):
                prop_name = prop.split(".")[1]
                if prop_name not in [
                    "safe_contract_address",
                    "most_voted_keeper_address",
                ]:
                    if prop_name.endswith("_hash"):
                        sync_data.append(f'{prop_name}="0x1234abcd{prop_name}"')
                    elif prop_name.endswith("_address"):
                        sync_data.append(f'{prop_name}="0x{prop_name.upper()}"')
                    else:
                        sync_data.append(f'{prop_name}="{prop_name}_value"')

        return ", ".join(sync_data)

    def _generate_mock_methods(self) -> str:
        """Generate mock implementations for generator methods called by tests."""
        methods = []

        # Common generator methods to mock
        dependencies = {
            "send_a2a_transaction",
            "wait_until_round_end",
            "get_contract_api_response",
            "wait_for_message",
            "get_http_response",
            "get_ledger_api_response",
        }

        # Add additional dependencies found in AST analysis
        dependencies.update(self.analyzer.dependencies)

        for method_name in sorted(dependencies):
            if method_name != "async_act":  # async_act is implemented separately
                methods.append(
                    f"def {method_name}(self, *args, **kwargs):\n        return (yield MagicMock())"
                )

        return "\n    ".join(methods)

    def _generate_imports(self) -> str:
        """Generate import statements for the test file."""
        imports = [
            "from packages.valory.skills.market_creation_manager_abci.behaviours.base import MarketCreationManagerBaseBehaviour",
            f"from packages.valory.skills.market_creation_manager_abci.behaviours.{self.behavior_class.__name__.lower()} import {self.behavior_class.__name__}",
        ]

        # Add protocol imports if protocols are used
        if "get_contract_api_response" in self.analyzer.dependencies:
            imports.append(
                "from packages.valory.protocols.contract_api import ContractApiMessage"
            )

        if "get_ledger_api_response" in self.analyzer.dependencies:
            imports.append(
                "from packages.valory.protocols.ledger_api import LedgerApiMessage"
            )

        if "get_http_response" in self.analyzer.dependencies:
            imports.append("from packages.valory.protocols.http import HttpMessage")

        # Import related rounds
        matching_round = self.analyzer.get_matching_round()
        if matching_round:
            imports.append(
                f"from packages.valory.skills.market_creation_manager_abci.rounds import {matching_round}"
            )

        return "\n".join(imports)

    def _generate_unittest_test_file(self) -> str:
        """Generate a unittest style test file."""
        module_name = self.behavior_class.__module__.split(".")[-1]

        # Generate sync_data mocks
        sync_data_mocks = []
        for prop in self.analyzer.accessed_properties:
            if prop.startswith("synchronized_data."):
                prop_name = prop.split(".")[1]
                if prop_name == "most_voted_keeper_address":
                    sync_data_mocks.append(f'sync_data.{prop_name} = "agent_address"')
                else:
                    sync_data_mocks.append(
                        f'sync_data.{prop_name} = "{prop_name}_value"'
                    )

        # Generate params mocks
        params_mocks = []
        for prop in self.analyzer.accessed_properties:
            if prop.startswith("params."):
                param_name = prop.split(".")[1]
                if param_name.endswith("_contract"):
                    params_mocks.append(
                        f'params.{param_name} = "0x{param_name.upper()}"'
                    )
                elif "address" in param_name:
                    params_mocks.append(
                        f'params.{param_name} = "0x{param_name.upper()}"'
                    )
                else:
                    params_mocks.append(f'params.{param_name} = "{param_name}_value"')

        return UNITTEST_FILE_TEMPLATE.format(
            module_name=module_name,
            behavior_name=self.behavior_class.__name__,
            imports=self._generate_imports(),
            behavior_class=self.behavior_class.__name__,
            matching_round=self.analyzer.get_matching_round(),
            mock_methods=self._generate_mock_methods(),
            sync_data_mocks="\n        ".join(sync_data_mocks),
            params_mocks="\n        ".join(params_mocks),
            method_tests="",  # Implement method tests for unittest style if needed
        )

    def _generate_pytest_test_file(self) -> str:
        """Generate a pytest style test file."""
        behavior_module = self.behavior_class.__module__.split(".")[-1]

        return PYTEST_FILE_TEMPLATE.format(
            behavior_name=self.behavior_class.__name__,
            imports=self._generate_imports(),
            behavior_class=self.behavior_class.__name__,
            matching_round=self.analyzer.get_matching_round(),
            mock_methods=self._generate_mock_methods(),
            params_namespace=self._generate_params_namespace(),
            sync_data_namespace=self._generate_sync_data_namespace(),
            method_tests=self._generate_method_tests_pytest(),
            basic_method_assertions=self._generate_basic_method_assertions(),
            basic_param_assertions=self._generate_basic_param_assertions(),
            basic_sync_data_assertions=self._generate_basic_sync_data_assertions(),
        )


class BehaviorFinder:
    """Find behavior classes in a skill."""

    def __init__(self, skill_path: str, base_class_name: str = "BaseBehaviour"):
        """Initialize the finder with skill path and base class name."""
        self.skill_path = Path(skill_path).resolve()
        if not self.skill_path.exists():
            raise FileNotFoundError(f"Skill path {skill_path} does not exist")

        self.base_class_name = base_class_name
        self.behaviors_path = self.skill_path / "behaviours"
        if not self.behaviors_path.exists():
            raise FileNotFoundError(
                f"Behaviors path {self.behaviors_path} does not exist"
            )

    def _import_module_from_path(self, module_path: str) -> Optional[Any]:
        """Import a module from its file path."""
        try:
            # Add the project root to sys.path if it's not already there
            project_root = str(self.skill_path.parent.parent.parent.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            # Import directly using spec_from_file_location which doesn't rely on
            # module naming conventions
            module_name = f"dynamic_module_{abs(hash(module_path))}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                print(f"Failed to create spec for {module_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[
                module_name
            ] = module  # Add module to sys.modules to make imports within the module work
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            print(f"Error importing module {module_path}: {e}")
            return None

    def _is_behavior_class(self, obj: Any) -> bool:
        """Check if the object is a behavior class."""
        if not inspect.isclass(obj):
            return False

        # Check if it inherits from the base behavior class
        for base in obj.__mro__:
            if base.__name__ == self.base_class_name:
                return True

        return False

    def find_base_class(self) -> Optional[Type]:
        """Find the base class for the behaviors in the skill."""
        # Look in base.py first
        base_path = self.behaviors_path / "base.py"
        if base_path.exists():
            base_module = self._import_module_from_path(str(base_path))
            if base_module:
                for name, obj in inspect.getmembers(base_module):
                    if inspect.isclass(obj) and name == self.base_class_name:
                        return obj

        # Look in __init__.py
        init_path = self.behaviors_path / "__init__.py"
        if init_path.exists():
            init_module = self._import_module_from_path(str(init_path))
            if init_module:
                for name, obj in inspect.getmembers(init_module):
                    if inspect.isclass(obj) and name == self.base_class_name:
                        return obj

        # Search all modules
        for module in self._get_all_behavior_modules():
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and name == self.base_class_name:
                    return obj

        return None

    def _get_all_behavior_modules(self) -> List[Any]:
        """Get all behavior modules in the skill."""
        modules = []

        # Get all Python files in the behaviors directory
        for file_path in self.behaviors_path.glob("*.py"):
            if file_path.name.startswith("__"):
                continue

            module = self._import_module_from_path(str(file_path))
            if module:
                modules.append(module)

        return modules

    def find_behavior_classes(self, module_path: Optional[str] = None) -> List[Type]:
        """Find all behavior classes in the skill or specific module."""
        behavior_classes = []

        # If module_path is provided, only look in that module
        if module_path:
            module = self._import_module_from_path(module_path)
            if module:
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and hasattr(obj, "__module__")
                        and obj.__module__ == module.__name__
                        and self._is_behavior_class(obj)
                        and not name.startswith("Abstract")
                    ):
                        behavior_classes.append(obj)
        else:
            # Look in all modules
            for module in self._get_all_behavior_modules():
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and hasattr(obj, "__module__")
                        and obj.__module__ == module.__name__
                        and self._is_behavior_class(obj)
                        and not name.startswith("Abstract")
                    ):
                        behavior_classes.append(obj)

        return behavior_classes


def find_behavior_classes(
    module_path: str, base_class_name: str = "BaseBehaviour"
) -> List[Type]:
    """Find all behavior classes in the given module."""
    try:
        module_name = module_path.replace("/", ".").rstrip(".py")
        if module_name.startswith("."):
            module_name = module_name[1:]

        if module_name.endswith(".py"):
            module_name = module_name[:-3]

        module = importlib.import_module(module_name)

        behavior_classes = []
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and hasattr(obj, "__module__")
                and obj.__module__ == module_name
            ):
                # Check if it's a behavior class (inherits from BaseBehaviour)
                mro = obj.__mro__
                if any(
                    cls.__name__ == base_class_name for cls in mro
                ) and not name.startswith("Abstract"):
                    behavior_classes.append(obj)

        return behavior_classes
    except (ImportError, AttributeError) as e:
        print(f"Error importing module {module_path}: {e}")
        return []


def create_test_file(behavior_class: Type, output_dir: str, style: str) -> str:
    """Generate and write a test file for the given behavior class."""
    generator = TestGenerator(behavior_class, style=style)
    test_content = generator.generate_test_file()

    behavior_name = behavior_class.__name__
    behavior_module = behavior_class.__module__.split(".")[-1]

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Write the test file
    test_file_path = os.path.join(
        output_dir, f"test_{behavior_module}_{behavior_name.lower()}.py"
    )
    with open(test_file_path, "w") as f:
        f.write(test_content)

    return test_file_path


def main():
    """Run the script."""
    parser = argparse.ArgumentParser(
        description="Generate test scaffolding for Valory framework behaviors using AST parsing."
    )
    parser.add_argument(
        "skill_path", help="Path to the skill containing behavior classes"
    )
    parser.add_argument(
        "--module",
        "-m",
        help="Path to a specific behavior module within the skill",
        default=None,
    )
    parser.add_argument(
        "--output-dir", "-o", help="Directory to output test files", default=None
    )
    parser.add_argument(
        "--style",
        "-s",
        choices=[TEST_STYLE_UNITTEST, TEST_STYLE_PYTEST],
        default=TEST_STYLE_PYTEST,
        help="Test style to generate (unittest or pytest)",
    )
    parser.add_argument(
        "--base-class",
        "-b",
        default=None,
        help="Base class name to look for (default: auto-detect)",
    )
    parser.add_argument(
        "--behavior-name",
        "-n",
        default=None,
        help="Specific behavior class name to generate test for",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available behavior classes and exit",
    )

    args = parser.parse_args()

    # Auto-detect the base class if not provided
    base_class_name = args.base_class
    if base_class_name is None:
        # Try to guess from the skill name
        skill_path = Path(args.skill_path)
        skill_name = skill_path.name
        if skill_name.endswith("_abci"):
            skill_name = skill_name[:-5]
        # Convert snake_case to CamelCase
        base_class_guess = (
            "".join(x.title() for x in skill_name.split("_")) + "BaseBehaviour"
        )
        base_class_name = base_class_guess

    # Set default output directory if not provided
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = os.path.join(args.skill_path, "tests")

    # Find behavior classes
    try:
        finder = BehaviorFinder(args.skill_path, base_class_name)

        if args.module:
            # Resolve module path
            module_path = os.path.join(args.skill_path, "behaviours", args.module)
            if not module_path.endswith(".py"):
                module_path += ".py"
            behavior_classes = finder.find_behavior_classes(module_path)
        else:
            behavior_classes = finder.find_behavior_classes()

        if args.list:
            print(f"Found {len(behavior_classes)} behavior classes:")
            for i, cls in enumerate(behavior_classes):
                print(f"{i+1}. {cls.__name__} (from {cls.__module__})")
            return 0

        if not behavior_classes:
            print(f"No behavior classes found in {args.skill_path}")
            return 1

        # Filter by behavior name if provided
        if args.behavior_name:
            behavior_classes = [
                cls for cls in behavior_classes if cls.__name__ == args.behavior_name
            ]
            if not behavior_classes:
                print(f"No behavior class named '{args.behavior_name}' found")
                return 1

        # Generate test files
        for behavior_class in behavior_classes:
            test_file_path = create_test_file(behavior_class, output_dir, args.style)
            print(
                f"Generated test file: {test_file_path} for {behavior_class.__name__}"
            )

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
