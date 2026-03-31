import json
import sys
import urllib.request
import urllib.error
sys.path.insert(0, "..")
from common import BASE_URL
from endpoints import PACKAGES


class PackageService:

    def __init__(self, api_key: str):
        self._api_key = api_key

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}{PACKAGES}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  [Packages] HTTP Error {e.code}: {error_body}")
            return {"error": f"HTTP {e.code}", "message": error_body}

    def check(self, package_id: str) -> dict:
        payload = {
            "apikey": self._api_key,
            "action": "check",
            "packageid": package_id,
        }
        print(f"  [Packages] check -> {json.dumps(payload, ensure_ascii=False)}")
        result = self._post(payload)
        print(f"  [Packages] check <- {json.dumps(result, ensure_ascii=False)}")
        return result

    def redirect(self, package_id: str, destination: str, code: str) -> dict:
        payload = {
            "apikey": self._api_key,
            "action": "redirect",
            "packageid": package_id,
            "destination": destination,
            "code": code,
        }
        print(f"  [Packages] redirect -> {json.dumps(payload, ensure_ascii=False)}")
        result = self._post(payload)
        print(f"  [Packages] redirect <- {json.dumps(result, ensure_ascii=False)}")
        return result
