"""Conservative spatial association; ambiguity causes deferral, not identity swaps."""
from .contracts import BBox, PlateDetection, VehicleTrack


def intersection(a: BBox, b: BBox) -> float:
    return max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))


def continuous(previous: VehicleTrack, current: VehicleTrack, max_gap: float) -> bool:
    dt = current.source_timestamp - previous.source_timestamp
    a, b = previous.bbox, current.bbox
    area_a, area_b = (a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])
    displacement = ((a[0]+a[2]-b[0]-b[2])**2 + (a[1]+a[3]-b[1]-b[3])**2)**.5 / 2
    return (previous.key == current.key and previous.vehicle_class == current.vehicle_class and 0 < dt <= max_gap
            and .25 <= area_b/area_a <= 4 and displacement <= max(a[2]-a[0], a[3]-a[1]))


def associate(plate: PlateDetection, tracks: list[VehicleTrack], previous_positions: dict) -> VehicleTrack | None:
    box = plate.bbox
    area = (box[2]-box[0])*(box[3]-box[1])
    candidates = []
    for track in tracks:
        if track.source_frame_index != plate.source_frame_index or abs(track.source_timestamp-plate.source_timestamp) > 1e-6:
            continue
        v = track.bbox
        contained = intersection(v, box) / area
        cx, cy = ((box[0]+box[2])/2-v[0])/(v[2]-v[0]), ((box[1]+box[3])/2-v[1])/(v[3]-v[1])
        relative_area = area / ((v[2]-v[0])*(v[3]-v[1]))
        if contained < .95 or not (.05 <= cx <= .95 and .15 <= cy <= .98) or not .0005 <= relative_area <= .4:
            continue
        candidates.append((track, (cx, cy)))
    # Even a previous match cannot disambiguate overlapping current vehicles safely.
    if len(candidates) != 1:
        return None
    track, position = candidates[0]
    previous = previous_positions.get(track.key)
    if previous and max(abs(position[i]-previous[i]) for i in (0, 1)) > .25:
        return None
    return track


def relative_position(plate: PlateDetection, track: VehicleTrack) -> tuple[float, float]:
    p, v = plate.bbox, track.bbox
    return ((p[0]+p[2])/2-v[0])/(v[2]-v[0]), ((p[1]+p[3])/2-v[1])/(v[3]-v[1])
