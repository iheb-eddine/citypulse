"""Re-classify existing seed reports using AI. Reads. Reads images from disk, no re-downloading."""

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.database import SessionLocal, create_tables
from app.models import Report
from app.classifier import classify_image

BASE_DIR = Path(__file__).resolve().parent.parent / "app"


def main():
    create_tables()
    db = SessionLocal()
    try:
        reports = db.query(Report).filter(Report.category == "unclassified").all()
        print(f"{len(reports)} reports need classification.")
        classified = 0
        failed = 0

        for i, r in enumerate(reports):
            img_path = BASE_DIR / r.photo_path.lstrip("/").replace("static/", "static/", 1)
            if not img_path.exists():
                print(f"  [{i+1}/{len(reports)}] SKIP — file missing: {r.photo_path}")
                failed += 1
                continue

            result = classify_image(img_path.read_bytes())

            if result["category"] == "unclassified":
                failed += 1
                print(f"  [{i+1}/{len(reports)}] SKIP — AI unavailable")
                time.sleep(4)
                continue

            r.category = result["category"]
            r.severity = result["severity"]
            r.department = result["department"]
            r.description = result["description"]
            classified += 1
            print(f"  [{i+1}/{len(reports)}] {result['category']} ({result['severity']})")
            time.sleep(2)

        db.commit()
        print(f"\nDone. Classified: {classified}, Failed: {failed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
