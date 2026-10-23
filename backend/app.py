
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import sqlite3
import math

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database stored beside this root-level app.py
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


def analyze_water_quality(readings):
    """Preliminary rule-based screening, not a trained AI model."""

    issues = []
    checked = []

    thresholds = {
        "ph": (6.5, 8.5, "pH"),
        "turbidity": (None, 5.0, "Turbidity"),
        "tds": (None, 500.0, "Total dissolved solids"),
        "temp": (None, 35.0, "Temperature"),
        "oxygen": (5.0, None, "Dissolved oxygen"),
    }

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


# -------------------- WEBSITE --------------------

@app.get("/")
@app.get("/index.html")
def home():
    return send_from_directory(
        Path(__file__).resolve().parent,
        "index.html"
    )


# -------------------- HEALTH API --------------------

@app.get("/api/health")
def health():
    return jsonify({
        "status": "online",
        "project": "SmartWater AI",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": "SQLite"
    })


# -------------------- SENSOR READING APIs --------------------

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


# -------------------- WATER QUALITY ANALYSIS API --------------------

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

def get_dataset_catalog():
    with get_db_connection() as connection:
        rows = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name LIKE 'dataset_col_%'
            ORDER BY name
        """).fetchall()

        datasets = []

        for row in rows:
            table_name = row["name"]
            safe_table = '"' + table_name.replace('"', '""') + '"'

            count = connection.execute(
                "SELECT COUNT(*) FROM " + safe_table
            ).fetchone()[0]

            datasets.append({
                "table": table_name,
                "records": count
            })

    return datasets


@app.get("/api/datasets")
def list_datasets():
    datasets = get_dataset_catalog()

    return jsonify({
        "status": "success",
        "count": len(datasets),
        "datasets": datasets
    })


@app.get("/api/datasets/<table_name>")
def get_dataset_records(table_name):
    datasets = get_dataset_catalog()
    allowed_tables = {item["table"] for item in datasets}

    if table_name not in allowed_tables:
        return jsonify({
            "status": "error",
            "message": "Dataset not found."
        }), 404

    try:
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({
            "status": "error",
            "message": "limit and offset must be integers."
        }), 400

    if limit < 1 or limit > 100 or offset < 0:
        return jsonify({
            "status": "error",
            "message": "Use limit 1-100 and offset 0 or greater."
        }), 400

    safe_table = '"' + table_name.replace('"', '""') + '"'

    with get_db_connection() as connection:
        columns = connection.execute(
            "PRAGMA table_info(" + safe_table + ")"
        ).fetchall()

        records = connection.execute(
            "SELECT * FROM " + safe_table + " LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()

        total = connection.execute(
            "SELECT COUNT(*) FROM " + safe_table
        ).fetchone()[0]

    return jsonify({
        "status": "success",
        "dataset": table_name,
        "total_records": total,
        "limit": limit,
        "offset": offset,
        "columns": [column["name"] for column in columns],
        "records": [dict(record) for record in records]
    })


@app.post("/api/datasets/<table_name>/test")
def test_dataset_record(table_name):
    datasets = get_dataset_catalog()
    allowed_tables = {item["table"] for item in datasets}

    if table_name not in allowed_tables:
        return jsonify({
            "status": "error",
            "message": "Dataset not found."
        }), 404

    data = request.get_json(silent=True) or {}

    try:
        record_number = int(data.get("record_number", 1))
    except (ValueError, TypeError):
        return jsonify({
            "status": "error",
            "message": "record_number must be an integer."
        }), 400

    if record_number < 1:
        return jsonify({
            "status": "error",
            "message": "record_number starts at 1."
        }), 400

    safe_table = '"' + table_name.replace('"', '""') + '"'

    with get_db_connection() as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM " + safe_table
        ).fetchone()[0]

        if record_number > total:
            return jsonify({
                "status": "error",
                "message": f"Choose a record from 1 to {total}."
            }), 400

        columns = connection.execute(
            "PRAGMA table_info(" + safe_table + ")"
        ).fetchall()

        record = connection.execute(
            "SELECT * FROM " + safe_table + " LIMIT 1 OFFSET ?",
            (record_number - 1,)
        ).fetchone()

    return jsonify({
        "status": "success",
        "dataset": table_name,
        "record_number": record_number,
        "total_records": total,
        "columns": [column["name"] for column in columns],
        "record": dict(record),
        "analysis": {
            "method": "dataset_record_inspection",
            "message": (
                "Record retrieved successfully. No trained AI prediction "
                "has been performed."
            )
        }
    })


# -------------------- STARTUP --------------------

initialize_database()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
