# Versioned detection validation dataset

The repository contains the runner and manifest format, not private competition video.
Create a versioned directory outside Git, copy `manifest.example.json`, and reference
real, consented clips with stable expected take-off frame and verdict annotations. Schema
2 records the board and foul-line calibration, expected advisory, shoe visibility, accepted
frame tolerance, and processing width. Schema 1 remains readable for older frame-only
datasets. Run `py -3 tools/detection_validation.py <manifest>` before changing detection.

Increment `dataset_version` only when clips or human annotations change. Record the app
commit as `algorithm_version`. Reports are machine-readable and let releases compare
accuracy, missed detections, and processing time without exposing athlete footage.

Do not commit real athlete footage, names, bibs, or generated reports containing private
paths. Synthetic fixtures may be committed under `validation/fixtures/`.

Automatic advice is a release-gated decision-support feature. A production model/version
must be frozen and evaluated on clips from every supported camera angle, footwear colour,
lighting condition, frame rate, and complete/partial shoe visibility class. Partial visibility
may support a Foul advisory when the crossing edge is visible, but it must never produce a
Valid advisory. Keep false confident advice below the agreed release threshold (target 1%)
and report Review rate separately; Review is the safe result, not a failed test unless the
case expects a confident answer.
