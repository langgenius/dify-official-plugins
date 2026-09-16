import tools.create_worksheet as create_module
import tools.write_worksheet_data as write_module
from tools.create_worksheet import CreateWorksheetTool
from tools.write_worksheet_data import WriteWorksheetDataTool


SITE_ID = "contoso.sharepoint.com,site-guid,web-guid"


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload


def _run(tool, parameters: dict) -> None:
    # The tools are generators; drain them so the request is actually issued.
    list(tool._invoke(parameters))


def test_write_targets_the_site_drive_when_site_id_is_given(monkeypatch) -> None:
    urls = []

    def fake_patch(url, headers, json, timeout):
        urls.append(url)
        return FakeResponse({"rowCount": 1, "columnCount": 1, "address": "A1"})

    monkeypatch.setattr(write_module.requests, "patch", fake_patch)

    tool = WriteWorksheetDataTool.from_credentials({"access_token": "access-token"})
    _run(
        tool,
        {
            "workbook_id": "workbook-id",
            "worksheet_name": "Sheet1",
            "range": "A1",
            "values": [["x"]],
            "site_id": SITE_ID,
        },
    )

    # Writing to a site drive is why Files.ReadWrite.All is part of _SCOPES:
    # Files.ReadWrite only covers the signed-in user's own OneDrive.
    assert urls[0].startswith(
        f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/"
    )


def test_write_targets_the_user_drive_without_site_id(monkeypatch) -> None:
    urls = []

    def fake_patch(url, headers, json, timeout):
        urls.append(url)
        return FakeResponse({"rowCount": 1, "columnCount": 1, "address": "A1"})

    monkeypatch.setattr(write_module.requests, "patch", fake_patch)

    tool = WriteWorksheetDataTool.from_credentials({"access_token": "access-token"})
    _run(
        tool,
        {
            "workbook_id": "workbook-id",
            "worksheet_name": "Sheet1",
            "range": "A1",
            "values": [["x"]],
        },
    )

    assert urls[0].startswith("https://graph.microsoft.com/v1.0/me/drive/")


def test_create_worksheet_targets_the_site_drive(monkeypatch) -> None:
    urls = []

    def fake_post(url, headers, json, timeout):
        urls.append(url)
        return FakeResponse({"id": "1", "name": "Sheet2"}, status_code=201)

    monkeypatch.setattr(create_module.requests, "post", fake_post)

    tool = CreateWorksheetTool.from_credentials({"access_token": "access-token"})
    _run(
        tool,
        {
            "workbook_id": "workbook-id",
            "worksheet_name": "Sheet2",
            "site_id": SITE_ID,
        },
    )

    assert urls[0] == (
        f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}"
        "/drive/items/workbook-id/workbook/worksheets"
    )
