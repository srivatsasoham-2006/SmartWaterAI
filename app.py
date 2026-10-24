
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import sqlite3
import math
import re

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_PATH = BASE_DIR / "smartwater.db"
data_lock = Lock()

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)

@app.route("/debug-logo")
def debug_logo():
    logo_file = STATIC_DIR / "logo.png"
    return {
        "app_root": str(app.root_path),
        "static_folder": str(app.static_folder),
        "static_dir": str(STATIC_DIR),
        "logo_exists": logo_file.is_file(),
        "logo_size_bytes": logo_file.stat().st_size if logo_file.is_file() else 0,
        "static_files": [f.name for f in STATIC_DIR.iterdir()] if STATIC_DIR.is_dir() else []
    }

SENSOR_FIELDS = {
    "ph": (0, 14),
    "turbidity": (0, None),
    "tds": (0, None),
    "temp": (-10, 100),
    "oxygen": (0, None),
}

# Dataset tables must start with this prefix.
DATASET_PREFIX = "dataset_col_"


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


def analyze_water_quality(readings):
    thresholds = {
        "ph": (6.5, 8.5, "pH"),
        "turbidity": (None, 5.0, "Turbidity"),
        "tds": (None, 500.0, "Total dissolved solids"),
        "temp": (None, 35.0, "Temperature"),
        "oxygen": (5.0, None, "Dissolved oxygen"),
    }

    issues = []
    checked = []

    for field, (low, high, label) in thresholds.items():
        value = readings.get(field)

        if value is None:
            continue

        checked.append(field)

        if low is not None and value < low:
            issues.append(
                f"{label} is below the configured screening range."
            )

        if high is not None and value > high:
            issues.append(
                f"{label} is above the configured screening range."
            )

    if not checked:
        status = "insufficient_data"
        message = "No supported sensor measurements are available."
    elif issues:
        status = "warning"
        message = "One or more measurements need further investigation."
    else:
        status = "screening_normal"
        message = "No configured threshold violations were detected."

    return {
        "status": status,
        "message": message,
        "checked_sensors": checked,
        "issues": issues,
        "method": "rule_based_screening",
        "is_ai_model": False,
        "disclaimer": (
            "Preliminary screening only. This result does not certify "
            "water as safe to drink."
        )
    }


# -------------------- DATASET HELPERS --------------------

def get_dataset_tables(connection):
    """Return only tables using the expected dataset prefix."""
    rows = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name LIKE ?
        ORDER BY name
    """, (DATASET_PREFIX + "%",)).fetchall()

    return [row["name"] for row in rows]


def valid_dataset_table(table_name, connection):
    """Verify the requested table exists before querying it."""
    if not isinstance(table_name, str):
        return False

    if not re.fullmatch(r"dataset_col_[A-Za-z0-9_]+", table_name):
        return False

    return table_name in get_dataset_tables(connection)


def quote_identifier(identifier):
    """Safely quote a validated SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


# -------------------- FRONTEND --------------------

@app.get("/")
@app.get("/index.html")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(STATIC_DIR, "favicon.ico", mimetype="image/x-icon")


@app.get("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


# -------------------- HEALTH API --------------------

@app.get("/api/health")
def health():
    return jsonify({
        "status": "online",
        "project": "SmartWater AI",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": "SQLite"
    })


# -------------------- SENSOR APIs --------------------

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
        })

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

    return jsonify({
        "status": "success",
        "message": "Sensor readings saved to SQLite.",
        "reading": row_to_dict(row)
    }), 201


@app.get("/api/analysis/latest")
def get_latest_analysis():
    with data_lock:
        with get_db_connection() as connection:
            row = connection.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
            ).fetchone()

    if row is None:
        return jsonify({
            "status": "no_data",
            "message": "No sensor readings are available for analysis."
        })

    readings = {
        field: row[field]
        for field in SENSOR_FIELDS
        if row[field] is not None
    }

    return jsonify({
        "timestamp": row["timestamp"],
        "readings": readings,
        "analysis": analyze_water_quality(readings)
    })


# -------------------- DATASET APIs --------------------

@app.get("/api/datasets")
def list_datasets():
    with data_lock:
        with get_db_connection() as connection:
            tables = get_dataset_tables(connection)
            datasets = []

            for table_name in tables:
                table = quote_identifier(table_name)

                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]

                columns = connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()

                datasets.append({
                    "name": table_name,
                    "row_count": count,
                    "columns": [column["name"] for column in columns]
                })

    return jsonify({
        "status": "success",
        "count": len(datasets),
        "datasets": datasets,
        "message": (
            "Datasets loaded."
            if datasets
            else "No dataset tables found. Expected table names "
                 "beginning with dataset_col_."
        )
    })


@app.get("/api/datasets/<table_name>")
def get_dataset(table_name):
    with data_lock:
        with get_db_connection() as connection:
            if not valid_dataset_table(table_name, connection):
                return jsonify({
                    "status": "error",
                    "message": "Dataset table not found."
                }), 404

            table = quote_identifier(table_name)

            columns = connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()

            rows = connection.execute(
                f"SELECT * FROM {table} LIMIT 500"
            ).fetchall()

            records = [dict(row) for row in rows]

    return jsonify({
        "status": "success",
        "dataset": table_name,
        "columns": [column["name"] for column in columns],
        "count": len(records),
        "limit": 500,
        "rows": records
    })


@app.post("/api/datasets/<table_name>/test")
def test_dataset(table_name):
    with data_lock:
        with get_db_connection() as connection:
            if not valid_dataset_table(table_name, connection):
                return jsonify({
                    "status": "error",
                    "message": "Dataset table not found."
                }), 404

            table = quote_identifier(table_name)

            try:
                result = connection.execute(
                    f"SELECT * FROM {table} LIMIT 1"
                ).fetchone()

                return jsonify({
                    "status": "success",
                    "dataset": table_name,
                    "message": "Dataset table can be queried.",
                    "has_data": result is not None
                })

            except sqlite3.Error as error:
                return jsonify({
                    "status": "error",
                    "message": str(error)
                }), 500


# Create the database and sensor table when the app starts.
initialize_database()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
