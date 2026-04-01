"""
Lazy iterative orchestrator for s01e04 — downloads documents on-demand
based on API error feedback. Uses function calling to let the LLM decide
which files to fetch.

Flow:
  1. Submit form with known values + placeholders
  2. On error: give LLM the error + list of available files
  3. LLM picks which file(s) to download
  4. Download only those, LLM fixes the field
  5. Resubmit, repeat until accepted
"""
import base64
import json
import os
import re
import uuid
import urllib.request
from datetime import datetime

from common import get_api_key, load_dotenv, api_post, ApiError, llm, llm_vision_call, cost_tracker, BASE_URL
from endpoints import VERIFY, DATA_DOC

load_dotenv()
api_key = get_api_key()

MAX_ITERATIONS = 10
LLM_MODEL = os.environ.get("LLM_MODEL", "google/gemini-2.0-flash-001")
DOC_BASE = f"{BASE_URL}{DATA_DOC}"

KNOWN = {
    "sender_id": "450202122",
    "sending_point": "Gdańsk",
    "destination": "Żarnowiec",
    "weight_kg": 2800,
    "description": "kasety z paliwem do reaktora",
    "special_notes": "",
    "amount_pp": "0 PP",
    "date": "[UNKNOWN]",
    "route_code": "[UNKNOWN]",
    "category": "[UNKNOWN]",
    "wdp": 0,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": "Download a file from the SPK documentation. Use this to fetch specific documents that might contain information needed to fix the form.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to download, e.g. 'index.md', 'zalacznik-F.md', 'trasy-wylaczone.png'"
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_field",
            "description": "Update a field in the declaration form.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["date", "route_code", "category", "wdp"],
                        "description": "Which field to update"
                    },
                    "value": {
                        "type": "string",
                        "description": "New value for the field"
                    }
                },
                "required": ["field", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_form",
            "description": "Submit the current declaration form to the API for verification.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


def format_declaration(d):
    return (
        "SYSTEM PRZESYŁEK KONDUKTORSKICH - DEKLARACJA ZAWARTOŚCI\n"
        "======================================================\n"
        f"DATA: {d['date']}\n"
        f"PUNKT NADAWCZY: {d['sending_point']}\n"
        "------------------------------------------------------\n"
        f"NADAWCA: {d['sender_id']}\n"
        f"PUNKT DOCELOWY: {d['destination']}\n"
        f"TRASA: {d['route_code']}\n"
        "------------------------------------------------------\n"
        f"KATEGORIA PRZESYŁKI: {d['category']}\n"
        "------------------------------------------------------\n"
        f"OPIS ZAWARTOŚCI (max 200 znaków): {d['description']}\n"
        "------------------------------------------------------\n"
        f"DEKLAROWANA MASA (kg): {d['weight_kg']}\n"
        "------------------------------------------------------\n"
        f"WDP: {d['wdp']}\n"
        "------------------------------------------------------\n"
        f"UWAGI SPECJALNE: {d['special_notes']}\n"
        "------------------------------------------------------\n"
        f"KWOTA DO ZAPŁATY: {d['amount_pp']}\n"
        "------------------------------------------------------\n"
        "OŚWIADCZAM, ŻE PODANE INFORMACJE SĄ PRAWDZIWE.\n"
        "BIORĘ NA SIEBIE KONSEKWENCJĘ ZA FAŁSZYWE OŚWIADCZENIE.\n"
        "======================================================"
    )


def download_file(filename):
    url = f"{DOC_BASE}{filename}"
    print(f"  [Lazy] Downloading {url}")
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def get_available_files():
    print("  [Lazy] Fetching index.md for file list...")
    with urllib.request.urlopen(f"{DOC_BASE}index.md") as resp:
        index_md = resp.read().decode("utf-8")
    includes = re.findall(r'\[include file="([^"]+)"\]', index_md)
    return ["index.md"] + includes


def submit_to_api(declaration):
    form_text = format_declaration(declaration)
    return api_post(VERIFY, {
        "apikey": api_key,
        "task": "sendit",
        "answer": {"declaration": form_text}
    })


def save_result(history, declaration, response):
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    filepath = os.path.join(output_dir, f"iterative_{ts}_{uid}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "iterations": history,
            "final_declaration": declaration,
            "final_response": response,
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved to {filepath}")


if __name__ == "__main__":
    declaration = KNOWN.copy()
    downloaded_files = {}

    # Get list of available files
    available = get_available_files()
    print(f"Available files: {available}")

    # First submit to get initial error
    print("\n[Iteration 0] Initial submit with placeholders...")
    try:
        result = submit_to_api(declaration)
        print(f"SUCCESS on first try: {result}")
        save_result([], declaration, result)
        exit()
    except ApiError as e:
        initial_error = e.body
        print(f"REJECTED: {initial_error}")

    # Start agent loop
    messages = [
        {"role": "system", "content": (
            "Jesteś autonomicznym agentem wypełniającym formularz deklaracji SPK.\n"
            "NIGDY nie pytaj użytkownika o informacje — WSZYSTKO musisz ustalić samodzielnie "
            "pobierając i analizując dokumentację SPK.\n\n"
            "Dostępne narzędzia:\n"
            "- download_file: pobierz dokument z dokumentacji SPK\n"
            "- update_field: zaktualizuj pole formularza\n"
            "- submit_form: wyślij formularz do weryfikacji\n\n"
            "PROCEDURA: Zacznij od pobrania index.md — to główny dokument zawierający "
            "informacje o systemie SPK, kategoriach przesyłek, trasach, dacie, opłatach itp. "
            "Na jego podstawie pobieraj dodatkowe pliki jeśli potrzebujesz szczegółów.\n\n"
            f"Dostępne pliki dokumentacji: {available}\n\n"
            "Pola które MUSISZ ustalić z dokumentacji:\n"
            "- date: format YYYY-MM-DD (znajdź w dokumentacji informacje o aktualnej dacie w systemie SPK)\n"
            "- route_code: kod trasy z mapy sieci (format np. M-01, R-04, X-01)\n"
            "- category: kategoria przesyłki A/B/C/D/E (dopasuj do typu zawartości)\n"
            "- wdp: liczba dodatkowych wagonów (oblicz na podstawie wagi i ładowności wagonów)\n\n"
            "Znane fakty o przesyłce (NIE ZMIENIAJ tych wartości):\n"
            "- Nadawca: 450202122\n"
            "- Z: Gdańsk → Do: Żarnowiec\n"
            "- Zawartość: kasety z paliwem do reaktora, 2800 kg\n"
            "- Koszt: 0 PP\n"
            "- Uwagi: brak\n\n"
            "Pobieraj pliki które mogą pomóc rozwiązać konkretny problem. "
            "Nie pobieraj wszystkich plików na raz."
        )},
        {"role": "user", "content": (
            f"Formularz został odrzucony z błędem:\n{initial_error}\n\n"
            f"Obecny stan formularza:\n{json.dumps(declaration, indent=2, ensure_ascii=False)}\n\n"
            "Pobierz potrzebne dokumenty i popraw formularz."
        )}
    ]

    history = [{"iteration": 0, "error": initial_error}]
    final_response = None

    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'=' * 60}")
        print(f"AGENT ITERATION {i}/{MAX_ITERATIONS}")
        print(f"{'=' * 60}")

        msg = llm(messages, tools=TOOLS, max_tokens=2048, temperature=0.3, model=LLM_MODEL, raw=True)
        messages.append(msg)

        if msg.get("content"):
            print(f"  [Agent] {msg['content']}")

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            print("  [Agent] No tool calls — stopping.")
            break

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])
            print(f"  [Agent] Calling {fn_name}({json.dumps(fn_args)})")

            if fn_name == "download_file":
                fname = fn_args["filename"]
                if fname in downloaded_files:
                    content = downloaded_files[fname]
                    tool_result = f"[Cached] {fname}:\n{content}"
                else:
                    raw = download_file(fname)
                    if fname.lower().endswith((".png", ".jpg", ".jpeg")):
                        b64 = base64.b64encode(raw).decode("utf-8")
                        ext = fname.rsplit(".", 1)[-1].lower()
                        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}[ext]
                        content = llm_vision_call(messages=[
                            {"role": "system", "content": "Opisz dokładnie co widzisz. Wymień wszystkie trasy, kody, lokalizacje."},
                            {"role": "user", "content": [
                                {"type": "text", "text": f"Opisz obraz {fname}:"},
                                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                            ]}
                        ])
                    else:
                        content = raw.decode("utf-8")
                    downloaded_files[fname] = content
                    tool_result = f"{fname}:\n{content}"
                print(f"  [Lazy] Got {fname} ({len(content)} chars)")

            elif fn_name == "update_field":
                field = fn_args["field"]
                value = fn_args["value"]
                if field == "wdp":
                    value = int(value)
                elif field == "weight_kg":
                    value = float(value)
                declaration[field] = value
                tool_result = f"Updated {field} = {value}. Current form:\n{json.dumps(declaration, indent=2, ensure_ascii=False)}"
                print(f"  [Lazy] {field} = {value}")

            elif fn_name == "submit_form":
                form_text = format_declaration(declaration)
                print(f"\n  [Lazy] Submitting form...")
                print(form_text)
                try:
                    api_result = submit_to_api(declaration)
                    tool_result = f"SUCCESS: {json.dumps(api_result)}"
                    print(f"  SUCCESS: {api_result}")
                    final_response = api_result
                    history.append({"iteration": i, "declaration": declaration.copy(), "response": api_result})
                except ApiError as e:
                    tool_result = f"REJECTED: {e.body}"
                    print(f"  REJECTED: {e.body}")
                    history.append({"iteration": i, "declaration": declaration.copy(), "error": e.body})

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

        if final_response and final_response.get("code") == 0:
            print(f"\nDone! Files downloaded: {list(downloaded_files.keys())}")
            break

    else:
        print(f"\nFailed after {MAX_ITERATIONS} iterations.")

    save_result(history, declaration, final_response)
    print(f"\n{cost_tracker.summary()}")
