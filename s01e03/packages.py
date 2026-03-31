import json

from common import api_post, ApiError
from endpoints import PACKAGES


class PackageService:

    def __init__(self, api_key: str):
        self._api_key = api_key

    def check(self, package_id: str) -> dict:
        payload = {
            "apikey": self._api_key,
            "action": "check",
            "packageid": package_id,
        }
        print(f"  [Packages] check -> {json.dumps(payload, ensure_ascii=False)}")
        try:
            result = api_post(PACKAGES, payload)
        except ApiError as e:
            print(f"  [Packages] check error: {e}")
            return {"error": str(e)}
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
        try:
            result = api_post(PACKAGES, payload)
        except ApiError as e:
            print(f"  [Packages] redirect error: {e}")
            return {"error": str(e)}
        print(f"  [Packages] redirect <- {json.dumps(result, ensure_ascii=False)}")
        return result
