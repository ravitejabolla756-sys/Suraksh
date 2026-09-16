# SURAKSH demo media

This directory is reserved for legitimate, non-sensitive CCTV test media used by
the hackathon demonstration. Do not commit private surveillance footage or
generated detection JSON.

For the non-Docker Windows path, place two short videos here:

- `vms-a.mp4`
- `vms-b.mp4`

Each file must visibly contain at least one vehicle. The edge worker decodes
these files with OpenCV, runs the configured Ultralytics model, attempts OCR
only on detected vehicle crops, and sends only observations produced by that
pipeline to the backend. A missing or unreadable file is a hard demo failure.

Recommended: use a rights-cleared sample from an openly licensed dataset and
record its source and licence in `SOURCE.md` beside the media. The files are
ignored by Git by default because source footage may be large or sensitive.
