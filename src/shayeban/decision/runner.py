"""Offline runner port matching the surveyed laya-lab decide() contract."""

from copy import deepcopy
from typing import Any, Protocol

# Any is intentional at the upstream transport boundary. Question schemas and
# validated domain answers belong to the typed adapter, not this runner port.
type StatePayload = str | dict[str, Any] | list[Any]


class PredictRunner(Protocol):
    """One synchronous port shared by detection, stance and verdict passes."""

    def decide(
        self,
        state: StatePayload,
        schema: Any = None,
        *,
        questions: dict[str, Any] | None = None,
        return_details: bool = False,
        **predict_kwargs: Any,
    ) -> Any: ...


class FakeRunner:
    """Return a fixed configured answer and snapshot the latest call.

    Construct one fake per configured pass (or reuse it for identical answers).
    Responses use the upstream choice/score/noul envelope unchanged. No inference,
    question interpretation, answer validation or return_details emulation occurs.
    Configure the exact response your caller expects, including detail payloads.
    Copies isolate configuration, returned answers and observed mutable inputs.
    """

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = deepcopy(response)
        self.seen_state: StatePayload | None = None
        self.seen_schema: Any = None
        self.seen_questions: dict[str, Any] | None = None
        self.seen_return_details = False
        self.seen_predict_kwargs: dict[str, Any] = {}

    def decide(
        self,
        state: StatePayload,
        schema: Any = None,
        *,
        questions: dict[str, Any] | None = None,
        return_details: bool = False,
        **predict_kwargs: Any,
    ) -> dict[str, Any]:
        self.seen_state = deepcopy(state)
        self.seen_schema = schema
        self.seen_questions = deepcopy(questions)
        self.seen_return_details = return_details
        self.seen_predict_kwargs = deepcopy(predict_kwargs)
        return deepcopy(self._response)
