"""Run the isolated Suraksh person/vehicle detector benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-ai"))

from app.perception.benchmark import PersonDetectionBenchmark, default_candidates, sample_video, write_report
from app.perception.dataset import decode_frame, load_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, help="approved ground-truth manifest")
    parser.add_argument("--video", type=Path, action="append", help="runtime-only source video")
    parser.add_argument("--candidate", action="append", dest="candidates")
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--output", type=Path,
                        default=ROOT / ".runtime" / "person-benchmark" / "results.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_frames < 1 or args.max_frames > 256:
        raise SystemExit("--max-frames must be between 1 and 256")
    if args.manifest:
        manifest = load_manifest(args.manifest.resolve())
        selected = manifest.frames[:args.max_frames]
        samples = [(annotation, decode_frame(annotation).frame) for annotation in selected]
        annotated = True
    else:
        videos = args.video or [ROOT / "demo-media" / "anpr-vms-a.mp4",
                                ROOT / "demo-media" / "OP.mp4"]
        per_video = max(1, args.max_frames // len(videos))
        samples = []
        for index, video in enumerate(videos):
            samples.extend(sample_video(video.resolve(), f"benchmark-{index + 1}", per_video))
        annotated = False
    benchmark = PersonDetectionBenchmark(ROOT, default_candidates(ROOT, set(args.candidates or [])))
    report = benchmark.run(samples, annotated)
    write_report(report, args.output.resolve())
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
