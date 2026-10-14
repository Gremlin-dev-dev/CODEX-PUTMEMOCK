import os
import json
import random
from datetime import datetime, timedelta, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)

app = Flask(__name__)

# ---------- Config ----------
database_url = os.environ.get("DATABASE_URL", "sqlite:///local_dev.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-me")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)

db = SQLAlchemy(app)
jwt = JWTManager(app)

frontend_origins = os.environ.get("FRONTEND_ORIGIN", "*")
origins_list = [o.strip() for o in frontend_origins.split(",")] if frontend_origins != "*" else "*"
CORS(app, resources={r"/api/*": {"origins": origins_list}})


def get_allowed_emails():
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def get_admin_emails():
    """Emails allowed to view the admin QA panel — separate from ALLOWED_EMAILS,
    since this is about who can review question content, not who can sit the exam."""
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def normalize_jamb(raw):
    return (raw or "").strip().upper().replace(" ", "")


def get_exam_dates():
    raw = os.environ.get("EXAM_DATES", "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        return None
    try:
        return {i + 1: datetime.strptime(parts[i], "%Y-%m-%d").date() for i in range(3)}
    except ValueError:
        return None


COMPULSORY_SUBJECTS = ["English Language", "General Knowledge"]

DEPARTMENT_ELECTIVES = {
    "science": ["Mathematics", "Physics", "Chemistry", "Biology", "Agricultural Science", "Computer Studies", "Economics"],
    "commercial": ["Mathematics", "Economics", "Commerce", "Accounting", "Government", "Marketing"],
    "art": ["Literature in English", "Government", "History",
            "Christian Religious Studies (CRS)", "Islamic Religious Studies (IRS)", "Economics"],
}

EXAM_DURATION_MINUTES = 30
MAX_ATTEMPTS_PER_DAY = 2
QUESTIONS_PER_SUBJECT = 10


# ---------- Models ----------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    jamb_number = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(20), nullable=True)
    subjects = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "jamb_number": self.jamb_number,
            "department": self.department,
            "subjects": self.subjects.split(",") if self.subjects else [],
        }


class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    day = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)

    def to_dict(self, include_answer=False):
        data = {
            "id": self.id,
            "external_id": self.external_id,
            "day": self.day,
            "subject": self.subject,
            "question_text": self.question_text,
            "options": {
                "A": self.option_a, "B": self.option_b,
                "C": self.option_c, "D": self.option_d,
            },
        }
        if include_answer:
            data["correct_option"] = self.correct_option
        return data


class Result(db.Model):
    __tablename__ = "results"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    day = db.Column(db.Integer, nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    subject_breakdown = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "day": self.day,
            "attempt_number": self.attempt_number,
            "score": self.score,
            "total_questions": self.total_questions,
            "percentage": round((self.score / self.total_questions) * 100, 1) if self.total_questions else 0,
            "subject_breakdown": json.loads(self.subject_breakdown) if self.subject_breakdown else [],
            "submitted_at": self.submitted_at.isoformat(),
        }


def seed_questions_from_files():
    day_files = {1: "questions_data/day1.json", 2: "questions_data/day2.json", 3: "questions_data/day3.json"}
    for day, filepath in day_files.items():
        if not os.path.exists(filepath):
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            items = json.load(f)
        for item in items:
            required = ["external_id", "subject", "question_text",
                        "option_a", "option_b", "option_c", "option_d", "correct_option"]
            if any(k not in item for k in required):
                continue
            if item["correct_option"].upper() not in ("A", "B", "C", "D"):
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
            else:
                db.session.add(Question(
                    external_id=item["external_id"], day=day, subject=item["subject"],
                    question_text=item["question_text"], option_a=item["option_a"],
                    option_b=item["option_b"], option_c=item["option_c"],
                    option_d=item["option_d"], correct_option=item["correct_option"].upper(),
                ))
    db.session.commit()


with app.app_context():
    db.create_all()
    seed_questions_from_files()


