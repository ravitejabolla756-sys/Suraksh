"""Experimental trajectory-based accident analysis; no alert side effects."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from math import hypot
from typing import Sequence
from .contracts import EventFamily, InferenceRequest, ModelStatus, SafetyDetection, SafetyPerceptionResult
from .models import TemporalSafetyModel

@dataclass(frozen=True, slots=True)
class TrackObservation:
    track_id: int
    class_name: str
    bbox: tuple[float, float, float, float]
    zone: str | None = None
    pose: dict | None = None

    @property
    def center(self): return ((self.bbox[0]+self.bbox[2])/2, (self.bbox[1]+self.bbox[3])/2)

@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    timestamp: datetime
    center: tuple[float, float]
    speed: float

@dataclass(frozen=True, slots=True)
class TrackTrajectory:
    track_id: int
    points: tuple[TrajectoryPoint, ...]

class TrajectoryExtractor:
    def __init__(self, max_tracks=128, points_per_track=32):
        self.max_tracks, self.points_per_track = max_tracks, points_per_track
        self._history: dict[int, deque[TrajectoryPoint]] = {}
    def update(self, frame, observations):
        for obs in observations:
            points = self._history.setdefault(obs.track_id, deque(maxlen=self.points_per_track))
            previous = points[-1] if points else None
            dt = (frame.timestamp - previous.timestamp).total_seconds() if previous else 0
            speed = hypot(obs.center[0]-previous.center[0], obs.center[1]-previous.center[1]) / dt if previous and dt > 0 else 0
            points.append(TrajectoryPoint(frame.timestamp, obs.center, speed))
        for key in list(self._history)[self.max_tracks:]: del self._history[key]
        return tuple(TrackTrajectory(k, tuple(v)) for k, v in self._history.items())

@dataclass(frozen=True, slots=True)
class AccidentConfig:
    window_size: int = 16; persistence_frames: int = 3; confidence_threshold: float = .65
    collision_distance: float = 60; impact_deceleration: float = .3; minimum_approach_speed: float = 10
    deduplication_frames: int = 30
    def __post_init__(self):
        if self.window_size < self.persistence_frames or self.persistence_frames < 2: raise ValueError("invalid accident temporal policy")

class AccidentState:
    NORMAL="NORMAL"; SUSPICIOUS="SUSPICIOUS"; CANDIDATE="CANDIDATE"; CONFIRMED="CONFIRMED"; RESOLVED="RESOLVED"

@dataclass(frozen=True, slots=True)
class AccidentEvent:
    event_type: str; confidence: float; tracks: tuple[int, ...]; timestamp: datetime; state: str = AccidentState.CONFIRMED

class AccidentTemporalVerifier:
    def __init__(self, config=AccidentConfig()): self.config=config; self.history=deque(maxlen=config.window_size); self.states={}; self.last_event={}
    def observe(self, frame_index, observations, timestamp):
        self.history.append((frame_index, observations, timestamp)); events=[]
        vehicles=[o for o in observations if o.class_name=="vehicle"]
        for a in range(len(vehicles)):
            for b in range(a+1,len(vehicles)):
                distance=hypot(vehicles[a].center[0]-vehicles[b].center[0], vehicles[a].center[1]-vehicles[b].center[1])
                key=(vehicles[a].track_id,vehicles[b].track_id)
                suspicious=distance <= self.config.collision_distance
                self.states[key]=AccidentState.CANDIDATE if suspicious else AccidentState.NORMAL
                recent=sum(1 for _,items,_ in self.history if len([o for o in items if o.track_id in key])==2)
                if suspicious and recent >= self.config.persistence_frames and self.last_event.get(key,-10**9)+self.config.deduplication_frames < frame_index:
                    self.last_event[key]=frame_index; events.append(AccidentEvent("vehicle_collision", min(1, .5+self.config.confidence_threshold/2), key, timestamp))
        persons=[o for o in observations if o.class_name=="person" and o.pose and o.pose.get("posture")=="horizontal"]
        for person in persons:
            if self.last_event.get((person.track_id,),-10**9)+self.config.deduplication_frames < frame_index:
                self.last_event[(person.track_id,)]=frame_index; events.append(AccidentEvent("person_fall", self.config.confidence_threshold, (person.track_id,), timestamp))
        return events

@dataclass(frozen=True, slots=True)
class AccidentPerceptionFrame:
    tracks: tuple[TrackObservation, ...]

class ExperimentalAccidentModel(TemporalSafetyModel):
    event_family=EventFamily.ACCIDENT; model_id="trajectory-accident-experimental"; model_version="0.1"
    def __init__(self, config=AccidentConfig()): self.config=config
    async def infer(self, request: InferenceRequest):
        events=[]
        return SafetyPerceptionResult(self.event_family, request.frame.camera_id, self.model_id, self.model_version, tuple(SafetyDetection(e.event_type,e.confidence,attributes={"tracks":e.tracks}) for e in events), 0, (), request.temporal_window, 0, ModelStatus.READY)
    def event_payload(self, result): return {"event_type":"accident","camera_id":result.camera_id,"confidence":result.confidence,"model_version":result.model_version}

@dataclass(frozen=True, slots=True)
class AccidentMetrics: precision: float; recall: float; f1: float; false_alarm_rate: float; detection_delay: float | None; missed_accidents: int
def evaluate_accident_events(actual, predicted):
    tp=sum(a is not None and a==p for a,p in zip(actual,predicted)); fp=sum(p is not None and p!=a for a,p in zip(actual,predicted)); fn=sum(a is not None and a!=p for a,p in zip(actual,predicted)); precision=tp/(tp+fp) if tp+fp else 0; recall=tp/(tp+fn) if tp+fn else 0
    return AccidentMetrics(precision,recall,2*precision*recall/(precision+recall) if precision+recall else 0,fp/len(actual) if actual else 0,None,fn)
