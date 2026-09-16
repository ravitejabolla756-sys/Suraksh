"""Common model contract; concrete model implementations belong elsewhere."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from .contracts import EventFamily, InferenceRequest, SafetyPerceptionResult


class SafetyModel(ABC):
    """Every safety model exposes the same async inference boundary."""

    event_family: ClassVar[EventFamily]
    model_id: ClassVar[str]
    model_version: ClassVar[str]

    @property
    @abstractmethod
    def is_temporal(self) -> bool:
        """Whether inference requires the request's bounded temporal window."""

    @abstractmethod
    async def infer(self, request: InferenceRequest) -> SafetyPerceptionResult:
        """Infer one result without publishing alerts or mutating application state."""


class FrameSafetyModel(SafetyModel):
    """Base contract for one-frame detectors."""

    is_temporal = False


class TemporalSafetyModel(SafetyModel):
    """Base contract for bounded video/temporal detectors."""

    is_temporal = True
