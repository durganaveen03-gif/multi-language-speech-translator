
from flask import Flask, render_template, request, jsonify
from gtts import gTTS
from groq import Groq

import sqlite3
import os
import time
import uuid
from threading import Lock
from datetime import datetime


# ==================================
# BASE DIRECTORY
# ==================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

DB_NAME = os.path.join(BASE_DIR, "database.db")

AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)


# ==================================
# GROQ API KEY
# ==================================

GROQ_API_KEY = "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"

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ==================================
# API RATE CONTROL
# ==================================

_api_lock = Lock()
_last_api_call = 0.0
MIN_API_INTERVAL = 2.0


# ==================================
# LANGUAGES
# ==================================

LANGUAGES = {
    "auto": "auto-detect",
    "en": "English",
    "te": "Telugu",
    "hi": "Hindi",
    "ta": "Tamil",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic"
}


# ==================================
# DATABASE
# ==================================

def create_database():

    with sqlite3.connect(DB_NAME) as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original TEXT NOT NULL,
                translated TEXT NOT NULL,
                from_lang TEXT,
                to_lang TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.commit()


# ==================================
# GROQ CLIENT CHECK
# ==================================

def groq_client_or_error():

    if client is None:

        return None, (jsonify({
            "error": "Please add your Groq API key in app.py."
        }), 503)

    return client, None


# ==================================
# API WAIT
# ==================================

def wait_for_api_slot():

    global _last_api_call

    with _api_lock:

        elapsed = time.monotonic() - _last_api_call

        if elapsed < MIN_API_INTERVAL:

            time.sleep(MIN_API_INTERVAL - elapsed)

        _last_api_call = time.monotonic()


# ==================================
# SAVE HISTORY
# ==================================

