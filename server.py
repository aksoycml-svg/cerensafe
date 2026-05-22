import os
import json
import re
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder="static")
CORS(app)

PERSONA = open("persona.txt", encoding="utf-8").read()
API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "setap2024")
MODEL        = "claude-sonnet-4-6"

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/breakdown", methods=["POST"])
def breakdown():
    if request.headers.get("X-App-Password", "") != APP_PASSWORD:
        return jsonify({"error": "Yetkisiz erişim"}), 401

    body    = request.get_json(force=True)
    senaryo = body.get("senaryo", "")
    anacast = body.get("anacast", "")

    json_instr = """

Çıktını SADECE geçerli JSON olarak ver. Kod bloğu veya açıklama ekleme:
{"scenes":[{"sahne":"1","bolum":"","gun":"1","zaman":"İÇ/GECE","sayfa":"1","mekan":"MEKAN","oyuncular":[],"yrd_oyuncular":[],"sac":[],"makyaj":[],"kostum":[],"sanat":[],"araclar":[],"produksiyon":[],"teknik":[],"cgi_vfx":[],"sfx":[],"sound_design":[],"reji_notlar":[],"aciklama":"","notlar":""}]}"""

    user_msg = ""
    if anacast.strip():
        user_msg += f"AnaCast Beyaz Listesi:\n{anacast.strip()}\n\n---\n\n"
    user_msg += f"SENARYO:\n{senaryo.strip()}{json_instr}"

    def generate():
        accumulated = []
        try:
            with requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": MODEL,
                    "max_tokens": 10000,
                    "stream": True,
                    "system": PERSONA,
                    "messages": [{"role": "user", "content": user_msg}]
                },
                stream=True,
                timeout=119
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except Exception:
                        continue

                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            accumulated.append(chunk)
                            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

                    elif event.get("type") == "message_stop":
                        break

        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'İstek zaman aşımına uğradı'})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        full_text = "".join(accumulated)

        def clean_and_parse(text):
            # markdown code block temizle
            text = re.sub(r'^```[a-zA-Z]*\s*', '', text.strip())
            text = re.sub(r'\s*```$', '', text.strip())
            # geçersiz kontrol karakterlerini temizle (tab/newline hariç)
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
            # doğrudan parse dene
            try:
                return json.loads(text)
            except Exception:
                pass
            # JSON objesini metinden çıkar
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                return json.loads(m.group(0))
            raise ValueError("JSON bulunamadı")

        try:
            result = clean_and_parse(full_text)
        except Exception:
            yield f"data: {json.dumps({'error': 'JSON parse edilemedi', 'raw': full_text[:500]})}\n\n"
            return

        yield f"data: {json.dumps({'done': True, 'result': result})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
