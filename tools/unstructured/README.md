# Unstructured Partition API

**Author:** langgenius  
**Version:** 0.0.1  
**Type:** tool

---

## Partition Input Parameters

The Unstructured Partition Endpoint provides parameters to customize the processing of documents.

> **The only required parameter is `files`** – the file you wish to process.

---

### Main Parameters

| Python / POST                           | JavaScript/TypeScript                | Description                                                                                                                                                                                                                                       |
| --------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `files` (shared.Files)                  | `files` (File, Blob, shared.Files)   | **Required.** The file to process.                                                                                                                                                                                                                |
| `chunking_strategy` (str)               | `chunkingStrategy` (string)          | Use one of the supported strategies to chunk the returned elements after partitioning. When not specified, no chunking is performed and any other chunking parameters are ignored.<br>Supported: `basic`, `by_title`, `by_page`, `by_similarity`. |
| `content_type` (str)                    | `contentType` (string)               | A hint about the content type to use (such as `text/markdown`), when there are problems processing a specific file. This value is a MIME type in the format `type/subtype`.                                                                       |
| `coordinates` (bool)                    | `coordinates` (boolean)              | `true` to return bounding box coordinates for each element extracted with OCR. Default: `false`.                                                                                                                                                  |
| `encoding` (str)                        | `encoding` (string)                  | The encoding method used to decode the text input. Default: `utf-8`.                                                                                                                                                                              |
| `extract_image_block_types` (List[str]) | `extractImageBlockTypes` (string[])  | The types of elements to extract as Base64 encoded data in element metadata fields, e.g. `["Image","Table"]`. Supported filetypes: image and PDF.                                                                                                 |
| `gz_uncompressed_content_type` (str)    | `gzUncompressedContentType` (string) | If file is gzipped, use this content type after unzipping. Example: `application/pdf`                                                                                                                                                             |
| `hi_res_model_name` (str)               | `hiResModelName` (string)            | The name of the inference model used when strategy is `hi_res`. Options: `layout_v1.1.0`, `yolox`. Default: `layout_v1.1.0`.                                                                                                                      |
| `include_page_breaks` (bool)            | `includePageBreaks` (boolean)        | `true` for the output to include page breaks if the filetype supports it. Default: `false`.                                                                                                                                                       |
| `languages` (List[str])                 | `languages` (string[])               | The languages present in the document, for use in partitioning and OCR.                                                                                                                                                                           |
| `output_format` (str)                   | `outputFormat` (string)              | The format of the response. Supported: `application/json`, `text/csv`. Default: `application/json`.                                                                                                                                               |
| `pdf_infer_table_structure` (bool)      | `pdfInferTableStructure` (boolean)   | **Deprecated!** Use `skip_infer_table_types` instead. If `true` and strategy is `hi_res`, any Table elements extracted from a PDF will include an additional metadata field, `text_as_html`, with the HTML table.                                 |
| `skip_infer_table_types` (List[str])    | `skipInferTableTypes` (string[])     | The document types to skip table extraction for. Default: `[]`.                                                                                                                                                                                   |
| `starting_page_number` (int)            | `startingPageNumber` (number)        | The page number to assign to the first page in the document. This will be included in elements’ metadata.                                                                                                                                         |
| `strategy` (str)                        | `strategy` (string)                  | The strategy to use for partitioning PDF and image files. Options: `auto`, `vlm`, `hi_res`, `fast`, `ocr_only`. Default: `auto`.                                                                                                                  |
| `unique_element_ids` (bool)             | `uniqueElementIds` (boolean)         | `true` to assign UUIDs to element IDs (guarantees uniqueness). Otherwise, a SHA-256 of the element’s text is used. Default: `false`.                                                                                                              |
| `vlm_model` (str)                       | *(Not yet available)*                | Applies only when strategy is `vlm`. The name of the vision language model (VLM) provider to use for partitioning. `vlm_model_provider` must also be specified.                                                                                   |
| `vlm_model_provider` (str)              | *(Not yet available)*                | Applies only when strategy is `vlm`. The name of the vision language model (VLM) to use for partitioning. `vlm_model` must also be specified.                                                                                                     |
| `xml_keep_tags` (bool)                  | `xmlKeepTags` (boolean)              | `true` to retain the XML tags in the output. Otherwise, only the text within the tags is extracted. Only applies to XML documents.                                                                                                                |

---

### Chunking Parameters

> The following parameters only apply when a chunking strategy is specified. Otherwise, they are ignored.

