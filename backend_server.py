from flask import Flask, request, jsonify
import requests
import openai
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = Flask(__name__)

# OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Firebase Initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

WAYBACK_API = "http://archive.org/wayback/available"

@app.route("/report404", methods=["POST"])
def report_404():
    data = request.get_json()
    broken_url = data.get("url")
    print("Received broken URL:", broken_url)

    # Check Wayback Machine
    params = {"url": broken_url}
    wb_response = requests.get(WAYBACK_API, params=params).json()

    archived_snapshots = wb_response.get("archived_snapshots", {})
    snapshot_url = None
    ai_reconstruction = None

    if archived_snapshots.get("closest"):
        snapshot_url = archived_snapshots["closest"]["url"]
    else:
        ai_reconstruction = generate_ai_reconstruction(broken_url)

    # Store into Firebase
    store_in_firebase(broken_url, snapshot_url, ai_reconstruction)

    if snapshot_url:
        return jsonify({"archived": True, "snapshot_url": snapshot_url})
    else:
        return jsonify({"archived": False, "ai_reconstruction": ai_reconstruction})

def generate_ai_reconstruction(url):
    prompt = f"""
    The following webpage at URL '{url}' is currently unavailable.
    Generate a possible webpage reconstruction for it, based only on the URL and your general knowledge.
    Output simple HTML content with reasonable title, heading, and placeholder text that might have existed.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800
        )

        ai_content = response['choices'][0]['message']['content']
        return ai_content

    except Exception as e:
        print("OpenAI Error:", e)
        return "AI reconstruction failed."

def store_in_firebase(url, snapshot_url, ai_reconstruction):
    record = {
        "url": url,
        "archived": bool(snapshot_url),
        "snapshot_url": snapshot_url,
        "ai_reconstruction": ai_reconstruction
    }

    db.collection("archived_pages").add(record)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
