import os
import requests

# 官方 API 文档(11 个接口): https://asset.17track.net/api/document/v2.4_zh/index.html
# 只保留单一环境默认值;e2e 沙箱通过环境变量 SEVENTEEN_TRACK_API_BASE 覆盖,不落入代码
API_BASE = os.environ.get("SEVENTEEN_TRACK_API_BASE") or "https://api.17track.net/track/v2.4"

AUTH_CODES = {-18010001, -18010002, -18010004, -18010005}
UPSTREAM_CODES = {-18010003, -18019815, -18019816, -18019817}
RATE_LIMIT_CODES = {-18019907, -18019908}


class SeventeenTrackError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SeventeenTrackClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def request(self, path, body):
        try:
            response = requests.post(
                f"{API_BASE}/{path}",
                json=body,
                headers={
                    "17token": self.api_key,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                timeout=30,
            )
            payload = response.json()
        except requests.RequestException as error:
            raise SeventeenTrackError(None, f"17TRACK request failed: {error}") from error
        self._assert_envelope(payload)
        return payload

    def _assert_envelope(self, payload):
        data = payload.get("data") or {}
        errors = data.get("errors") or []
        if payload.get("code") != 0 or errors:
            first = errors[0] if errors else {}
            code = first.get("code", payload.get("code"))
            message = first.get("message") or f"17TRACK API error {code}"
            if code in AUTH_CODES:
                raise SeventeenTrackError(code, f"authentication failed: {message}")
            if code in RATE_LIMIT_CODES:
                raise SeventeenTrackError(code, f"rate limited: {message}")
            if code in UPSTREAM_CODES:
                raise SeventeenTrackError(code, f"upstream error: {message}")
            raise SeventeenTrackError(code, message)

    @staticmethod
    def _num(data, key):
        value = data.get(key)
        if not isinstance(value, (int, float)):
            raise SeventeenTrackError(None, f"17TRACK response field {key} is not a number")
        return value

    def get_quota(self):
        data = self.request("getquota", []).get("data") or {}
        fallback = "free_email_quotaused" if "free_email_quotaused" in data else "free_email_quota_used"
        return {
            "total": self._num(data, "quota_total"),
            "used": self._num(data, "quota_used"),
            "remaining": self._num(data, "quota_remain"),
            "todayUsed": self._num(data, "today_used"),
            "dailyLimit": self._num(data, "max_track_daily"),
            "freeEmailQuota": self._num(data, "free_email_quota"),
            "freeEmailQuotaUsed": self._num(data, fallback),
        }

    def register_trackings(self, trackings):
        payload = self.request("register", trackings)
        data = payload.get("data") or {}
        return {
            "accepted": data.get("accepted") or [],
            "rejected": data.get("rejected") or [],
        }

    def get_tracking_details(self, trackings):
        payload = self.request("gettrackinfo", trackings)
        data = payload.get("data") or {}
        return {
            "accepted": data.get("accepted") or [],
            "rejected": data.get("rejected") or [],
        }

    def list_trackings(self, page_no=0, package_status=None, tracking_status=None):
        body = {"page_no": page_no}
        if package_status:
            body["package_status"] = package_status
        if tracking_status:
            body["tracking_status"] = tracking_status
        payload = self.request("gettracklist", body)
        data = payload.get("data") or {}
        page = payload.get("page") or {}
        return {
            "trackings": data.get("accepted") or [],
            "pagination": {
                "totalItems": self._num(page, "data_total"),
                "totalPages": self._num(page, "page_total"),
                "pageNumber": self._num(page, "page_no"),
                "pageSize": self._num(page, "page_size"),
            },
        }

    @staticmethod
    def parse_numbers(raw):
        import re

        pattern = re.compile(r"^[A-Za-z0-9-]{5,50}$")
        numbers = [item.strip() for item in re.split(r"[\s,;]+", raw or "") if item.strip()]
        return [item for item in numbers if pattern.match(item)]

    def stop_trackings(self, trackings):
        payload = self.request("stoptrack", trackings)
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}

    def restart_trackings(self, trackings):
        payload = self.request("retrack", trackings)
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}

    def delete_trackings(self, trackings):
        payload = self.request("deletetrack", trackings)
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}

    def push_trackings(self, trackings):
        payload = self.request("push", trackings)
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}

    def change_carrier(self, carrier_changes):
        payload = self.request("changecarrier", carrier_changes)
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}

    def update_tracking_info(self, trackings):
        payload = self.request("changeinfo", trackings)
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}

    def get_realtime_tracking_details(self, tracking):
        payload = self.request("getRealTimeTrackInfo", [tracking])
        data = payload.get("data") or {}
        return {"accepted": data.get("accepted") or [], "rejected": data.get("rejected") or []}