def get_current_user():
    user_id = get_jwt_identity()
    return db.session.get(User, int(user_id))


def get_allowed_subjects(user):
    return COMPULSORY_SUBJECTS + user.subjects.split(",")


def first_completion_date(user, day):
    first_result = (Result.query
                     .filter_by(user_id=user.id, day=day)
                     .order_by(Result.submitted_at.asc())
                     .first())
    return first_result.submitted_at.date() if first_result else None


def result_release_date(user, day):
    completed_date = first_completion_date(user, day)
    if completed_date is None:
        return None
    return completed_date + timedelta(days=1)


def readiness_verdict(pct):
    if pct >= 80:
        return {"tier": "EXCEPTIONAL", "message": "Exceptional performance. You are more than ready — go and conquer that CBT!", "color": "#16A34A"}
    if pct >= 70:
        return {"tier": "READY", "message": "You are ready. Go and conquer!", "color": "#16A34A"}
    if pct >= 50:
        return {"tier": "SOLID", "message": "Solid foundation. A little more revision on your weak spots and you'll be unstoppable.", "color": "#2563EB"}
    if pct >= 30:
        return {"tier": "GETTING_THERE", "message": "You're getting there. Focus your remaining time on the subjects that pulled your score down.", "color": "#B45309"}
    return {"tier": "NEEDS_WORK", "message": "There's real work to do before exam day — but you still have time. Use this result to guide your revision.", "color": "#DC2626"}


def day_status_for_user(user, day):
    attempts_used = Result.query.filter_by(user_id=user.id, day=day).count()
    today = datetime.now(timezone.utc).date()
    exam_dates = get_exam_dates()

    if day == 1:
        if exam_dates:
            unlocked = today >= exam_dates[1]
            return unlocked, attempts_used, (None if unlocked else exam_dates[1].isoformat())
        return True, attempts_used, None

    previous_day = day - 1
    prev_completed = Result.query.filter_by(user_id=user.id, day=previous_day).count() >= 1

    if exam_dates:
        if not prev_completed:
            return False, attempts_used, None
        date_ok = today >= exam_dates[day]
        return date_ok, attempts_used, (None if date_ok else exam_dates[day].isoformat())
    else:
        prev_completion_date = first_completion_date(user, previous_day)
        if prev_completion_date is None:
            return False, attempts_used, None
        unlock_date = prev_completion_date + timedelta(days=1)
        unlocked = today >= unlock_date
        return unlocked, attempts_used, (None if unlocked else unlock_date.isoformat())


# ---------- Auth routes ----------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    jamb_number = normalize_jamb(data.get("jamb_number"))
    password = data.get("password") or ""

    if not full_name or not email or not password or not jamb_number:
        return jsonify({"error": "Full name, JAMB number, email and password are all required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if email not in get_allowed_emails():
        return jsonify({
            "error": "This email isn't on our invite list yet. Message us on WhatsApp to get added.",
            "code": "NOT_INVITED"
        }), 403
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists. Try logging in instead."}), 409

    user = User(
        full_name=full_name,
        email=email,
        jamb_number=jamb_number,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.to_dict()}), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Incorrect email or password."}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.to_dict()}), 200


@app.get("/api/me")
@jwt_required()
def me():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"user": user.to_dict()}), 200


@app.post("/api/set-department")
@jwt_required()
def set_department():
    data = request.get_json(silent=True) or {}
    department = (data.get("department") or "").strip().lower()
    if department not in DEPARTMENT_ELECTIVES:
        return jsonify({"error": "Department must be science, art, or commercial."}), 400

    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404

    user.department = department
    db.session.commit()
    return jsonify({"user": user.to_dict()}), 200


@app.get("/api/electives")
@jwt_required()
def get_electives():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.department:
        return jsonify({"error": "Choose a department first."}), 400

    return jsonify({"department": user.department, "electives": DEPARTMENT_ELECTIVES[user.department]}), 200


