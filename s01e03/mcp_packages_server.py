"""
MCP Server exposing package management tools (check & redirect).

Run standalone:
    python3 -m s01e03.mcp_packages_server

Or use as stdio subprocess from an MCP client.
"""
import os
import sys

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import load_dotenv, get_api_key
from s01e03.packages import PackageService

load_dotenv()
service = PackageService(get_api_key())

mcp = FastMCP(
    name="packages",
    instructions="Serwer MCP do zarządzania paczkami w systemie logistycznym elektrowni. "
                 "Udostępnia narzędzia do sprawdzania statusu paczek oraz ich przekierowywania.",
)


@mcp.tool()
def check_package(package_id: str) -> dict:
    """Sprawdza status paczki po jej ID.

    Zwraca lokalizację, status dostarczenia i inne szczegóły paczki.

    Args:
        package_id: ID paczki, np. PKG12345678
    """
    return service.check(package_id)


@mcp.tool()
def redirect_package(package_id: str, destination: str, code: str) -> dict:
    """Przekierowuje paczkę do nowego miejsca docelowego.

    Wymaga ID paczki, kodu miejsca docelowego i kodu zabezpieczającego
    podanego przez operatora.

    Args:
        package_id: ID paczki
        destination: Kod miejsca docelowego, np. PWR3847PL
        code: Kod zabezpieczający
    """
    return service.redirect(package_id, destination, code)


if __name__ == "__main__":
    mcp.run(transport="stdio")
