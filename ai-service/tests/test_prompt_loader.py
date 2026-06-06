import pytest
from app.utils.prompt_loader import (
    interpolate_variables,
    process_snippets,
    process_conditionals,
    load_prompt_file,
)


class TestInterpolateVariables:
    def test_simple_replacement(self):
        template = "Hello {name}!"
        result = interpolate_variables(template, {"name": "World"})
        assert result == "Hello World!"

    def test_multiple_variables(self):
        template = "{greeting} {name}, you are {age} years old."
        result = interpolate_variables(template, {"greeting": "Hi", "name": "Alice", "age": "25"})
        assert result == "Hi Alice, you are 25 years old."

    def test_missing_variable_preserved(self):
        template = "Hello {name}, welcome to {place}!"
        result = interpolate_variables(template, {"name": "Alice"})
        assert result == "Hello Alice, welcome to {place}!"

    def test_dict_value(self):
        template = "Profile: {profile}"
        result = interpolate_variables(template, {"profile": {"key": "value"}})
        assert '"key": "value"' in result

    def test_list_value(self):
        template = "Items: {items}"
        result = interpolate_variables(template, {"items": [1, 2, 3]})
        assert "[1, 2, 3]" in result

    def test_none_value(self):
        template = "Value: {val}"
        result = interpolate_variables(template, {"val": None})
        assert result == "Value: {val}"

    def test_empty_variables(self):
        template = "Hello {name}!"
        result = interpolate_variables(template, {})
        assert result == "Hello {name}!"

    def test_none_variables(self):
        template = "Hello {name}!"
        result = interpolate_variables(template, None)
        assert result == "Hello {name}!"


class TestProcessConditionals:
    def test_condition_true(self):
        template = "Start {{#if show}}Hidden Content{{/if}} End"
        result = process_conditionals(template, {"show": True})
        assert result == "Start Hidden Content End"

    def test_condition_false(self):
        template = "Start {{#if show}}Hidden Content{{/if}} End"
        result = process_conditionals(template, {"show": False})
        assert result == "Start  End"

    def test_no_conditions(self):
        template = "Plain text without conditions"
        result = process_conditionals(template)
        assert result == "Plain text without conditions"


class TestProcessSnippets:
    def test_snippet_not_found(self):
        template = "{{snippet:nonexistent}}"
        result = process_snippets(template)
        assert "[snippet:nonexistent not found]" in result

    def test_no_snippets(self):
        template = "Plain text"
        result = process_snippets(template)
        assert result == "Plain text"


class TestLoadPromptFile:
    def test_load_existing_prompt(self):
        result = load_prompt_file("profile_agent", "system.yaml", key="system")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_nonexistent_file(self):
        result = load_prompt_file("nonexistent", "fake.yaml")
        assert result == ""

    def test_load_nonexistent_key(self):
        result = load_prompt_file("profile_agent", "system.yaml", key="nonexistent")
        assert result == ""
