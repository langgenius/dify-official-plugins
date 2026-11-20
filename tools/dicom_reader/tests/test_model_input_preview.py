import io

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from tools.dicom_model_input import DicomModelInputTool


class _File:
    def __init__(self, blob: bytes, filename: str = "scan.dcm") -> None:
        self.blob = blob
        self.filename = filename


def _dicom_bytes(rows: int = 8, columns: int = 8, channels: int = 1) -> bytes:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = meta
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.Rows = rows
    ds.Columns = columns
    ds.SamplesPerPixel = channels
    ds.PhotometricInterpretation = "RGB" if channels == 3 else "MONOCHROME2"
    if channels == 3:
        ds.PlanarConfiguration = 0
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.PixelData = np.arange(rows * columns * 3, dtype=np.uint8).tobytes()
    else:
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.PixelData = np.arange(rows * columns, dtype=np.uint16).tobytes()

    buffer = io.BytesIO()
    ds.save_as(buffer, write_like_original=False)
    return buffer.getvalue()


def _make_tool() -> DicomModelInputTool:
    tool = DicomModelInputTool.__new__(DicomModelInputTool)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_blob_message = lambda blob, meta=None: ("blob", blob, meta)
    return tool


def test_preview_emits_blob_and_dimensions():
    tool = _make_tool()

    messages = list(
        tool._invoke(
            {
                "dicom_file": _File(_dicom_bytes()),
                "include_preview_image": True,
                "max_preview_edge": 8,
            }
        )
    )

    kinds = [kind for kind, *_ in messages]
    assert "blob" in kinds
    assert "json" in kinds

    blob_message = next(message for message in messages if message[0] == "blob")
    assert blob_message[1][:8] == b"\x89PNG\r\n\x1a\n"

    payload = next(message for message in messages if message[0] == "json")[1]
    preview = payload["preview"]
    assert preview["preview_width"] == 8
    assert preview["preview_height"] == 8
    assert preview["mime_type"] == "image/png"


def test_no_preview_when_disabled():
    tool = _make_tool()

    messages = list(tool._invoke({"dicom_file": _File(_dicom_bytes())}))

    assert all(kind != "blob" for kind, *_ in messages)
    payload = next(message for message in messages if message[0] == "json")[1]
    assert "preview" not in payload


def test_preview_handles_rgb_frames():
    tool = _make_tool()

    messages = list(
        tool._invoke(
            {
                "dicom_file": _File(_dicom_bytes(channels=3)),
                "include_preview_image": True,
                "max_preview_edge": 8,
            }
        )
    )

    blob_message = next(message for message in messages if message[0] == "blob")
    assert blob_message[1][:8] == b"\x89PNG\r\n\x1a\n"

    payload = next(message for message in messages if message[0] == "json")[1]
    assert payload["preview"]["preview_width"] == 8
    assert payload["preview"]["preview_height"] == 8
