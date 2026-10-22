"""Runner contract tests: fixed fixtures, no model, credentials or network."""

import inspect
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from shayeban.decision import FakeRunner, PredictRunner, StatePayload


@pytest.mark.parametrize(
    ("field", "choice"),
    [("is_claim", "claim"), ("stance", "support"), ("verdict", "UNCLEAR")],
)
def test_each_pass_returns_its_configured_answer(field: str, choice: str) -> None:
    response = {field: {"type": "choice", "choice": choice, "confidence": 0.9}}
    runner: PredictRunner = FakeRunner(response)
    questions = {field: {"type": "choice", "options": [choice]}}
    assert runner.decide("ادعای آزمایشی", questions=questions) == response
    assert runner.decide("different state", questions=questions) == response
    assert runner.decide("ادعای آزمایشی", questions=questions) == response


def test_upstream_answer_envelopes_are_preserved() -> None:
    response = {
        "verdict": {"type": "choice", "choice": "cat", "confidence": 0.9},
        "drama": {
            "type": "score",
            "probabilities": {"0": 0.0, "1": 0.05, "2": 0.1, "3": 0.25, "4": 0.6},
        },
        "forgive": {"type": "noul", "noul": 0.8},
    }
    assert FakeRunner(response).decide("fixture") == response


@pytest.mark.parametrize("state", ["claim", {"claim": ["ادعا"]}, ["claim", {"n": 1}]])
def test_all_payload_forms_and_call_arguments_are_recorded(state: StatePayload) -> None:
    fake = FakeRunner({"answer": {"type": "noul", "noul": 0.8}})
    schema = object()
    questions = {"answer": {"type": "noul"}}
    assert fake.seen_state is None
    fake.decide(state, schema, questions=questions, return_details=True, device="cpu")
    assert fake.seen_state == state
    assert fake.seen_schema is schema
    assert fake.seen_questions == questions
    assert fake.seen_return_details is True
    assert fake.seen_predict_kwargs == {"device": "cpu"}
    fake.decide("next")
    assert fake.seen_state == "next"
    assert fake.seen_schema is None
    assert fake.seen_questions is None
    assert fake.seen_return_details is False
    assert fake.seen_predict_kwargs == {}


def test_mutating_configuration_or_return_value_cannot_change_future_answers() -> None:
    response = {"stance": {"type": "choice", "choice": "support", "confidence": 0.9}}
    fake = FakeRunner(response)
    response["stance"]["choice"] = "contradict"
    first = fake.decide("claim")
    first["stance"]["choice"] = "irrelevant"
    second = fake.decide("claim")
    assert second["stance"]["choice"] == "support"
    assert first is not second
    assert first["stance"] is not second["stance"]


def test_observed_mutable_inputs_are_snapshots() -> None:
    state: dict[str, Any] = {"claim": ["original"]}
    questions: dict[str, Any] = {"stance": {"options": ["support"]}}
    options = {"nested": [1]}
    fake = FakeRunner({})
    fake.decide(state, questions=questions, options=options)
    state["claim"].append("changed")
    questions["stance"]["options"].append("contradict")
    options["nested"].append(2)
    assert fake.seen_state == {"claim": ["original"]}
    assert fake.seen_questions == {"stance": {"options": ["support"]}}
    assert fake.seen_predict_kwargs == {"options": {"nested": [1]}}


def test_independent_fakes_do_not_share_configuration() -> None:
    support = FakeRunner({"stance": {"choice": "support"}})
    contradict = FakeRunner({"stance": {"choice": "contradict"}})
    assert support.decide("same") != contradict.decide("same")
    assert support.decide("same") == {"stance": {"choice": "support"}}


@pytest.mark.parametrize("runner_type", [PredictRunner, FakeRunner])
def test_signature_matches_the_survey(runner_type: type[PredictRunner]) -> None:
    parameters = inspect.signature(runner_type.decide).parameters
    assert list(parameters) == [
        "self",
        "state",
        "schema",
        "questions",
        "return_details",
        "predict_kwargs",
    ]
    assert parameters["state"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["state"].default is inspect.Parameter.empty
    assert parameters["schema"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["schema"].default is None
    assert parameters["questions"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["questions"].default is None
    assert parameters["return_details"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["return_details"].default is False
    assert parameters["predict_kwargs"].kind is inspect.Parameter.VAR_KEYWORD
    assert not inspect.iscoroutinefunction(runner_type.decide)


def test_import_and_all_passes_work_with_model_imports_and_network_forbidden() -> None:
    # Fresh interpreter prevents a previously imported dependency hiding a leak.
    # This is an import/network guard, not a mock runner or a model substitute.
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = """
import sys
import importlib.abc
class BlockModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "laya", "torch", "transformers", "huggingface_hub", "safetensors"
        }:
            raise AssertionError("model dependency imported: " + fullname)
sys.meta_path.insert(0, BlockModels())
def forbid_network(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                 "socket.sendto", "socket.bind"}:
        raise AssertionError("network attempted: " + event)
sys.addaudithook(forbid_network)
sys.path.insert(0, sys.argv[1])
from shayeban.decision import FakeRunner
for field, choice in [("is_claim", "claim"), ("stance", "support"),
                      ("verdict", "UNCLEAR")]:
    expected = {field: {"type": "choice", "choice": choice, "confidence": 0.9}}
    fake = FakeRunner(expected)
    assert fake.decide("fixture") == fake.decide("fixture") == expected
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(source_root)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