| Python / POST                  | JavaScript/TypeScript           | Description                                                                                                                                                                                          |
| ------------------------------ | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `combine_under_n_chars` (int)  | `combineUnderNChars` (number)   | Applies only when the chunking strategy is set to `by_title`. Combines small chunks until the combined chunk reaches a length of n characters. Default: same as `max_characters`.                    |
| `include_orig_elements` (bool) | `includeOrigElements` (boolean) | `true` (default) to have the elements used to form a chunk appear in `.metadata.orig_elements` for that chunk.                                                                                       |
| `max_characters` (int)         | `maxCharacters` (number)        | Cut off new sections after reaching a length of n characters. (Hard maximum.) Default: `500`.                                                                                                        |
| `multipage_sections` (bool)    | `multipageSections` (boolean)   | Applies only when the chunking strategy is set to `by_title`. Determines if a chunk can include elements from more than one page. Default: `true`.                                                   |
| `new_after_n_chars` (int)      | `newAfterNChars` (number)       | Applies only when the chunking strategy is specified. Cuts off new sections after reaching a length of n characters. (Soft maximum.) Default: `1500`.                                                |
| `overlap` (int)                | `overlap` (number)              | A prefix of this many trailing characters from the prior text-split chunk is applied to second and later chunks formed from oversized elements by text-splitting. Default: none.                     |
| `overlap_all` (bool)           | `overlapAll` (boolean)          | `true` to have an overlap also applied to “normal” chunks formed by combining whole elements. Use with caution, as this can introduce noise into otherwise clean semantic units.                     |
| `similarity_threshold` (float) | `similarityThreshold` (number)  | Applies only when the chunking strategy is set to `by_similarity`. The minimum similarity text in consecutive elements must have to be included in the same chunk. Range: 0.01–0.99. Default: `0.5`. |

---

### Client-Specific Parameters (Not sent to server)

| Python / POST                       | JavaScript/TypeScript               | Description                                                                                                                                                             |
| ----------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `split_pdf_page` (bool)             | `splitPdfPage` (boolean)            | `true` to split the PDF file client-side.                                                                                                                               |
| `split_pdf_allow_failed` (bool)     | `splitPdfAllowFailed` (boolean)     | When `true`, a failed split request will not stop the processing of the rest of the document. The affected page range will be ignored in the results. Default: `false`. |
| `split_pdf_concurrency_level` (int) | `splitPdfConcurrencyLevel` (number) | The number of split files to be sent concurrently. Default: `5`. Maximum: `15`.                                                                                         |
| `split_pdf_page_range` (List[int])  | `splitPdfPageRange` (number[])      | A list of 2 integers within the range `[1, length_of_pdf]`. When PDF splitting is enabled, this will send only the specified page range to the API.                     |

---

## Notes

- For more details on each parameter, refer to the official documentation.
- Some parameters are only available in specific strategies or file types.
- Default values are shown where applicable.

---

## API Response Structure

### Top-Level Fields

| Field      | Type            | Description                                                                  |
| ---------- | --------------- | ---------------------------------------------------------------------------- |
| `text`     | string          | The full parsed content in Markdown format, including images, sections, etc. |
| `files`    | array           | List of attached files (if any).                                             |
| `json`     | array           | Structured JSON data (if any).                                               |
| `images`   | array of object | List of image objects extracted from the content.                            |
| `elements` | array of object | List of structured content blocks (sections, paragraphs, images, etc).       |

---

### Field Details

#### text

- **Type:** string  
- **Description:**  
  The entire content, formatted in Markdown. This may include images, headings, bullet points, and other formatting for direct rendering.

#### files

- **Type:** array  
- **Description:**  
  List of attached files. Typically empty in the current output.

#### json

- **Type:** array  
- **Description:**  
  Structured JSON data for advanced use cases. Typically empty in the current output.

#### images

- **Type:** array of objects  
- **Description:**  
  List of images found in the content. Each image object contains the following fields:

| Field         | Type    | Description                   |
| ------------- | ------- | ----------------------------- |
| `extension`   | string  | File extension (e.g., `.png`) |
| `id`          | string  | Unique image ID               |
| `mime_type`   | string  | MIME type of the image        |
| `name`        | string  | Image file name               |
| `preview_url` | string  | URL for image preview         |
| `size`        | integer | Image file size in bytes      |
| `type`        | string  | Always `"image"`              |

**Example:**

```json
[
  {
    "extension": ".png",
    "id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
    "mime_type": "image/png",
    "name": "weather-forecast.png",
    "preview_url": "https://example.com/files/tools/a1b2c3d4-5678-90ab-cdef-1234567890ab.png",
    "size": 20480,
    "type": "image"
  }
]
```

---

#### elements

- **Type:** array of objects  
- **Description:**  
  List of structured content blocks. Each object represents a section, paragraph, image, or other content element.

