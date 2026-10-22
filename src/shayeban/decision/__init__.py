"""Public runner contract and deterministic offline test double."""

from .runner import FakeRunner, PredictRunner, StatePayload

__all__ = ["FakeRunner", "PredictRunner", "StatePayload"]
