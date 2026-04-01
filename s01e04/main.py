"""
Orchestrator for s01e04 — uses the Explorer agent to gather documents and answer
questions, then fills the shipment declaration form (załącznik E).
"""
import json

from common import get_api_key, load_dotenv, submit
from s01e04.explorer import Explorer

load_dotenv()
api_key = get_api_key()

DECLARATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "declaration",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "sending_point": {"type": "string", "description": "miasto nadania"},
                "sender_id": {"type": "string", "description": "identyfikator płatnika"},
                "destination": {"type": "string", "description": "miasto docelowe"},
                "route_code": {"type": "string", "description": "kod trasy"},
                "category": {"type": "string", "description": "A/B/C/D/E"},
                "description": {"type": "string", "description": "opis zawartości, max 200 znaków"},
                "weight_kg": {"type": "number", "description": "deklarowana masa w kg"},
                "wdp": {"type": "number", "description": "WDP - liczba"},
                "special_notes": {"type": "string", "description": "uwagi specjalne"},
                "amount_pp": {"type": "string", "description": "kwota do zapłaty w PP"},
            },
            "required": ["date", "sending_point", "sender_id", "destination", "route_code",
                          "category", "description", "weight_kg", "wdp", "special_notes", "amount_pp"],
            "additionalProperties": False
        }
    }
}


if __name__ == "__main__":
    # Step 1: Initialize explorer and load all documents
    print("=" * 60)
    print("STEP 1: Loading documents via Explorer")
    print("=" * 60)
    explorer = Explorer().load()

    # Step 2: Ask explorer to fill the declaration
    print("\n" + "=" * 60)
    print("STEP 2: Filling declaration (załącznik E)")
    print("=" * 60)
    result = explorer.ask(
        "Wypełnij formularz deklaracji zawartości (załącznik E). "
        "Użyj danych z dokumentacji aby wypełnić wszystkie pola. "
        "Jeśli jakieś pole nie ma jednoznacznej wartości, użyj najbardziej prawdopodobnej na podstawie kontekstu.",
        schema=DECLARATION_SCHEMA,
        max_tokens=2048
    )

    print("\nDeclaration form data:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
