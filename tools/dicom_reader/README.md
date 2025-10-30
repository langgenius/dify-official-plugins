## DICOM Reader (Split Tools)

Author: langgenius  
Version: 0.0.2  
Type: Plugin (multiple tools)

### Overview
This plugin now provides focused DICOM tools, split from the original monolithic reader. Each tool does one job well and keeps outputs compact for LLMs.

Refactor highlights:
- Extracted common helpers into `tools/dicom_reader/tools/_utils.py` to reduce duplication.
- Unified preview image generation with a consistent size cap and resizing policy.
- Standardized frame selection, type coercion, and simple parsing utilities across tools.

Available tools and typical use cases:

- dicom_metadata
  - Purpose: Load patient/study/series/image tags and optional extra tags
  - Example: ds = pydicom.dcmread(file)

- dicom_pixels
  - Purpose: Summarize pixel array (shape/dtype/stats) with optional preview
  - Example: img = ds.pixel_array

- dicom_multiframe
  - Purpose: Read multi-frame CT/MRI, report frame count, preview a frame
  - Example: ds.NumberOfFrames

- dicom_hu_correction
  - Purpose: Apply RescaleSlope/Intercept; return stats and a preview
  - Example: hu = img * slope + intercept

- dicom_spatial
  - Purpose: Extract pixel spacing, slice thickness, orientation/position; compute voxel size/volume

- dicom_pixel_ops
  - Purpose: Add/subtract, normalize, clip, contrast stretch, box blur; returns preview

- dicom_stats
  - Purpose: Mean/variance/std and histogram on full image or rectangular ROI

- dicom_volume
  - Purpose: Threshold-based mask with spacing to estimate volume (mm³) and mean intensity

- dicom_threshold_mask
  - Purpose: Build a binary mask from thresholds and return overlay preview

- dicom_roi
  - Purpose: Compute stats inside a rectangular ROI; optional outlined preview

- dicom_model_input
  - Purpose: Convert to standard model shape [1, C, H, W] (or NHWC); optional normalization and preview

The original combined tool (tools/dicom_reader.yaml) remains for backwards compatibility.

### Common Parameters
- dicom_file (file, required): DICOM Part 10 (.dcm) file to process
- frame_index (number): 0-based frame index for multi-frame data (tools that use frames)
- max_preview_edge (number): Max preview edge (32–1024) for tools that output images

### Large File Strategy
- Where possible, headers are parsed with `stop_before_pixels` to keep responses small.
- Tools that operate on pixel data avoid returning full arrays; instead they report stats and attach small PNG previews (soft-capped to ~8 MB per image).

### Shared Utilities
- `as_bool/as_int/as_float`: consistent parameter parsing
- `select_frame`: robust multi-frame indexing across shapes
- `ensure_hw_or_hwc` and `to_uint8_minmax`: reliable image normalization
- `make_preview_png_bytes`: preview generation with edge clamping and byte-size cap
- Metadata helpers (`file_stats`, `collect_named_fields`, `parse_tag_keyword`, etc.) for compact, human-friendly output

### Notes
- No external credentials required.
- Outputs are JSON and small binary attachments (PNG) only; no base64 in JSON payloads.
