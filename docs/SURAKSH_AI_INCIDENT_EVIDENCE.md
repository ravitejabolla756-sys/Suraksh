# Suraksh AI Incident Evidence

Confirmed safety candidates can use the bounded `TemporalEvidenceEngine` to
retain references to triggering, pre-event, event, and post-event frames.
References point to existing recording/evidence storage; decoded pixels and
unlimited video are not retained in the engine. Track IDs and the rolling
track-history points remain attached to the temporal evidence.

`EvidenceAccessPolicy` filters references by organization and camera ownership.
`public_payload()` removes local filesystem paths; APIs must expose only
authorized opaque recording/frame references. Missing evidence and unknown
resolution requests return empty results safely.

Accident evidence should use the configured temporal window around the impact.
Fire/smoke evidence should include multiple persistent observations. Incident
resolution is represented as an evidence-engine cleanup/resolve operation;
operational lifecycle and authorization remain enforced by the existing
Incident Engine and API dependencies.
