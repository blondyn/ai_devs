import random
from flask import Flask, request, jsonify

RESPONSES = [
    "Got it, thanks!",
    "Message received loud and clear.",
    "Roger that!",
    "Acknowledged.",
    "Copy that, over and out.",
    "Understood, moving on.",
    "10-4, good buddy.",
]

app = Flask(__name__)


@app.route("/", methods=["POST"])
def handle_message():
    data = request.get_json()
    print(f"\n{'='*50}")
    print(f"Session ID: {data.get('sessionID')}")
    print(f"Message: {data.get('msg')}")
    print(f"{'='*50}\n")
    return jsonify({"msg": random.choice(RESPONSES)})


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({
        "error": "Method Not Allowed. Use POST with JSON body:",
        "expected_format": {
            "sessionID": "your-session-id",
            "msg": "your message"
        }
    }), 405


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
