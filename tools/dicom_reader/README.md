## DICOM Reader

**Author:** langgenius  
**Version:** 0.0.1  
**Type:** Tool

### Description
- Parses DICOM Part 10 files using pydicom.
- Extracts structured patient, study, series, and image metadata.
- Optionally samples pixel data to compute descriptive statistics.
- Generates a min-max normalised PNG preview that is downsampled to remain small.

### Parameters
- `dicom_file` *(file, required)*: The DICOM file (.dcm) to inspect.
- `include_pixel_statistics` *(boolean)*: Compute min/mean/max/std and percentiles from pixel data (uses sampling for large datasets).
- `include_preview_image` *(boolean)*: Return a downsampled PNG preview of the selected frame as an attached image file.
- `preview_frame_index` *(number)*: Frame index (0-based) to preview when multiple frames exist.
- `max_preview_edge` *(number)*: Maximum edge length for the generated preview (32–1024 px).
- `additional_tags` *(string)*: Optional comma-separated tag names or hex codes to include (e.g. `PatientAge,0018,5100`).

### Large File Strategy
- Metadata extraction uses `stop_before_pixels` unless statistics or previews are requested, so headers from >20 MB files remain light-weight.
- Pixel statistics operate on a sampled subset (default ≤262,144 pixels) to balance fidelity and size.
- Preview images are normalised to 8-bit and resized to keep responses well under 20 MB even for very high-resolution studies.

### Output
- JSON payload containing `metadata`, optional `pixel_statistics`, optional `preview` metadata, and diagnostic `notes`.
- When a preview is requested the PNG image is delivered via a binary file message (no base64 in JSON), keeping responses compact.
- Human-readable text summary that highlights key findings and indicates any skipped operations.
