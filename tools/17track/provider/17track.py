from dify_plugin import PluginProvider

from tools.seventeentrack_client import SeventeenTrackClient, SeventeenTrackError


class SeventeenTrackProvider(PluginProvider):
    def validate_credentials(self, credentials: dict) -> None:
        client = SeventeenTrackClient(credentials["seventeen_track_api_key"])
        try:
            client.get_quota()
        except SeventeenTrackError as error:
            raise Exception(str(error)) from error
