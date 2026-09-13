# Versioned detection validation dataset

The repository contains the runner and manifest format, not private competition video.
Create a versioned directory outside Git, copy `manifest.example.json`, and reference
real, consented clips with stable expected take-off frame annotations. Each case records
the board ROI, judge-selected freeze frame, accepted frame tolerance, and processing
width. Run `py -3 tools/detection_validation.py <manifest>` before changing detection.

Increment `dataset_version` only when clips or human annotations change. Record the app
commit as `algorithm_version`. Reports are machine-readable and let releases compare
accuracy, missed detections, and processing time without exposing athlete footage.

Do not commit real athlete footage, names, bibs, or generated reports containing private
paths. Synthetic fixtures may be committed under `validation/fixtures/`.
