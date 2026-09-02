#!/usr/bin/env python
"""Bulk-create Meta2bAnalyst user accounts from a CSV file.

Usage (inside the backend container):

    docker cp students.csv meta2banalyst-backend-1:/tmp/students.csv
    docker exec meta2banalyst-backend-1 python /app/scripts/create_users.py /tmp/students.csv

CSV format (header row optional):

    username,password[,role][,quota_mb]
    s2026001,pass1234
    s2026002,pass5678,student,1000

Existing usernames are skipped, not overwritten. Print a summary at the end.
"""
import csv
import sys
from pathlib import Path

# Allow running as a plain script from /app inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402


def main(csv_path: str) -> int:
    db = SessionLocal()
    created, skipped, failed = 0, 0, 0
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.reader(f) if r and r[0].strip()]
        # Tolerate a header row.
        if rows and rows[0][0].strip().lower() in ("username", "user", "name"):
            rows = rows[1:]
        for row in rows:
            username = row[0].strip()
            password = row[1].strip() if len(row) > 1 else ""
            role = row[2].strip() if len(row) > 2 and row[2].strip() else "student"
            quota_mb = None
            if len(row) > 3 and row[3].strip():
                try:
                    quota_mb = int(row[3].strip())
                except ValueError:
                    print(f"  ! {username}: invalid quota '{row[3]}', using default")
            if not username or len(password) < 6:
                print(f"  ! skipped {username or row}: username empty or password < 6 chars")
                failed += 1
                continue
            if db.query(User).filter(User.username == username).first():
                print(f"  - {username}: already exists, skipped")
                skipped += 1
                continue
            db.add(User(username=username, password_hash=hash_password(password),
                        role=role, quota_mb=quota_mb))
            db.commit()
            print(f"  + {username} (role={role}, quota={quota_mb or 'default'})")
            created += 1
    finally:
        db.close()
    print(f"\nDone: {created} created, {skipped} already existed, {failed} invalid rows.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
