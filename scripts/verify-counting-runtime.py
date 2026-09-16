"""Sample both running cameras; save sustained counting and freshness evidence."""
import json
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
rows = {name:[] for name in ('anpr-vms-a.mp4','anpr-vms-b.mp4','OP.mp4')}
for tick in range(45):
    for name in rows:
        with urlopen(f'http://127.0.0.1:8000/demo-media/{name}/runtime',timeout=5) as response:
            data = json.load(response)
        rows[name].append(data)
    time.sleep(1)
summary = {}
for name,samples in rows.items():
    steady = samples[10:]
    frames = {(r.get('epoch'),r.get('detection_frame')) for r in steady}
    summary[name] = {'samples':len(steady),'fresh_samples':sum(r.get('status')=='TRACKING' for r in steady),
        'distinct_detector_frames':len(frames),'vehicle_counts':[r.get('vehicles') for r in steady],
        'ai_fps':steady[-1].get('ai_fps'),'preview_fps':steady[-1].get('preview_fps'),
        'max_detection_age_ms':max((r.get('detection_age_ms') or 0) for r in steady),
        'errors':[r['ai_error'] for r in steady if r.get('ai_error')]}
out = ROOT/'.runtime'/'counting-verification.json'
out.write_text(json.dumps({'summary':summary,'samples':rows},indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
assert all(v['fresh_samples']>=30 and v['distinct_detector_frames']>=25 and not v['errors'] for v in summary.values()), 'Sustained counting verification failed'
