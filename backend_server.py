from flask import Flask, request, jsonify, render_template_string, redirect
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

@app.route("/reconstruct")
def reconstruct():
    original_url = request.args.get("url")

    if not original_url:
        return "Missing URL parameter", 400

    # Search for matching document
    docs = db.collection("archived_pages").where("url", "==", original_url).stream()

    doc = next(docs, None)
    if not doc:
        return "No record found for this URL", 404

    data = doc.to_dict()

    # If Wayback snapshot exists, redirect user
    if data.get("snapshot_url"):
        return redirect(data["snapshot_url"])

    # If AI reconstruction is available, serve it
    if data.get("ai_reconstruction") and data["ai_reconstruction"] != "AI reconstruction failed.":
        html = data["ai_reconstruction"]

        full_page = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI Reconstructed Page</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background: #f9f9f9; }}
                .notice {{ font-size: 12px; color: #666; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="notice">This page was reconstructed using AI because no archive was available.</div>
            {html}
        </body>
        </html>
        """
        return render_template_string(full_page)

    return "No reconstruction available for this URL", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
