import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder="static")
CORS(app)

PERSONA = open("persona.txt", encoding="utf-8").read()
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = "claude-sonnet-4-6"

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/breakdown", methods=["POST"])
def breakdown():
    body     = request.get_json(force=True)
    senaryo  = body.get("senaryo", "")
    anacast  = body.get("anacast", "")

    json_instr = """

Çıktını SADECE geçerli JSON olarak ver. Kod bloğu veya açıklama ekleme:
{"scenes":[{"sahne":"1","bolum":"","gun":"1","zaman":"İÇ/GECE","sayfa":"1","mekan":"MEKAN","oyuncular":[],"yrd_oyuncular":[],"sac":[],"makyaj":[],"kostum":[],"sanat":[],"araclar":[],"produksiyon":[],"teknik":[],"cgi_vfx":[],"sfx":[],"sound_design":[],"reji_notlar":[],"aciklama":"","notlar":""}]}"""

    user_msg = ""
    if anacast.strip():
        user_msg += f"AnaCast Beyaz Listesi:\n{anacast.strip()}\n\n---\n\n"
    user_msg += f"SENARYO:\n{senaryo.strip()}{json_instr}"

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": MODEL,
            "max_tokens": 4000,
            "system": PERSONA,
            "messages": [{"role": "user", "content": user_msg}]
        },
        timeout=119
    )

    if resp.status_code != 200:
        return jsonify({"error": resp.text}), resp.status_code

    data = resp.json()
    if "error" in data:
        return jsonify({"error": data["error"]["message"]}), 400

    txt = "".join(b.get("text","") for b in data.get("content",[]))

    import json, re
    try:
        result = json.loads(txt)
    except:
        m = re.search(r'\{[\s\S]*\}', txt)
        if m:
            result = json.loads(m.group(0))
        else:
            return jsonify({"error": "JSON parse edilemedi", "raw": txt[:500]}), 500

    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
