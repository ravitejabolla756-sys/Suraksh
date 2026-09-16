"""Inspectable trajectory evidence, without detecting an 'accident' image class."""

from dataclasses import asdict, dataclass
from datetime import datetime
from math import hypot

from .config import AccidentConfig
from .tracking import TrackObservation, Trajectory

VEHICLE_CLASSES = frozenset({"vehicle", "car", "truck", "bus", "motorcycle", "bicycle"})


@dataclass(frozen=True, slots=True)
class AccidentFeatureRecord:
    camera_id: str
    timestamp: datetime
    source_frame_index: int
    track_ids: tuple[int, ...]
    classes: tuple[str, ...]
    positions: tuple[tuple[float, float], ...]
    velocities: tuple[tuple[float, float], ...]
    accelerations: tuple[tuple[float, float], ...]
    headings: tuple[float | None, ...]
    distance: float | None
    relative_velocity: tuple[float, float] | None
    closing_speed: float
    trajectory_intersection: bool
    closest_approach_distance: float | None
    time_to_closest_approach: float | None
    overlap: float
    deceleration: float
    speed_drop_ratio: float
    heading_change: float
    stationary: bool
    visual_impact: float
    fallen: bool
    zone_consistent: bool
    scene_state: str
    coordinate_units: str
    calibration_version: str
    motion_valid: bool

    def payload(self) -> dict:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


def _iou(first, second) -> float:
    overlap = max(0, min(first[2], second[2])-max(first[0], second[0])) * max(0, min(first[3], second[3])-max(first[1], second[1]))
    union = (first[2]-first[0])*(first[3]-first[1]) + (second[2]-second[0])*(second[3]-second[1])-overlap
    return overlap / union if union else 0.0


def extract_features(camera_id: str, observations: tuple[TrackObservation, ...],
                     trajectories: tuple[Trajectory, ...], config: AccidentConfig,
                     units: str, calibration_version: str, scene_state: str) -> AccidentFeatureRecord:
    points = tuple(item.points[-1] for item in trajectories)
    first = points[0]
    distance = closest = time_to_closest = relative = None
    closing = overlap = 0.0
    intersection = False
    if len(points) == 2:
        displacement = tuple(points[1].center[i] - first.center[i] for i in (0, 1))
        relative = tuple(points[1].velocity[i] - first.velocity[i] for i in (0, 1))
        distance = hypot(*displacement)
        prior_distance = None
        if all(len(item.points) >= 2 for item in trajectories):
            prior = tuple(item.points[-2] for item in trajectories)
            prior_distance = hypot(*(prior[1].center[i] - prior[0].center[i] for i in (0, 1)))
            elapsed = max((first.timestamp - prior[0].timestamp).total_seconds(), 1e-9)
            closing = (prior_distance - distance) / elapsed
        dot = sum(displacement[i]*relative[i] for i in (0, 1))
        relative_squared = sum(v*v for v in relative)
        if relative_squared > 1e-9:
            time_to_closest = -dot / relative_squared
            closest = hypot(*(displacement[i] + relative[i]*time_to_closest for i in (0, 1)))
            intersection = distance <= config.collision_distance or (0 < time_to_closest <= config.trajectory_horizon_seconds and closest <= config.collision_distance)
        else:
            closest = distance
            intersection = distance <= config.collision_distance
        overlap = _iou(observations[0].box, observations[1].box)
    drops = []
    for trajectory in trajectories:
        if len(trajectory.points) >= 3 and trajectory.points[-2].speed >= config.minimum_approach_speed:
            drops.append(max(0.0, 1-trajectory.points[-1].speed/trajectory.points[-2].speed))
    return AccidentFeatureRecord(
        camera_id, first.timestamp, first.frame_sequence,
        tuple(item.track_id for item in observations), tuple(item.label for item in observations),
        tuple(item.center for item in points), tuple(item.velocity for item in points),
        tuple(item.acceleration_vector for item in points), tuple(item.heading for item in points),
        distance, relative, closing, intersection, closest, time_to_closest, overlap,
        max(max(0.0, -item.acceleration) for item in points), max(drops, default=0.0),
        max(item.heading_change for item in points),
        all(item.speed <= config.stationary_speed for item in points),
        max((item.visual_evidence.get(signal, 0.0) for item in observations
             for signal in ("impact", "deformation", "ejection")), default=0.0),
        any(item.label == "person" and item.pose.get("posture") in {"fallen", "horizontal"} for item in observations),
        len({item.zone for item in observations if item.zone is not None}) <= 1,
        scene_state, units, calibration_version, all(item.motion_valid for item in points),
    )
