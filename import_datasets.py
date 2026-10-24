"""Import the 10 SmartWater AI CSV datasets into the existing SQLite database.
Place this script in the SmartWaterAi project root, alongside the backend folder
and the datasets folder. It only replaces tables named dataset_* and leaves the
existing sensor readings tables untouched.
"""
import csv
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "datasets"
DB_PATH = ROOT / "backend" / "smartwater.db"


def safe_identifier(value):
    value = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    if not value or value[0].isdigit():
        value = "col_" + value
    return value


def main():
    if not DATA_DIR.exists():
        raise SystemExit(f"Dataset folder not found: {DATA_DIR}")
    if not DB_PATH.exists():
        raise SystemExit(
            f"Database not found: {DB_PATH}\n"
            "Run your SmartWater AI backend once first so it creates smartwater.db."
        )

    files = sorted(DATA_DIR.glob("*.csv"))
    if len(files) != 10:
        raise SystemExit(f"Expected 10 CSV files in {DATA_DIR}, found {len(files)}")

    db = sqlite3.connect(DB_PATH)
    results = []
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS dataset_catalog (
            dataset_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            table_name TEXT NOT NULL UNIQUE,
            record_count INTEGER NOT NULL,
            columns_json TEXT NOT NULL
        )""")
        import json
        for path in files:
            dataset_id = safe_identifier(path.stem.lower())
            table = "dataset_" + dataset_id
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    print(f"SKIP {path.name}: no header row")
                    continue
                original_headers = reader.fieldnames
                headers = [safe_identifier(h) for h in original_headers]
                if len(set(headers)) != len(headers):
                    raise ValueError(f"Duplicate column names after cleanup in {path.name}: {headers}")
                # Replace only this import's table so rerunning the script won't duplicate rows.
                db.execute(f'DROP TABLE IF EXISTS "{table}"')
                cols_sql = ", ".join(f'"{h}" TEXT' for h in headers)
                db.execute(f'CREATE TABLE "{table}" ("_row_id" INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})')
                placeholders = ", ".join("?" for _ in headers)
                insert_sql = f'INSERT INTO "{table}" ({", ".join(chr(34)+h+chr(34) for h in headers)}) VALUES ({placeholders})'
                count = 0
                for row in reader:
                    values = [row.get(h, "") for h in original_headers]
                    db.execute(insert_sql, values)
                    count += 1
                db.execute(
                    "INSERT OR REPLACE INTO dataset_catalog(dataset_id,file_name,table_name,record_count,columns_json) VALUES(?,?,?,?,?)",
                    (dataset_id, path.name, table, count, json.dumps(headers))
                )
                results.append((path.name, table, count, len(headers)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\nSmartWater AI dataset import complete")
    print(f"Database: {DB_PATH}")
    total = 0
    for filename, table, count, columns in results:
        total += count
        print(f"{filename}: {count:,} records, {columns} columns -> {table}")
    print(f"TOTAL IMPORTED: {total:,} records across {len(results)} datasets")
    print("Existing sensor tables were not modified.")

if __name__ == "__main__":
    main()
