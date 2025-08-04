from typing import Any

from azure.core.credentials import AccessToken, TokenCredential
from msgraph.graph_service_client import GraphServiceClient


class MockCredential(TokenCredential):
    token: AccessToken = None

    def __init__(self, token: str, expires_on: int):
        self.token = AccessToken(token=token, expires_on=expires_on)

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        return self.token


class OneDriveClient:

    def __init__(self, credentials: dict[str, Any]):
        self.client = GraphServiceClient(
            credentials=MockCredential(
                token=credentials.get("access_token"),
                expires_on=credentials.get("expires_at", 2000000000),
            ),
            scopes=["Files.Read.All"],
        )

    def get_client(self) -> GraphServiceClient:
        return self.client

    async def get_file_by_id(self, file_id: str):
        drive = (
            await self.client.me.drive.get()
        )  # Assuming you want to get the user's drive
        return (
            await self.client.drives.by_drive_id(drive.id)
            .items.by_drive_item_id(file_id)
            .get()
        )

    async def get_drive_by_id(self, drive_id: str):
        return await self.client.drives.by_drive_id(drive_id).get()

    async def delete_file_by_id(self, file_id: str):
        drive = await self.client.me.drive.get()
        await self.client.drives.by_drive_id(drive.id).items.by_drive_item_id(
            file_id
        ).delete()

    async def search_file(self, query: str):
        drive = await self.client.me.drive.get()

        return await self.client.drives.by_drive_id(drive.id).search_with_q(query).get()

    async def upload_file(self, file_name: str, file_content: bytes):
        drive = await self.client.me.drive.get()

        response = (
            await self.client.drives.by_drive_id(drive.id)
            .items.by_drive_item_id(f"root:/{file_name}:")
            .content.put(file_content)
        )

        return response
