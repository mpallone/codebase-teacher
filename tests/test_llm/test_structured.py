"""Tests for structured output parsing."""

import pytest
from pydantic import BaseModel

from codebase_teacher.llm.structured import extract_json, parse_json_response, parse_model, parse_model_list
from codebase_teacher.core.exceptions import LLMResponseError


class SampleModel(BaseModel):
    name: str
    value: int


def test_extract_json_from_code_fence():
    text = '```json\n{"name": "test", "value": 42}\n```'
    result = extract_json(text)
    assert result == '{"name": "test", "value": 42}'


def test_extract_json_bare():
    text = '{"name": "test", "value": 42}'
    result = extract_json(text)
    assert result == '{"name": "test", "value": 42}'


def test_extract_json_with_surrounding_text():
    text = 'Here is the result:\n{"name": "test", "value": 42}\nDone.'
    result = extract_json(text)
    assert result == '{"name": "test", "value": 42}'


def test_extract_json_array():
    text = '[{"name": "a", "value": 1}, {"name": "b", "value": 2}]'
    result = extract_json(text)
    assert result == text


def test_parse_json_response_valid():
    result = parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}


def test_parse_json_response_invalid():
    with pytest.raises(LLMResponseError):
        parse_json_response("this is not json at all")


def test_parse_model():
    text = '{"name": "test", "value": 42}'
    result = parse_model(text, SampleModel)
    assert result.name == "test"
    assert result.value == 42


def test_parse_model_list():
    text = '[{"name": "a", "value": 1}, {"name": "b", "value": 2}]'
    result = parse_model_list(text, SampleModel)
    assert len(result) == 2
    assert result[0].name == "a"
    assert result[1].value == 2


def test_parse_model_invalid_data():
    with pytest.raises(LLMResponseError):
        parse_model('{"wrong_field": "test"}', SampleModel)


def test_parse_model_from_code_fence():
    text = '```json\n{"name": "fenced", "value": 99}\n```'
    result = parse_model(text, SampleModel)
    assert result.name == "fenced"
    assert result.value == 99
