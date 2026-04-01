"""
Orchestrator for s01e04 — loads SPK documents, uses LLM to determine
unknown fields, fills the declaration form, and submits after confirmation.
"""
import json
import os
import uuid
from datetime import datetime

from common import get_api_key, load_dotenv, api_post, cost_tracker
from endpoints import VERIFY
from s01e04.explorer import Explorer

load_dotenv()
api_key = get_api_key()
LLM_MODEL = os.environ.get("LLM_MODEL", "google/gemini-2.0-flash-001")

# Fixed values provided by the task
FIXED = {
    "sender_id": "450202122",
    "sending_point": "Gdańsk",
    "destination": "Żarnowiec",
    "weight_kg": 2800,
    "description": "kasety z paliwem do reaktora",
    "special_notes": "",
    "amount_pp": "0 PP",
}

# Schema for LLM to fill the remaining fields
UNKNOWN_FIELDS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "unknown_fields",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD — data nadania"},
                "route_code": {"type": "string", "description": "kod trasy z mapy sieci (załącznik F)"},
                "category": {"type": "string", "description": "kategoria przesyłki A/B/C/D/E"},
                "wdp": {"type": "number", "description": "WDP — liczba dodatkowych wagonów potrzebnych"},
            },
            "required": ["date", "route_code", "category", "wdp"],
            "additionalProperties": False
        }
    }
}


def format_declaration(d):
    """Format exactly as załącznik E template."""
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


def verify_declaration(form_text):
    """Submit the declaration to the verify endpoint."""
    payload = {
        "apikey": api_key,
        "task": "sendit",
        "answer": {"declaration": form_text}
    }
    print(f"Sending payload:\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n")
    return api_post(VERIFY, payload)


def save_result(declaration, form_text, response):
    """Save declaration and API response to a unique file."""
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    filepath = os.path.join(output_dir, f"declaration_{ts}_{uid}.json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "declaration_json": declaration,
            "declaration_text": form_text,
            "api_response": response,
        }, f, indent=2, ensure_ascii=False)

    print(f"Saved to {filepath}")


if __name__ == "__main__":
    # Step 1: Load documents
    print("[1/3] Loading documents via Explorer...")
    explorer = Explorer(model=LLM_MODEL).load()

    # Step 2: Ask LLM to determine unknown fields
    print("\n[2/3] Determining unknown fields...")
    unknowns = explorer.ask(
        "Muszę wysłać przesyłkę z Gdańska do Żarnowca. Zawartość: kasety z paliwem do reaktora, waga 2800 kg. "
        "Na podstawie dokumentacji SPK ustal:\n"
        "1. DATA — data w formacie YYYY-MM-DD (Rok Systemu 14, Cykl 7, Kwartał 3)\n"
        "2. TRASA — kod trasy z załącznika F (mapa sieci). Kody tras mają format np. M-01, R-04, X-01 itd. "
        "Znajdź kod trasy łączącej Gdańsk z Żarnowcem.\n"
        "3. KATEGORIA — jaka kategoria przesyłki (A/B/C/D/E) pasuje do paliwa reaktorowego? "
        "Kategoria A to strategiczna (wojskowa/rządowa), B to medyczna, E to osobista.\n"
        "4. WDP — ile dodatkowych wagonów potrzeba? Standardowy pociąg: 2 wagony × 500 kg = 1000 kg. "
        "Przesyłka waży 2800 kg, więc potrzeba dodatkowych wagonów po 500 kg każdy.",
        schema=UNKNOWN_FIELDS_SCHEMA,
        max_tokens=1024
    )

    print(f"LLM determined: {json.dumps(unknowns, indent=2, ensure_ascii=False)}")

    # Merge fixed + LLM-determined fields
    declaration = {**FIXED, **unknowns}

    # Step 3: Show and confirm
    form_text = format_declaration(declaration)
    print("\n" + form_text)

    confirm = input("\nSubmit? [y/N]: ").strip().lower()
    response = None
    if confirm in ("y", "yes", "tak"):
        print("\n[3/3] Submitting...")
        try:
            response = verify_declaration(form_text)
            print(f"Response: {json.dumps(response, indent=2, ensure_ascii=False)}")
        except Exception as e:
            response = {"error": str(e)}
            print(f"Error: {e}")
    else:
        print("Submission skipped.")

    save_result(declaration, form_text, response)
    print(f"\n{cost_tracker.summary()}")