def save_history(original, translated, source, target):

    try:

        with sqlite3.connect(DB_NAME) as conn:

            conn.execute(
                """
                INSERT INTO history
                (original, translated, from_lang, to_lang, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    original,
                    translated,
                    source,
                    target,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )

            conn.commit()

    except sqlite3.Error as exc:

        app.logger.warning("Could not save history: %s", exc)


# ==================================
# HOME
# ==================================

@app.route("/")
def home():

    return render_template("index.html")


# ==================================
# TRANSLATION
# ==================================

@app.route("/translate", methods=["POST"])
def translate():

    data = request.get_json(silent=True) or {}

    text = (data.get("text") or "").strip()

    source = (data.get("from_lang") or "auto").strip()

    target = (data.get("to_lang") or "en").strip()

    if not text:

        return jsonify({
            "error": "Please enter or record some text."
        }), 400

    if len(text) > 5000:

        return jsonify({
            "error": "Text too long. Please use 5000 characters or fewer."
        }), 400

    if target not in LANGUAGES or target == "auto":

        return jsonify({
            "error": "Please select a valid target language."
        }), 400

    if source not in LANGUAGES:

        source = "auto"

    api, error_response = groq_client_or_error()

    if error_response:

        return error_response

    source_name = LANGUAGES.get(source, "auto-detect")

    target_name = LANGUAGES[target]

    if source != "auto" and source == target:

        save_history(text, text, source, target)

        return jsonify({
            "translated": text,
            "from_lang": source,
            "to_lang": target
        })

    prompt = (
        "You are a professional translator. Translate the user's text faithfully into "
        f"{target_name}. Source language: {source_name}. "
        "If source language is auto-detect, identify it yourself. "
        "Return only the translated text, with no explanation, labels, or quotation marks. "
        "Preserve meaning, names, numbers, formatting, and tone."
    )

    try:

        wait_for_api_slot()

        completion = api.chat.completions.create(

            model="openai/gpt-oss-20b",

            messages=[
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": text
                }
            ],

            temperature=0.1,

            max_completion_tokens=2048
        )

        translated = (
            completion.choices[0].message.content or ""
        ).strip()

        if not translated:

            return jsonify({
                "error": "Translation service returned an empty result. Try again."
            }), 502

        save_history(text, translated, source, target)

        return jsonify({
            "translated": translated,
            "from_lang": source,
            "to_lang": target
        })

    except Exception as exc:

        message = str(exc)

        app.logger.exception("Translation failed")

        if "429" in message or "rate_limit" in message.lower() or "rate limit" in message.lower():

            return jsonify({
                "error": "Groq API rate limit reached. Please wait and try again, or check your Groq account limits."
            }), 429

        return jsonify({
            "error": "Translation failed. Check your internet connection, GROQ_API_KEY, and terminal error."
        }), 502


# ==================================
# MICROPHONE TRANSCRIPTION
# ==================================

@app.route("/transcribe", methods=["POST"])
def transcribe():

    if "audio" not in request.files:

        return jsonify({
            "error": "No microphone audio received. Please allow microphone permission and record again."
        }), 400

    audio_file = request.files["audio"]

    audio_bytes = audio_file.read()

    if not audio_bytes:

        return jsonify({
            "error": "The audio recording is empty. Speak for a few seconds and try again."
        }), 400

    api, error_response = groq_client_or_error()

    if error_response:

        return error_response

    filename = audio_file.filename or "recording.webm"

    ext = os.path.splitext(filename)[1].lower()

    if ext not in {
        ".webm", ".wav", ".mp3", ".m4a",
        ".mp4", ".mpeg", ".mpga", ".ogg", ".flac"
    }:

        ext = ".webm"

    try:

        wait_for_api_slot()

        result = api.audio.transcriptions.create(

            file=(f"recording{ext}", audio_bytes),

            model="whisper-large-v3-turbo",

            response_format="json"
        )

        transcript = (getattr(result, "text", "") or "").strip()

        if not transcript:

            return jsonify({
                "error": "Speech was not detected. Speak clearly and try again."
            }), 422

        return jsonify({
            "text": transcript
        })

    except Exception as exc:

        message = str(exc)

        app.logger.exception("Microphone transcription failed")

        if "429" in message or "rate_limit" in message.lower() or "rate limit" in message.lower():

            return jsonify({
                "error": "Audio transcription API rate limit reached. Wait a little and try again."
            }), 429

        return jsonify({
            "error": "Could not transcribe audio. Check internet, API key, and terminal error."
        }), 502


# ==================================
# TEXT TO SPEECH
# ==================================

@app.route("/speak", methods=["POST"])
def speak():

    data = request.get_json(silent=True) or {}

    text = (data.get("text") or "").strip()

    language = (data.get("language") or "en").strip()

    if not text:

        return jsonify({
            "error": "No text provided to speak."
        }), 400

    if language not in LANGUAGES or language == "auto":

        language = "en"

    try:

        filename = f"{uuid.uuid4().hex}.mp3"

        filepath = os.path.join(AUDIO_DIR, filename)

        gTTS(
            text=text[:5000],
            lang=language
        ).save(filepath)

        return jsonify({
            "audio": f"/static/audio/{filename}"
        })

    except Exception:

        app.logger.exception("Text-to-speech failed")

        return jsonify({
            "error": "Text-to-speech failed. Check internet connection and selected language."
        }), 502


# ==================================
# HISTORY
# ==================================

@app.route("/history", methods=["GET"])
def history():

    try:

        with sqlite3.connect(DB_NAME) as conn:

            rows = conn.execute(
                """
                SELECT id, original, translated,
                from_lang, to_lang, created_at
                FROM history
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()

        return jsonify(rows)

    except sqlite3.Error:

        app.logger.exception("History read failed")

        return jsonify({
            "error": "Could not load history."
        }), 500


# ==================================
# CLEAR HISTORY
# ==================================

@app.route("/clear", methods=["POST"])
def clear_history():

    try:

        with sqlite3.connect(DB_NAME) as conn:

            conn.execute("DELETE FROM history")

            conn.commit()

        return jsonify({
            "message": "History cleared."
        })

    except sqlite3.Error:

        app.logger.exception("History clear failed")

        return jsonify({
            "error": "Could not clear history."
        }), 500


# ==================================
# AI EXPLANATION
# ==================================

@app.route("/ai", methods=["POST"])
def ai_explain():

    data = request.get_json(silent=True) or {}

    text = (data.get("text") or "").strip()

    if not text:

        return jsonify({
            "error": "Please enter text for AI explanation."
        }), 400

    api, error_response = groq_client_or_error()

    if error_response:

        return error_response

    try:

        wait_for_api_slot()

        completion = api.chat.completions.create(

            model="openai/gpt-oss-20b",

            messages=[
                {
                    "role": "system",
                    "content": "Explain the meaning of the user's text in simple, clear language. If helpful, give a short Telugu explanation too. Do not invent context."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],

            temperature=0.2,

            max_completion_tokens=1024
        )

        answer = (
            completion.choices[0].message.content or ""
        ).strip()

        return jsonify({
            "response": answer
        })

    except Exception as exc:

        app.logger.exception("AI explanation failed")

        if "429" in str(exc) or "rate_limit" in str(exc).lower():

            return jsonify({
                "error": "Groq API rate limit reached. Wait and try again."
            }), 429

        return jsonify({
            "error": "AI explanation failed. Check API key, internet, and terminal error."
        }), 502


# ==================================
# START APPLICATION
# ==================================

create_database()


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
