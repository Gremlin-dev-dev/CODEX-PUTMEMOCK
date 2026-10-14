"""
Loads questions from questions_data/day1.json, day2.json, day3.json into the database.

Run this on Render's Shell tab whenever you add or edit questions:
    python seed_questions.py

Safe to re-run: a question is matched by its "external_id", so editing
an existing question's text in the JSON file and re-running this updates it
in place instead of creating a duplicate.
"""
import json
import os

from app import app, db, Question

DAY_FILES = {
    1: "questions_data/day1.json",
    2: "questions_data/day2.json",
    3: "questions_data/day3.json",
}


def load_day(day, filepath):
    if not os.path.exists(filepath):
        print(f"  Skipping day {day}: {filepath} not found.")
        return 0, 0

    with open(filepath, "r", encoding="utf-8") as f:
        items = json.load(f)

    created, updated = 0, 0
    for item in items:
        required = ["external_id", "subject", "question_text",
                    "option_a", "option_b", "option_c", "option_d", "correct_option"]
        missing = [k for k in required if k not in item]
        if missing:
            print(f"  Skipping a day {day} question — missing fields: {missing}")
            continue

        if item["correct_option"].upper() not in ("A", "B", "C", "D"):
            print(f"  Skipping '{item['external_id']}' — correct_option must be A, B, C, or D.")
            continue

        existing = Question.query.filter_by(external_id=item["external_id"]).first()
        if existing:
            existing.day = day
            existing.subject = item["subject"]
            existing.question_text = item["question_text"]
            existing.option_a = item["option_a"]
            existing.option_b = item["option_b"]
            existing.option_c = item["option_c"]
            existing.option_d = item["option_d"]
            existing.correct_option = item["correct_option"].upper()
            updated += 1
        else:
            db.session.add(Question(
                external_id=item["external_id"],
                day=day,
                subject=item["subject"],
                question_text=item["question_text"],
                option_a=item["option_a"],
                option_b=item["option_b"],
                option_c=item["option_c"],
                option_d=item["option_d"],
                correct_option=item["correct_option"].upper(),
            ))
            created += 1

    return created, updated


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        total_created, total_updated = 0, 0
        for day, filepath in DAY_FILES.items():
            print(f"Loading day {day} from {filepath}...")
            c, u = load_day(day, filepath)
            total_created += c
            total_updated += u
        db.session.commit()
        print(f"\nDone. {total_created} question(s) created, {total_updated} updated.")
