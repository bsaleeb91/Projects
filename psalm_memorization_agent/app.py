"""
Psalm Memorization Agent — Flask application entry point.
"""

import os
import secrets
import smtplib
import string
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

load_dotenv()

import database as db
import psalms as psalm_data
from evaluation import evaluate, make_blank_version, make_first_letter_version, tokenize, normalize_word
from scoring import calculate_points
import claude_feedback

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = db.get_user_by_id(session["user_id"])
        if not user or user["role"] != "teacher":
            flash("Teacher access required.", "danger")
            return redirect(url_for("student_dashboard"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
        if user and user["role"] == "teacher":
            return redirect(url_for("teacher_dashboard"))
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "magic_link":
            email = request.form.get("email", "").strip().lower()
            user = db.get_user_by_email(email)
            if not user:
                flash("No account found with that email. Please ask your teacher to add you.", "warning")
                return render_template("login.html")
            _send_magic_link(user)
            flash("Check your email for a login link!", "success")
            return render_template("login.html")

        elif action == "login_code":
            code = request.form.get("code", "").strip().upper()
            link_row = db.get_login_code(code)
            if not link_row:
                flash("Invalid code.", "danger")
                return render_template("login.html")
            if link_row["used"]:
                flash("This code has already been used.", "danger")
                return render_template("login.html")
            if datetime.fromisoformat(link_row["expires_at"]) < datetime.utcnow():
                flash("This code has expired. Ask your teacher for a new one.", "danger")
                return render_template("login.html")
            db.consume_login_code(code)
            _log_in_user(link_row["user_id"])
            return _redirect_by_role(link_row["user_id"])

    return render_template("login.html")


@app.route("/auth/verify/<token>")
def verify_magic_link(token):
    link_row = db.get_magic_link(token)
    if not link_row:
        flash("Invalid or expired login link.", "danger")
        return redirect(url_for("login"))
    if link_row["used"]:
        flash("This link has already been used.", "danger")
        return redirect(url_for("login"))
    if datetime.fromisoformat(link_row["expires_at"]) < datetime.utcnow():
        flash("This link has expired. Request a new one.", "danger")
        return redirect(url_for("login"))
    db.consume_magic_link(token)
    _log_in_user(link_row["user_id"])
    return _redirect_by_role(link_row["user_id"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def student_dashboard():
    user = db.get_user_by_id(session["user_id"])
    if user["role"] == "teacher":
        return redirect(url_for("teacher_dashboard"))

    score = db.get_score(user["id"])
    votd = db.get_verse_of_the_day()
    current_psalm_id, current_chunk, current_mode = _get_current_position(user["id"])

    psalm = psalm_data.get_psalm(current_psalm_id) if current_psalm_id else None
    psalm_title = psalm["title"] if psalm else None

    return render_template(
        "student_dashboard.html",
        user=user,
        score=score,
        votd=votd,
        current_psalm_id=current_psalm_id,
        current_chunk=current_chunk,
        current_mode=current_mode,
        psalm_title=psalm_title,
    )


@app.route("/progress")
@login_required
def my_progress():
    user = db.get_user_by_id(session["user_id"])
    all_progress = {row["psalm_id"]: row for row in db.get_psalm_progress_all(user["id"])}

    psalms_status = []
    first_locked = None
    for pid in range(1, 9):
        progress = all_progress.get(pid)
        if progress and progress["mastered"]:
            status = "mastered"
        elif progress or pid == 1:
            # unlocked if psalm 1 or previous is mastered
            status = "in_progress"
        else:
            prev_progress = all_progress.get(pid - 1)
            if prev_progress and prev_progress["mastered"]:
                status = "in_progress"
            else:
                status = "locked"
                if first_locked is None:
                    first_locked = pid

        psalms_status.append({
            "psalm_id": pid,
            "title": psalm_data.get_psalm(pid)["title"],
            "status": status,
            "mastery_count": progress["mastery_count"] if progress else 0,
        })

    return render_template("my_progress.html", user=user, psalms_status=psalms_status)


@app.route("/leaderboard")
@login_required
def leaderboard():
    user = db.get_user_by_id(session["user_id"])
    rows = db.get_leaderboard()
    return render_template("leaderboard.html", user=user, rows=rows)


@app.route("/drill/<int:psalm_id>/<int:chunk_number>/<mode>", methods=["GET", "POST"])
@login_required
def drill(psalm_id: int, chunk_number: int, mode: str):
    user = db.get_user_by_id(session["user_id"])
    if user["role"] == "teacher":
        return redirect(url_for("teacher_dashboard"))

    psalm = psalm_data.get_psalm(psalm_id)
    total_chunks = psalm_data.get_total_chunks(psalm_id)

    # For single-verse psalms, chunk_number=1 is the only chunk
    effective_chunk = chunk_number if total_chunks > 0 else 1
    correct_text = psalm_data.get_chunk_text(psalm_id, effective_chunk)
    chunk_word_count = psalm_data.count_words(correct_text)
    full_psalm_text = psalm_data.get_chunk_text(psalm_id, 0)
    psalm_word_count = psalm_data.count_words(full_psalm_text)

    cp = db.get_or_create_chunk_progress(user["id"], psalm_id, effective_chunk, mode)

    feedback_message = None
    result = None

    if request.method == "POST":
        if mode == "study":
            # Mark study as complete and move to blank mode
            db.mark_chunk_completed(user["id"], psalm_id, effective_chunk, "study")
            return redirect(url_for("drill", psalm_id=psalm_id, chunk_number=effective_chunk, mode="blank"))

        typed = request.form.get("typed_text", "").strip()
        eval_result = evaluate(typed, correct_text)
        score = eval_result["score"]

        # Determine pass threshold
        pass_threshold = 0.80 if mode in ("blank", "letters") else 0.80
        passed = score >= pass_threshold

        # Update streak before scoring
        db.update_streak(user["id"])
        current_score = db.get_score(user["id"])
        streak = current_score["current_streak"] if current_score else 0

        # Check mastery conditions
        is_chunk_mastery = False
        is_psalm_mastery = False
        is_first_in_class = False

        if passed:
            db.increment_chunk_success(user["id"], psalm_id, effective_chunk, mode)
            cp_fresh = db.get_chunk_progress(user["id"], psalm_id, effective_chunk, mode)
            new_success = cp_fresh["success_count"]

            if mode == "recitation" and new_success >= 3:
                db.mark_chunk_completed(user["id"], psalm_id, effective_chunk, mode)
                is_chunk_mastery = True

                # Check if this was the full psalm (chunk_number==0) or all chunks done
                if effective_chunk == 0:
                    # This was a full psalm recitation
                    db.update_psalm_mastery_count(user["id"], psalm_id)
                    psalm_prog = db.get_or_create_psalm_progress(user["id"], psalm_id)
                    if psalm_prog["mastery_count"] >= 3 or (psalm_prog["mastery_count"] + 1) >= 3:
                        is_psalm_mastery = True
                        is_first = db.is_first_to_master(user["id"], psalm_id)
                        avg_acc = db.get_average_accuracy(user["id"], psalm_id)
                        if is_first and avg_acc >= 0.90:
                            is_first_in_class = True
            elif mode in ("blank", "letters") and new_success >= 1:
                # Mode unlocked after first pass — mark complete and advance
                db.mark_chunk_completed(user["id"], psalm_id, effective_chunk, mode)

        # Calculate points
        points = calculate_points(
            psalm_id=psalm_id,
            chunk_number=effective_chunk,
            mode=mode,
            passed=passed,
            is_chunk_mastery=is_chunk_mastery,
            is_psalm_mastery=is_psalm_mastery,
            streak=streak,
            is_first_in_class=is_first_in_class,
            psalm_word_count=psalm_word_count,
            chunk_word_count=chunk_word_count,
        )

        db.record_attempt(
            user["id"], psalm_id, effective_chunk, mode,
            typed, score, passed, points,
        )

        if points > 0:
            db.add_total_points(user["id"], points)
            db.add_points_to_psalm(user["id"], psalm_id, points)

        # Generate feedback
        if passed:
            import random
            feedback_message = random.choice(psalm_data.SUCCESS_MESSAGES)
            if is_chunk_mastery and effective_chunk > 0:
                chunk_msgs = psalm_data.CHUNK_MASTERY_MESSAGES.get(psalm_id, {})
                feedback_message = chunk_msgs.get(effective_chunk, feedback_message)
            if is_psalm_mastery:
                feedback_message = psalm_data.PSALM_MASTERY_MESSAGES.get(psalm_id, feedback_message)
        else:
            recent = [dict(r) for r in db.get_recent_attempts(user["id"], psalm_id, effective_chunk, 5)]
            feedback_message = claude_feedback.get_feedback(
                correct_text=correct_text,
                typed_text=typed,
                mode=mode,
                recent_attempts=recent,
                psalm_title=psalm["title"],
            )

        result = {
            "score": score,
            "passed": passed,
            "points": points,
            "is_chunk_mastery": is_chunk_mastery,
            "is_psalm_mastery": is_psalm_mastery,
            "details": eval_result["details"],
        }

        # Determine next step URL
        next_url = _next_step_url(user["id"], psalm_id, effective_chunk, mode, passed,
                                  is_chunk_mastery, is_psalm_mastery, total_chunks)

        return render_template(
            "drill.html",
            user=user,
            psalm=psalm,
            psalm_id=psalm_id,
            chunk_number=effective_chunk,
            mode=mode,
            correct_text=correct_text,
            result=result,
            feedback_message=feedback_message,
            next_url=next_url,
            chunk_display=_make_display_text(correct_text, mode),
        )

    # GET: render drill screen
    return render_template(
        "drill.html",
        user=user,
        psalm=psalm,
        psalm_id=psalm_id,
        chunk_number=effective_chunk,
        mode=mode,
        correct_text=correct_text,
        result=None,
        feedback_message=None,
        next_url=None,
        chunk_display=_make_display_text(correct_text, mode),
        cp=cp,
    )


# ---------------------------------------------------------------------------
# Teacher routes
# ---------------------------------------------------------------------------

@app.route("/teacher")
@teacher_required
def teacher_dashboard():
    user = db.get_user_by_id(session["user_id"])
    overview = db.get_class_overview()
    for student in overview:
        if student["current_psalm_id"]:
            student["psalm_title"] = psalm_data.get_psalm(student["current_psalm_id"])["title"]
        else:
            student["psalm_title"] = "—"
    return render_template("teacher_dashboard.html", user=user, overview=overview)


@app.route("/teacher/student/<int:student_id>")
@teacher_required
def student_detail(student_id: int):
    user = db.get_user_by_id(session["user_id"])
    student = db.get_user_by_id(student_id)
    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
        return redirect(url_for("teacher_dashboard"))
    attempts = db.get_all_attempts_for_student(student_id)
    score = db.get_score(student_id)
    psalm_progress = {row["psalm_id"]: row for row in db.get_psalm_progress_all(student_id)}

    psalms_status = []
    for pid in range(1, 9):
        prog = psalm_progress.get(pid)
        psalms_status.append({
            "psalm_id": pid,
            "title": psalm_data.get_psalm(pid)["title"],
            "mastered": prog["mastered"] if prog else False,
            "mastery_count": prog["mastery_count"] if prog else 0,
            "points_earned": prog["points_earned"] if prog else 0,
        })

    return render_template(
        "student_detail.html",
        user=user,
        student=student,
        attempts=attempts,
        score=score,
        psalms_status=psalms_status,
    )


@app.route("/teacher/admin", methods=["GET", "POST"])
@teacher_required
def admin():
    user = db.get_user_by_id(session["user_id"])
    students = db.get_all_students()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_student":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if not name or not email:
                flash("Name and email are required.", "warning")
            elif db.get_user_by_email(email):
                flash("A user with that email already exists.", "warning")
            else:
                db.create_user(email, name, role="student")
                flash(f"Student '{name}' added.", "success")
            return redirect(url_for("admin"))

        elif action == "remove_student":
            student_id = int(request.form.get("student_id", 0))
            db.delete_user(student_id)
            flash("Student removed.", "success")
            return redirect(url_for("admin"))

        elif action == "set_votd":
            verse = request.form.get("verse", "").strip()
            if verse:
                db.set_verse_of_the_day(verse, user["id"])
                flash("Verse of the Day updated.", "success")
            return redirect(url_for("admin"))

        elif action == "generate_code":
            student_id = int(request.form.get("student_id", 0))
            student = db.get_user_by_id(student_id)
            if not student:
                flash("Student not found.", "danger")
            else:
                code = _generate_login_code()
                expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
                db.create_login_code(student_id, code, expires_at)
                flash(f"Login code for {student['name']}: {code} (valid 15 min)", "info")
            return redirect(url_for("admin"))

    return render_template("admin.html", user=user, students=students,
                           votd=db.get_verse_of_the_day())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_magic_link(user):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    db.create_magic_link(user["id"], token, expires_at)
    link = f"{BASE_URL}/auth/verify/{token}"

    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        # SMTP not configured — just flash the link for dev purposes
        flash(f"[DEV] Magic link: {link}", "info")
        return

    try:
        msg = MIMEText(
            f"Hello {user['name']},\n\nClick this link to log in to the Psalm Memorization app:\n\n{link}\n\nThis link expires in 1 hour.",
            "plain",
        )
        msg["Subject"] = "Your Psalm Memorization Login Link"
        msg["From"] = os.getenv("EMAIL_FROM", os.getenv("SMTP_USER", ""))
        msg["To"] = user["email"]

        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", 587))) as smtp:
            smtp.starttls()
            smtp.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
    except Exception:
        flash(f"[DEV] Magic link (email failed): {link}", "warning")


def _generate_login_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


def _log_in_user(user_id: int):
    session["user_id"] = user_id
    db.update_last_login(user_id)


def _redirect_by_role(user_id: int):
    user = db.get_user_by_id(user_id)
    if user and user["role"] == "teacher":
        return redirect(url_for("teacher_dashboard"))
    return redirect(url_for("student_dashboard"))


def _get_current_position(user_id: int) -> tuple[int | None, int | None, str | None]:
    """
    Determine where a student should pick up next.
    Returns (psalm_id, chunk_number, mode) or (None, None, None) if all mastered.
    """
    for psalm_id in range(1, 9):
        psalm = psalm_data.get_psalm(psalm_id)
        total_chunks = psalm_data.get_total_chunks(psalm_id)

        # Check if this psalm is fully mastered
        psalm_prog = db.get_or_create_psalm_progress(user_id, psalm_id)
        if psalm_prog["mastered"]:
            continue

        # Determine chunk progression
        chunks_to_check = list(range(1, total_chunks + 1)) if total_chunks > 0 else [1]

        for chunk_num in chunks_to_check:
            for mode in ("study", "blank", "letters", "recitation"):
                cp = db.get_chunk_progress(user_id, psalm_id, chunk_num, mode)
                if cp is None or not cp["completed"]:
                    return psalm_id, chunk_num, mode

        # All chunks done — check if full psalm recitation unlocked
        if total_chunks > 0:
            # Check full psalm recitation (chunk_number=0)
            for mode in ("study", "blank", "letters", "recitation"):
                cp = db.get_chunk_progress(user_id, psalm_id, 0, mode)
                if cp is None or not cp["completed"]:
                    return psalm_id, 0, mode

    return None, None, None


def _next_step_url(user_id: int, psalm_id: int, chunk_number: int, mode: str,
                   passed: bool, is_chunk_mastery: bool, is_psalm_mastery: bool,
                   total_chunks: int) -> str:
    """Return the URL for the 'Continue' button after an attempt."""
    if not passed:
        return url_for("drill", psalm_id=psalm_id, chunk_number=chunk_number, mode=mode)

    mode_order = ["study", "blank", "letters", "recitation"]

    if mode in ("blank", "letters"):
        # Advance to next mode for this chunk
        next_mode_idx = mode_order.index(mode) + 1
        return url_for("drill", psalm_id=psalm_id, chunk_number=chunk_number,
                       mode=mode_order[next_mode_idx])

    if mode == "recitation" and is_chunk_mastery:
        if chunk_number == 0:
            # Full psalm mastered or still working toward 3x
            psalm_prog = db.get_or_create_psalm_progress(user_id, psalm_id)
            if psalm_prog["mastered"]:
                # Unlock next psalm
                next_psalm_id = psalm_id + 1
                if next_psalm_id <= 8:
                    return url_for("drill", psalm_id=next_psalm_id, chunk_number=1, mode="study")
                return url_for("student_dashboard")
            else:
                return url_for("drill", psalm_id=psalm_id, chunk_number=0, mode="recitation")
        else:
            # Check if all sub-chunks mastered
            if db.all_chunks_mastered(user_id, psalm_id, total_chunks):
                # Advance to full psalm practice
                return url_for("drill", psalm_id=psalm_id, chunk_number=0, mode="study")
            else:
                # Next chunk
                next_chunk = chunk_number + 1
                return url_for("drill", psalm_id=psalm_id, chunk_number=next_chunk, mode="study")

    # Default: retry same
    return url_for("drill", psalm_id=psalm_id, chunk_number=chunk_number, mode=mode)


def _make_display_text(correct_text: str, mode: str) -> str:
    if mode == "study":
        return correct_text
    if mode == "blank":
        blanked, _ = make_blank_version(correct_text)
        return blanked
    if mode == "letters":
        return make_first_letter_version(correct_text)
    return ""  # recitation — no display


# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------

@app.before_request
def initialize():
    db.init_db()
    # Only run once
    app.before_request_funcs[None].remove(initialize)


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True)
