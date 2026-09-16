# Suraksh Model Promotion

Task 17 is acceptance-gated. The current acceptance report has no measured
winner, so no detector/tracker has been promoted. `ModelPromotionManager`
refuses candidates unless the report is explicitly accepted and health checks
pass. It retains the previous version and supports rollback; it never removes
the previous detector/tracker before rollback verification.

`PerCameraPerceptionConfig` provides per-camera detector model/resolution/
thresholds, tracker type/thresholds/buffer, ReID, fire/smoke model and safety
thresholds, and realtime/evaluation mode. Model version remains part of
results and promotion records. Business logic should consume this configuration
and model registry metadata rather than hardcoding model assumptions.
