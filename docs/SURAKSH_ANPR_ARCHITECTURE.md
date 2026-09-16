# Suraksh ANPR Architecture

## Design contract

ANPR is optional and disabled by default. It consumes confirmed vehicle tracks
from the existing timestamp-aware tracker; it never creates or renames a track.
Identity is `(organization, camera, tracker session, track ID)`. A replay or
tracker restart creates a new session. Person tracking remains independent.

Flow: tracked source frame → sampled plate detector → conservative association
→ quality gate → optional mild preprocessing → replaceable OCR → configurable
regional validation → bounded temporal consensus → encrypted result/evidence.

Implementation phases: (1) contracts, association and fusion; (2) persistence,
authorization and runtime integration; (3) opt-in investigation UI; (4) annotated
evaluation and regression verification. This file records the intended boundary
before implementation; operational details and measured verification follow.

## Decisions

- Every observation retains the source frame index and source timestamp. Wall
  clock observation time is separate from video-relative source time.
- Duplicate frames, ambiguous overlapping vehicles, poor crops, invalid OCR,
  excessive disagreement and insufficient observations cannot confirm a result.
- Voting may use per-character confidence, but cannot invent an unseen string:
  the winning normalized text must have been observed on multiple frames.
- Each camera has a latest-only background queue. Detection is sampled; known
  plates are checked less often. A discontinuity or conflicting reading revokes
  stability and returns the track to the faster sampling schedule.
- No external model is downloaded. Runtime activation requires a versioned,
  hash-verified local model bundle with recorded licensing review.
- The planned persistence boundary will encrypt result payloads and original/crop
  PNG evidence at rest. Exact search will use a tenant-bound HMAC index; arbitrary
  global search will be unavailable.
- The planned API boundary will be authenticated, organization-scoped and
  role-controlled. Searches will use POST bodies to avoid putting plate text in
  access-log URLs.
- The planned retention worker will exclude expired results at read time and
  remove them in bounded sweeps. Evidence will be deleted with its result.
  Audit events will contain identifiers and counts, never plate strings or
  search terms.

## Boundaries

The current code has no durable ANPR result/evidence adapter yet. The next
implementation phase must place one behind the API boundary, then move evidence
to an encrypted object store, partition results by tenant/time, and assign camera
ownership to workers at fleet scale. No statewide throughput is claimed.

Synthetic contract fixtures verify software behavior. They do not establish
detector/OCR accuracy. Real annotated evaluation and license approval are release
gates; this feature must not be described as production-ready before they pass.