@app.post("/api/set-subjects")
@jwt_required()
def set_subjects():
    data = request.get_json(silent=True) or {}
    chosen = data.get("subjects") or []

    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.department:
        return jsonify({"error": "Choose a department first."}), 400

    valid_options = set(DEPARTMENT_ELECTIVES[user.department])
    chosen = list(dict.fromkeys(chosen))

    if len(chosen) != 3:
        return jsonify({"error": "Please choose exactly 3 subjects."}), 400
    if not all(s in valid_options for s in chosen):
        return jsonify({"error": "One or more subjects aren't valid for your department."}), 400

    user.subjects = ",".join(chosen)
    db.session.commit()
    return jsonify({"user": user.to_dict()}), 200


# ---------- Exam routes ----------
@app.get("/api/exam-status")
@jwt_required()
def exam_status():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.department or not user.subjects:
        return jsonify({"error": "Please choose your department and subjects first."}), 400

    days = []
    for day in (1, 2, 3):
        unlocked, attempts_used, unlock_date = day_status_for_user(user, day)
        days.append({
            "day": day,
            "unlocked": unlocked,
            "unlock_date": unlock_date,
            "attempts_used": attempts_used,
            "attempts_remaining": max(0, MAX_ATTEMPTS_PER_DAY - attempts_used),
        })

    return jsonify({"duration_minutes": EXAM_DURATION_MINUTES, "days": days}), 200


@app.get("/api/results")
@jwt_required()
def get_results():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404

    days = []
    for day in (1, 2, 3):
        attempts = Result.query.filter_by(user_id=user.id, day=day).order_by(Result.submitted_at.asc()).all()
        if not attempts:
            days.append({"day": day, "status": "not_attempted"})
            continue

        release_date = result_release_date(user, day)
        today = datetime.now(timezone.utc).date()

        if today < release_date:
            days.append({
                "day": day,
                "status": "pending",
                "release_date": release_date.isoformat(),
                "attempts_used": len(attempts),
            })
        else:
            best = max(attempts, key=lambda r: r.score)
            days.append({
                "day": day,
                "status": "released",
                "attempts_used": len(attempts),
                "result": best.to_dict(),
            })

    return jsonify({"days": days}), 200


@app.get("/api/profile")
@jwt_required()
def get_profile():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404

    days = []
    all_released = True
    total_score = 0
    total_questions = 0

    for day in (1, 2, 3):
        attempts = Result.query.filter_by(user_id=user.id, day=day).order_by(Result.submitted_at.asc()).all()
        if not attempts:
            days.append({"day": day, "status": "not_attempted"})
            all_released = False
            continue

        release_date = result_release_date(user, day)
        today = datetime.now(timezone.utc).date()

        if today < release_date:
            days.append({
                "day": day,
                "status": "pending",
                "release_date": release_date.isoformat(),
                "attempts_used": len(attempts),
            })
            all_released = False
        else:
            best = max(attempts, key=lambda r: r.score)
            days.append({
                "day": day,
                "status": "released",
                "attempts_used": len(attempts),
                "result": best.to_dict(),
            })
            total_score += best.score
            total_questions += best.total_questions

    overall = None
    if all_released and total_questions > 0:
        overall_pct = round((total_score / total_questions) * 100, 1)
        verdict = readiness_verdict(overall_pct)
        overall = {
            "total_score": total_score,
            "total_questions": total_questions,
            "percentage": overall_pct,
            "tier": verdict["tier"],
            "message": verdict["message"],
            "color": verdict["color"],
        }

    return jsonify({
        "user": user.to_dict(),
        "days": days,
        "overall": overall,
    }), 200


