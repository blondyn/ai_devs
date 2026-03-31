import csv
import json
import os
import urllib.request

from common import get_api_key, api_get, submit, llm_call, BASE_URL
from endpoints import DATA_PEOPLE

API_KEY = get_api_key()

# 1. Download CSV
url = f"{BASE_URL}{DATA_PEOPLE.format(api_key=API_KEY)}"
response = urllib.request.urlopen(url)
text = response.read().decode('utf-8')

# 2. Parse and filter
reader = csv.DictReader(text.splitlines())
candidates = []
for row in reader:
    birth_year = int(row['birthDate'].split('-')[0])
    age_in_2026 = 2026 - birth_year
    if (row['gender'] == 'M'
        and row['birthPlace'] == 'Grudziądz'
        and 20 <= age_in_2026 <= 40):
        candidates.append(row)

print(f"Found {len(candidates)} candidates matching criteria")
for c in candidates:
    print(f"  {c['name']} {c['surname']}, born {c['birthDate']}, job: {c['job'][:80]}...")

# 3a. Step 1: Filter transport-related jobs (cheap, minimal output)
jobs_list = "\n".join(f"{i+1}. {c['job']}" for i, c in enumerate(candidates))

filter_schema = {
    "type": "json_schema",
    "json_schema": {
        "name": "transport_filter",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "transport_indices": {
                    "type": "array",
                    "items": {"type": "integer"}
                }
            },
            "required": ["transport_indices"],
            "additionalProperties": False
        }
    }
}

filter_result = llm_call(
    [{"role": "user", "content": f"Which of these jobs are related to transport (logistics, driving, shipping, cargo, fleet, traffic, movement of goods/people)? Return only their 1-based indices.\n\n{jobs_list}"}],
    filter_schema, max_tokens=256
)
transport_indices = filter_result['transport_indices']
print(f"Transport-related indices: {transport_indices}")

# 3b. Step 2: Full tagging for transport jobs only
transport_candidates = [(idx, candidates[idx - 1]) for idx in transport_indices]
transport_jobs = "\n".join(f"{idx}. {c['job']}" for idx, c in transport_candidates)

TAGS_ENUM = ["IT", "transport", "edukacja", "medycyna", "praca z ludźmi", "praca z pojazdami", "praca fizyczna"]

tag_schema = {
    "type": "json_schema",
    "json_schema": {
        "name": "job_tags",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string", "enum": TAGS_ENUM}
                            }
                        },
                        "required": ["index", "tags"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["results"],
            "additionalProperties": False
        }
    }
}

tag_result = llm_call(
    [{"role": "user", "content": f"Classify each job into one or more tags: IT, transport, edukacja, medycyna, praca z ludźmi, praca z pojazdami, praca fizyczna.\n\n{transport_jobs}"}],
    tag_schema, max_tokens=512
)

# 4. Build answer with transport-tagged people
answer = []
for item in tag_result['results']:
    idx = item['index'] - 1
    tags = item['tags']
    c = candidates[idx]
    print(f"  {c['name']} {c['surname']}: {tags}")
    answer.append({
        "name": c['name'],
        "surname": c['surname'],
        "gender": c['gender'],
        "born": int(c['birthDate'].split('-')[0]),
        "city": c['birthPlace'],
        "tags": tags
    })

print(f"\n{len(answer)} people with transport tag:")
for a in answer:
    print(f"  {a['name']} {a['surname']}: {a['tags']}")

# 5. Submit
submit(API_KEY, "people", answer)