| Field        | Type   | Description                                                                       |
| ------------ | ------ | --------------------------------------------------------------------------------- |
| `element_id` | string | Unique identifier for the element                                                 |
| `metadata`   | object | Metadata for the element (see below for details)                                  |
| `text`       | string | The text content of the element                                                   |
| `type`       | string | The type of element (e.g., `Title`, `NarrativeText`, `Image`, `CompositeElement`) |

##### metadata (object)

The `metadata` field provides detailed information about the element's origin, layout, and context.  
Possible fields include (not all fields are present in every element):

| Field                  | Type    | Description                                             |
| ---------------------- | ------- | ------------------------------------------------------- |
| `filename`             | string  | Name of the source file (e.g., `weather-report.pdf`)    |
| `filetype`             | string  | MIME type or file type (e.g., `application/pdf`, `PPM`) |
| `languages`            | array   | List of detected languages (e.g., `["eng"]`)            |
| `page_number`          | integer | Page number in the source file (if applicable)          |
| `coordinates`          | object  | Layout information (see below)                          |
| `detection_class_prob` | float   | Confidence score for element detection (0-1)            |
| `image_mime_type`      | string  | MIME type for images (e.g., `image/png`)                |
| `dify_file_id`         | string  | Unique file ID for images                               |
| `preview_url`          | string  | Preview URL for images                                  |
| `orig_elements`        | array   | List of original sub-elements (for composite elements)  |

###### coordinates (object)

Describes the position and size of the element in the source file (if available):

| Field           | Type    | Description                                         |
| --------------- | ------- | --------------------------------------------------- |
| `layout_height` | integer | Height of the layout (e.g., page height in pixels)  |
| `layout_width`  | integer | Width of the layout (e.g., page width in pixels)    |
| `points`        | array   | List of four [x, y] coordinate pairs (bounding box) |
| `system`        | string  | Coordinate system used (e.g., `PixelSpace`)         |

---

### Example Response

```json
{
  "text": "![Weather Chart](https://example.com/files/tools/a1b2c3d4-5678-90ab-cdef-1234567890ab.png)\n\n# Weekly Weather Report\n\n## Overview\n\nThis week will see a mix of sunny and rainy days across the region.\n\n## Details\n\n- **Monday:** Sunny, 25°C\n- **Tuesday:** Cloudy, 22°C\n- **Wednesday:** Rainy, 18°C\n- **Thursday:** Thunderstorms, 20°C\n- **Friday:** Partly Cloudy, 23°C\n",
  "files": [],
  "json": [],
  "images": [
    {
      "extension": ".png",
      "id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
      "mime_type": "image/png",
      "name": "weather-forecast.png",
      "preview_url": "https://example.com/files/tools/a1b2c3d4-5678-90ab-cdef-1234567890ab.png",
      "size": 20480,
      "type": "image"
    }
  ],
  "elements": [
    {
      "element_id": "xyz123abc456",
      "metadata": {
        "filename": "weather-report.pdf",
        "filetype": "application/pdf",
        "languages": ["eng"],
        "page_number": 1,
        "coordinates": {
          "layout_height": 2000,
          "layout_width": 1500,
          "points": [
            [100, 200],
            [100, 400],
            [600, 400],
            [600, 200]
          ],
          "system": "PixelSpace"
        },
        "detection_class_prob": 0.92
      },
      "text": "Weather Forecast\n\n- Monday: Sunny, 25°C\n- Tuesday: Cloudy, 22°C\n- Wednesday: Rainy, 18°C",
      "type": "CompositeElement"
    },
    {
      "element_id": "img789def012",
      "metadata": {
        "filename": "weather-report.pdf",
        "filetype": "PPM",
        "languages": ["eng"],
        "page_number": 1,
        "coordinates": {
          "layout_height": 2000,
          "layout_width": 1500,
          "points": [
            [1200, 100],
            [1200, 400],
            [1450, 400],
            [1450, 100]
          ],
          "system": "PixelSpace"
        },
        "detection_class_prob": 0.98,
        "dify_file_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
        "image_mime_type": "image/png",
        "preview_url": "https://example.com/files/tools/a1b2c3d4-5678-90ab-cdef-1234567890ab.png"
      },
      "text": "",
      "type": "Image"
    }
  ]
}
```

---

## Notes

- The `text` field is suitable for direct display in web or app frontends.
- The `elements` field is useful for structured processing, highlighting, or further analysis.
- The `images` field provides all image resources for preview or download.
- The `files` and `json` fields are reserved for future use or advanced scenarios.
- The `metadata` object in each element may contain additional fields depending on the extraction process and file type.

---
