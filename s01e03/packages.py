import sys
sys.path.insert(0, "..")
from common import api_post
from endpoints import PACKAGES


class PackageService:

    def __init__(self, api_key: str):
        self._api_key = api_key

    def check(self, package_id: str) -> dict:
        return api_post(PACKAGES, {
            "apikey": self._api_key,
            "action": "check",
            "packageid": package_id,
        })

    def redirect(self, package_id: str, destination: str, code: str) -> dict:
        return api_post(PACKAGES, {
            "apikey": self._api_key,
            "action": "redirect",
            "packageid": package_id,
            "destination": destination,
            "code": code,
        })