@app.get("/api/questions/<int:day>")
@jwt_required()
def get_questions(day):
    if day not in (1, 2, 3):
        return jsonify({"error": "Day must be 1, 2, or 3."}), 400

    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.department or not user.subjects:
        return jsonify({"error": "Please choose your department and subjects first."}), 400

    unlocked, attempts_used, unlock_date = day_status_for_user(user, day)
    if not unlocked:
        if unlock_date:
            return jsonify({"error": f"Day {day} unlocks on {unlock_date}."}), 403
        return jsonify({"error": f"Day {day} is locked. Complete the previous day first."}), 403
    if attempts_used >= MAX_ATTEMPTS_PER_DAY:
        return jsonify({"error": f"You've used both attempts for Day {day}."}), 403

    allowed_subjects = get_allowed_subjects(user)
    selected = []
    for subject in allowed_subjects:
        pool = (Question.query
                .filter(Question.day == day, Question.subject == subject)
                .all())
        random.shuffle(pool)
        selected.extend(pool[:QUESTIONS_PER_SUBJECT])

    return jsonify({
        "day": day,
        "duration_minutes": EXAM_DURATION_MINUTES,
        "subjects": allowed_subjects,
        "count": len(selected),
        "questions": [q.to_dict(include_answer=False) for q in selected]
    }), 200


@app.post("/api/submit-exam")
@jwt_required()
def submit_exam():
    data = request.get_json(silent=True) or {}
    day = data.get("day")
    answers = data.get("answers") or {}
    question_ids = data.get("question_ids") or []

    if day not in (1, 2, 3):
        return jsonify({"error": "Day must be 1, 2, or 3."}), 400
    if not question_ids:
        return jsonify({"error": "Missing question_ids for this attempt."}), 400

    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.department or not user.subjects:
        return jsonify({"error": "Please choose your department and subjects first."}), 400

    unlocked, attempts_used, unlock_date = day_status_for_user(user, day)
    if not unlocked:
        return jsonify({"error": f"Day {day} is locked."}), 403
    if attempts_used >= MAX_ATTEMPTS_PER_DAY:
        return jsonify({"error": f"You've used both attempts for Day {day}."}), 403

    allowed_subjects = get_allowed_subjects(user)
    questions = (Question.query
                 .filter(Question.id.in_(question_ids),
                         Question.day == day,
                         Question.subject.in_(allowed_subjects))
                 .all())

    score = 0
    subject_breakdown = {}
    for q in questions:
        subject_breakdown.setdefault(q.subject, {"correct": 0, "total": 0})
        subject_breakdown[q.subject]["total"] += 1
        given = answers.get(str(q.id))
        if given and given.upper() == q.correct_option:
            score += 1
            subject_breakdown[q.subject]["correct"] += 1

    breakdown_list = [
        {"subject": subj, "correct": vals["correct"], "total": vals["total"]}
        for subj, vals in subject_breakdown.items()
    ]

    result = Result(
        user_id=user.id,
        day=day,
        attempt_number=attempts_used + 1,
        score=score,
        total_questions=len(questions),
        subject_breakdown=json.dumps(breakdown_list),
    )
    db.session.add(result)
    db.session.commit()

    release_date = result_release_date(user, day)
    return jsonify({
        "message": "Your exam has been submitted successfully.",
        "day": day,
        "attempt_number": result.attempt_number,
        "results_available_on": release_date.isoformat() if release_date else None,
    }), 201


# ---------- Admin QA routes ----------
@app.get("/api/admin/questions/<int:day>")
@jwt_required()
def admin_get_questions(day):
    """Returns EVERY question for a given day, across ALL subjects, with
    correct answers included — for reviewing content/MathJax rendering.
    Gated by ADMIN_EMAILS, completely separate from the exam-taking flow."""
    if day not in (1, 2, 3):
        return jsonify({"error": "Day must be 1, 2, or 3."}), 400

    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.email not in get_admin_emails():
        return jsonify({"error": "Not authorized."}), 403

    questions = (Question.query
                 .filter(Question.day == day)
                 .order_by(Question.subject, Question.id)
                 .all())

    return jsonify({
        "day": day,
        "count": len(questions),
        "questions": [q.to_dict(include_answer=True) for q in questions]
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
