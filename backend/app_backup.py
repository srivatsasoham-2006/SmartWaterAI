
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import sqlite3
import math

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database file will be created inside the backend folder.
DATABASE_PATH = Path(__file__).resolve().parent / "smartwater.db"
data_lock = Lock()

SENSOR_FIELDS = {
    "ph": (0, 14),
    "turbidity": (0, None),
    "tds": (0, None),
    "temp": (-10, 100),
    "oxygen": (0, None),
}


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ph REAL,
                turbidity REAL,
                tds REAL,
                temp REAL,
                oxygen REAL
            )
        """)


def row_to_dict(row):
    if row is None:
        return None

    return {
        "timestamp": row["timestamp"],
        **{
            field: row[field]
            for field in SENSOR_FIELDS
            if row[field] is not None
        }
    }


def validate_readings(data):
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object."

    cleaned = {}

    for field, (minimum, maximum) in SENSOR_FIELDS.items():
        if field not in data or data[field] is None:
            continue

        value = data[field]

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return None, f"{field} must be a finite numeric value."

        if value < minimum:
            return None, f"{field} is below the accepted input range."

        if maximum is not None and value > maximum:
            return None, f"{field} is above the accepted input range."

        cleaned[field] = value

    if not cleaned:
        return None, "Include at least one valid sensor reading."

    return cleaned, None


@app.get("/")
def home():
    return jsonify({
        "project": "SmartWater AI",
        "message": "Water quality monitoring API is running.",
        "status": "online",
        "data_mode": "real_submissions_only",
        "storage": "SQLite",
        "endpoints": {
            "health": "/api/health",
            "latest": "/api/readings/latest",
            "history": "/api/readings/history",
            "submit": "/api/readings"
        }
    })


@app.get("/api/health")
def health():
    return jsonify({
        "status": "online",
        "project": "SmartWater AI",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": "SQLite"
    })


@app.get("/api/readings/latest")
def get_latest_readings():
    with data_lock:
        with get_db_connection() as connection:
            row = connection.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
            ).fetchone()

    data = row_to_dict(row)

    if data is None:
        return jsonify({
            "status": "no_data",
            "message": "No sensor readings have been submitted yet.",
            "readings": None
        }), 200

    return jsonify({
        "status": "data_available",
        "readings": data
    })


@app.get("/api/readings/history")
def get_readings_history():
    with data_lock:
        with get_db_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT 1000"
            ).fetchall()

    records = [row_to_dict(row) for row in reversed(rows)]

    return jsonify({
        "count": len(records),
        "readings": records
    })


@app.post("/api/readings")
def submit_readings():
    data = request.get_json(silent=True)
    cleaned, error = validate_readings(data)

    if error:
        return jsonify({
            "status": "error",
            "message": error
        }), 400

    timestamp = datetime.now(timezone.utc).isoformat()

    values = {
        field: cleaned.get(field)
        for field in SENSOR_FIELDS
    }

    with data_lock:
        with get_db_connection() as connection:
            cursor = connection.execute("""
                INSERT INTO readings
                (timestamp, ph, turbidity, tds, temp, oxygen)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                values["ph"],
                values["turbidity"],
                values["tds"],
                values["temp"],
                values["oxygen"]
            ))

            row = connection.execute(
                "SELECT * FROM readings WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()

    record = row_to_dict(row)

    return jsonify({
        "status": "success",
        "message": "Sensor readings saved to SQLite.",
        "reading": record
    }), 201


# Create the database and table when the app starts.
initialize_database()


if __name__ == "__main__":
    # Local development only.
    app.run(host="127.0.0.1", port=5000, debug=False)
