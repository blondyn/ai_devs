from flask import Flask, request, jsonify
from memory import ConversationMemory
from brain import Brain


def create_app(memory: ConversationMemory, brain: Brain) -> Flask:
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def handle_message_get():
        return jsonify({"msg": "Hello, I'm a chatbot!"})

    @app.route("/", methods=["POST"])
    def handle_message():
        data = request.get_json()
        session_id = data.get("sessionID")
        msg = data.get("msg")

        memory.add(session_id, "user", msg)

        response = brain.think(session_id, msg)
        memory.add(session_id, "assistant", response)

        print(f"\n{'='*50}")
        print(f"Session ID: {session_id}")
        print(f"Message: {msg}")
        print(f"Response: {response}")
        print(f"{'='*50}\n")

        return jsonify({"msg": response})

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            "error": "Method Not Allowed. Use POST with JSON body:",
            "expected_format": {
                "sessionID": "your-session-id",
                "msg": "your message"
            }
        }), 405

    return app
