"""Acceptance-gated model promotion and rollback primitives."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class PromotionCandidate:
    detector_model: str
    detector_version: str
    tracker_type: str
    report_status: str
    acceptance_passed: bool

@dataclass(frozen=True, slots=True)
class PromotionResult:
    promoted: bool
    reason: str
    active_version: str | None
    previous_version: str | None

class ModelPromotionManager:
    """Keeps prior configuration until health verification succeeds."""
    def __init__(self): self._active: dict[str, PromotionCandidate] = {}; self._previous: dict[str, PromotionCandidate] = {}
    def promote(self, camera_id: str, candidate: PromotionCandidate, health: dict[str, Any] | None = None) -> PromotionResult:
        if candidate.report_status != "accepted" or not candidate.acceptance_passed:
            return PromotionResult(False, "acceptance report has not passed all gates", self.version(camera_id), self.previous_version(camera_id))
        if health is not None and health.get("healthy") is not True:
            return PromotionResult(False, "candidate health check failed", self.version(camera_id), self.previous_version(camera_id))
        old = self._active.get(camera_id)
        if old: self._previous[camera_id] = old
        self._active[camera_id] = candidate
        return PromotionResult(True, "promoted after acceptance and health checks", candidate.detector_version, old.detector_version if old else None)
    def rollback(self, camera_id: str) -> PromotionResult:
        old = self._previous.get(camera_id)
        if old is None: return PromotionResult(False, "no verified previous model available", self.version(camera_id), None)
        current = self._active.get(camera_id); self._active[camera_id] = old; self._previous[camera_id] = current
        return PromotionResult(True, "rolled back to previous model", old.detector_version, current.detector_version if current else None)
    def version(self, camera_id): return self._active[camera_id].detector_version if camera_id in self._active else None
    def previous_version(self, camera_id): return self._previous[camera_id].detector_version if camera_id in self._previous else None
