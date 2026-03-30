import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import api_post, get_api_key, submit
from endpoints import ACCESS_LEVEL, LOCATION
API_KEY = get_api_key()

def get_access_level(name, surname, birthYear):
   return api_post(
        ACCESS_LEVEL,
        {"apikey": API_KEY, "name": name, "surname": surname, "birthYear": birthYear},
    )

def get_person_locations(name, surname, birthYear):
    return api_post(
        LOCATION,
        {"apikey": API_KEY, "name": name, "surname": surname, "birthYear": birthYear},
    )

print(get_access_level("Martin", "Handford", 1987))
