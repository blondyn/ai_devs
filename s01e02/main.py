import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import api_get, api_post, BASE_URL, get_api_key, submit
from endpoints import DATA_FINDHIM_LOCATIONS, LOCATION, ACCESS_LEVEL

API_KEY = get_api_key()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    print("OPENROUTER_API_KEY not set")
    sys.exit(1)

# --- Tool implementations ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def tool_get_suspects():
    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "s01e01",
            "results.json",
        )
    ) as f:
        return json.load(f)


def tool_get_power_plants():
    data = api_get(DATA_FINDHIM_LOCATIONS.format(api_key=API_KEY))
    return data["power_plants"]


def tool_get_person_locations(name, surname):
    result = api_post(
        LOCATION,
        {"apikey": API_KEY, "name": name, "surname": surname},
    )
    return result if isinstance(result, list) else result.get("locations", result.get("data", []))


def tool_find_nearest_plant(locations):
    """Given a list of {lat, lon} locations, find the nearest power plant city and return the min distance."""
    if isinstance(locations, dict):
        locations = locations.get("result", locations.get("locations", locations.get("data", [])))
    if not isinstance(locations, list):
        return {"error": "locations must be a list of {lat, lon} objects"}
    best_dist = float("inf")
    best_city = None
    best_loc = None
    for loc in locations:
        lat = loc.get("lat", loc.get("latitude"))
        lon = loc.get("lon", loc.get("longitude", loc.get("lng")))
        if lat is None or lon is None:
            continue
        for city, (plat, plon) in CITY_COORDS.items():
            dist = haversine(lat, lon, plat, plon)
            if dist < best_dist:
                best_dist = dist
                best_city = city
                best_loc = {"lat": lat, "lon": lon}
    return {"nearest_city": best_city, "distance_km": round(best_dist, 2), "location": best_loc}


def tool_get_access_level(name, surname, birthYear):
    result = api_post(
        ACCESS_LEVEL,
        {"apikey": API_KEY, "name": name, "surname": surname, "birthYear": birthYear},
    )
    return result


def tool_submit_answer(name, surname, accessLevel, powerPlant):
    answer = {
        "name": name,
        "surname": surname,
        "accessLevel": accessLevel,
        "powerPlant": powerPlant,
    }
    return submit(API_KEY, "findhim", answer)


# --- Tool registry ---

TOOLS_MAP = {
    "get_suspects": tool_get_suspects,
    "get_power_plants": tool_get_power_plants,
    "get_person_locations": tool_get_person_locations,
    "find_nearest_plant": tool_find_nearest_plant,
    "get_access_level": tool_get_access_level,
    "submit_answer": tool_submit_answer,
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_suspects",
            "description": "Get the list of suspects from the previous task (s01e01). Returns name, surname, birthYear for each.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_power_plants",
            "description": "Get the list of power plants with their city names, power output (MW), and codes (PWR####PL format).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_person_locations",
            "description": "Get the list of GPS locations (latitude, longitude) where a person was observed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "First name"},
                    "surname": {"type": "string", "description": "Last name"},
                },
                "required": ["name", "surname"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_nearest_plant",
            "description": "Given a list of GPS locations where a person was observed, find the nearest power plant city and return the minimum distance in km. Pass the locations array directly from get_person_locations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of location objects with latitude/longitude fields",
                    },
                },
                "required": ["locations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_access_level",
            "description": "Get the access level for a person. Requires birthYear as integer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "birthYear": {"type": "integer"},
                },
                "required": ["name", "surname", "birthYear"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Submit the final answer identifying the suspect near a power plant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "accessLevel": {"type": "integer"},
                    "powerPlant": {"type": "string", "description": "Power plant code in PWR####PL format"},
                },
                "required": ["name", "surname", "accessLevel", "powerPlant"],
            },
        },
    },
]

CITY_COORDS = {
    "Zabrze": (50.3249, 18.7857),
    "Piotrków Trybunalski": (51.4053, 19.7031),
    "Grudziądz": (53.4837, 18.7536),
    "Tczew": (54.0927, 18.7997),
    "Radom": (51.4027, 21.1471),
    "Chelmno": (53.3492, 18.4260),
    "Żarnowiec": (54.7833, 18.0667),
}

SYSTEM_PROMPT = """You are an agent tasked with finding which suspect was observed near a nuclear power plant in Poland.

You have tools to:
1. get_suspects - Get the list of suspects (name, surname, birthYear)
2. get_power_plants - Get power plant cities and their codes
3. get_person_locations - Get GPS locations where a person was observed
4. find_nearest_plant - Given locations, find the nearest power plant and distance
5. get_access_level - Get access level for a person
6. submit_answer - Submit the final answer

Steps:
1. Call get_suspects and get_power_plants in parallel
2. For each suspect, call get_person_locations, then find_nearest_plant with those locations
3. The suspect with the smallest distance to any plant is your target
4. Get that suspect's access level
5. Submit: name, surname, accessLevel, powerPlant (code from get_power_plants)

Call multiple tools in parallel when possible. For step 2, call get_person_locations for ALL suspects in parallel."""

# --- Agent loop ---

import urllib.request

def call_openrouter(messages):
    payload = json.dumps({
        "model": "google/gemini-2.0-flash-001",
        "messages": messages,
        "tools": TOOLS_SCHEMA,
        "max_tokens": 4096,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_KEY}",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)
    return json.loads(resp.read().decode("utf-8"))


def run_agent():
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Find the suspect who was observed near a nuclear power plant. Get their access level and submit the answer."},
    ]

    MAX_ITERATIONS = 15
    for i in range(MAX_ITERATIONS):
        print(f"\n--- Agent step {i + 1} ---")
        result = call_openrouter(messages)
        choice = result["choices"][0]
        message = choice["message"]

        # Add assistant message to history
        messages.append(message)

        print(f"Choices response: {len(result['choices'])}")
        print(f"Tool calls: {message.get('tool_calls', [])}")

        # Check if we have tool calls
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            # No tool calls — agent is done
            print(f"Agent response: {message.get('content', '')}")
            return

        # Execute tool calls
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}
            print(f"  Calling {func_name}({args})")

            func = TOOLS_MAP.get(func_name)
            if func:
                try:
                    tool_result = func(**args)
                except Exception as e:
                    tool_result = {"error": str(e)}
            else:
                tool_result = {"error": f"Unknown tool: {func_name}"}

            print(f"  Result: {json.dumps(tool_result, ensure_ascii=False)[:200]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, ensure_ascii=False),
            })

        # Check finish reason
        if choice.get("finish_reason") == "stop":
            print(f"Agent finished: {message.get('content', '')}")
            return

    print("Agent reached max iterations!")


run_agent()
