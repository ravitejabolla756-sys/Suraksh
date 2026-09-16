# Suraksh Person Model Evaluation

## Comparison

Compare the selected detector’s original pretrained checkpoint against the
Suraksh fine-tuned checkpoint using the same completely held-out test split,
source frames, preprocessing, confidence/NMS policy, and hardware. The
validation split is for training decisions only; it must not be used to report
final quality.

Report precision, recall, F1, AP50, AP50:95, false positives, false
negatives, and domain strata including tiny/distant, nighttime, crowded,
occluded, near-vehicle, indoor, and outdoor scenes. Also report preprocessing,
inference, postprocessing, end-to-end latency, FPS, CPU, RAM, and available
GPU metrics.

No metrics are reported until an approved, annotated, held-out test set is
available. Published model-card or internet values are context only and must
not be presented as Suraksh measurements. A fine-tuned model is not promoted
automatically.
