"""
Pro Jirga — Backend
====================
Flask backend with email verification, sessions, and full UI wiring.

Run:
    cd Backend && python app.py
"""

import os
import re
import random
import sqlite3
import uuid
import json
import urllib.request
import tempfile
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    request,
    jsonify,
    g,
    render_template,
    redirect,
    url_for,
    send_from_directory,
    session,
    flash,
    abort,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.realpath(os.path.normpath(os.path.join(BASE_DIR, "..", "Frontend")))
DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "skillledger.db")
if not os.access(os.path.dirname(DB_PATH), os.W_OK):
    DB_PATH = os.path.join(tempfile.gettempdir(), "skillledger.db")
static_dir = os.path.realpath(os.path.join(FRONTEND_DIR, "statics"))

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=static_dir,
    static_url_path="/static",
)
app.secret_key = os.environ.get("SECRET_KEY", "pro-jirga-dev-secret-change-in-production")
app.config["DEBUG"] = True

CODE_EXPIRY_MINUTES = 10
DB_INITIALIZED = False

@app.before_request
def ensure_database():
    global DB_INITIALIZED
    if not DB_INITIALIZED:
        init_db()
        DB_INITIALIZED = True


# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate_db(conn):
    """Migrate legacy phone-based schema to email-based schema."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(user)").fetchall()}

    if "phone" in cols and "email" not in cols:
        conn.executescript("""
        CREATE TABLE user_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            email_verified INTEGER DEFAULT 0,
            user_type TEXT NOT NULL,
            field TEXT NOT NULL,
            github_username TEXT,
            credibility_score REAL DEFAULT 0,
            match_score REAL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        INSERT INTO user_new (id, name, email, email_verified, user_type, field, github_username,
            credibility_score, match_score, created_at)
        SELECT id, name, phone || '@legacy.pro-jirga.local', 1, user_type, field, github_username,
            credibility_score, match_score, created_at FROM user;
        DROP TABLE user;
        ALTER TABLE user_new RENAME TO user;
        """)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(user)").fetchall()}

    if "email" not in cols:
        conn.execute("ALTER TABLE user ADD COLUMN email TEXT")
    if "email_verified" not in cols:
        conn.execute("ALTER TABLE user ADD COLUMN email_verified INTEGER DEFAULT 0")

    ecols = {row[1] for row in conn.execute("PRAGMA table_info(endorsement)").fetchall()}
    if "endorser_phone" in ecols and "endorser_email" not in ecols:
        conn.execute("ALTER TABLE endorsement ADD COLUMN endorser_email TEXT")
        conn.execute("UPDATE endorsement SET endorser_email = endorser_phone WHERE endorser_email IS NULL")
    elif "endorser_email" not in ecols:
        conn.execute("ALTER TABLE endorsement ADD COLUMN endorser_email TEXT")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS verification_code (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        email_verified INTEGER DEFAULT 0,
        user_type TEXT NOT NULL,
        field TEXT NOT NULL,
        github_username TEXT,
        credibility_score REAL DEFAULT 0,
        match_score REAL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS contribution (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        proof_type TEXT DEFAULT 'manual',
        complexity_weight REAL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES user (id)
    );

    CREATE TABLE IF NOT EXISTS endorsement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contribution_id INTEGER NOT NULL,
        endorser_email TEXT NOT NULL,
        token TEXT UNIQUE NOT NULL,
        confirmed INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (contribution_id) REFERENCES contribution (id)
    );

    CREATE TABLE IF NOT EXISTS rating (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rater_id INTEGER NOT NULL,
        rated_user_id INTEGER NOT NULL,
        stars INTEGER NOT NULL,
        tag TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS verification_code (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    migrate_db(conn)
    conn.commit()
    conn.close()


def user_public_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "user_type": row["user_type"],
        "field": row["field"],
        "github_username": row["github_username"],
        "credibility_score": round(row["credibility_score"], 2),
        "match_score": round(row["match_score"], 2),
        "display_credibility": normalized_credibility(row["credibility_score"]),
    }


def normalized_credibility(score):
    return min(100, round(float(score or 0) * 10, 1))


def time_ago(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00").split("+")[0])
        delta = datetime.utcnow() - dt
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                return "Just now"
            return f"{hours}h ago"
        if days == 1:
            return "1 day ago"
        if days < 7:
            return f"{days} days ago"
        if days < 30:
            return f"{days // 7} week(s) ago"
        return f"{days // 30} month(s) ago"
    except (ValueError, TypeError):
        return "Recently"


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()


def login_user(user_id):
    session["user_id"] = user_id
    session.permanent = True


def logout_user():
    session.clear()


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("landing"))
        return f(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    user = get_current_user()
    return {
        "current_user": user,
        "normalized_credibility": normalized_credibility,
        "time_ago": time_ago,
    }


def valid_email(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email or ""))


def generate_code():
    return f"{random.randint(100000, 999999)}"


def send_verification_email(email, code):
    """Dev mode: log code to console. Replace with SMTP in production."""
    print(f"\n{'='*50}\n  Pro Jirga — Verification code for {email}: {code}\n{'='*50}\n")
    return True


def store_verification_code(email):
    db = get_db()
    code = generate_code()
    expires = (datetime.utcnow() + timedelta(minutes=CODE_EXPIRY_MINUTES)).isoformat()
    db.execute("DELETE FROM verification_code WHERE email = ?", (email,))
    db.execute(
        "INSERT INTO verification_code (email, code, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email, code, expires, datetime.utcnow().isoformat()),
    )
    db.commit()
    send_verification_email(email, code)
    return code


def verify_code(email, code):
    db = get_db()
    row = db.execute(
        "SELECT * FROM verification_code WHERE email = ? AND code = ? ORDER BY id DESC LIMIT 1",
        (email, code),
    ).fetchone()
    if not row:
        return False
    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        return False
    db.execute("DELETE FROM verification_code WHERE email = ?", (email,))
    db.commit()
    return True


def find_user_by_slug(slug):
    db = get_db()
    user = db.execute("SELECT * FROM user WHERE github_username = ?", (slug,)).fetchone()
    if user:
        return user
    user = db.execute("SELECT * FROM user WHERE email = ?", (slug,)).fetchone()
    if user:
        return user
    user = db.execute("SELECT * FROM user WHERE email LIKE ?", (f"{slug}@%",)).fetchone()
    if user:
        return user
    if slug.isdigit():
        return db.execute("SELECT * FROM user WHERE id = ?", (int(slug),)).fetchone()
    return None


def user_slug(user):
    return user["github_username"] or user["email"].split("@")[0]


def get_user_contributions(user_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM contribution WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    result = []
    for c in rows:
        confirmed = db.execute(
            "SELECT COUNT(*) FROM endorsement WHERE contribution_id = ? AND confirmed = 1",
            (c["id"],),
        ).fetchone()[0]
        result.append({
            "id": c["id"],
            "title": c["title"],
            "description": c["description"] or "",
            "source": "GitHub" if c["proof_type"] == "github" else "Manual",
            "timestamp": time_ago(c["created_at"]),
            "complexity_score": min(10, max(1, round(c["complexity_weight"] * 5))),
            "confirmed_endorsements": confirmed,
        })
    return result


def credibility_breakdown(user_id):
    db = get_db()
    contributions = db.execute(
        "SELECT * FROM contribution WHERE user_id = ?", (user_id,)
    ).fetchall()
    github_pts = 0.0
    manual_pts = 0.0
    endorsement_pts = 0.0
    for c in contributions:
        pts = c["complexity_weight"]
        if c["proof_type"] == "github":
            github_pts += pts
        else:
            manual_pts += pts
        confirmed = db.execute(
            "SELECT COUNT(*) FROM endorsement WHERE contribution_id = ? AND confirmed = 1",
            (c["id"],),
        ).fetchone()[0]
        endorsement_pts += confirmed * 0.5 * c["complexity_weight"]
    items = []
    if github_pts:
        items.append({"label": f"GitHub contributions", "value": f"+{round(github_pts, 1)}"})
    if manual_pts:
        items.append({"label": f"Manual proof of work", "value": f"+{round(manual_pts, 1)}"})
    if endorsement_pts:
        items.append({"label": f"Peer endorsements", "value": f"+{round(endorsement_pts, 1)}"})
    if not items:
        items.append({"label": "No contributions yet", "value": "0"})
    return items


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------
def recalculate_credibility_score(user_id):
    db = get_db()
    contributions = db.execute(
        "SELECT * FROM contribution WHERE user_id = ?", (user_id,)
    ).fetchall()
    total = 0.0
    for c in contributions:
        confirmed_count = db.execute(
            "SELECT COUNT(*) FROM endorsement WHERE contribution_id = ? AND confirmed = 1",
            (c["id"],),
        ).fetchone()[0]
        total += c["complexity_weight"] * (1 + 0.5 * confirmed_count)
    db.execute("UPDATE user SET credibility_score = ? WHERE id = ?", (total, user_id))
    db.commit()
    return total


def recalculate_match_score(user_id):
    db = get_db()
    ratings = db.execute(
        "SELECT * FROM rating WHERE rated_user_id = ?", (user_id,)
    ).fetchall()
    if not ratings:
        db.execute("UPDATE user SET match_score = 0.0 WHERE id = ?", (user_id,))
        db.commit()
        return 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    for r in ratings:
        rater = db.execute("SELECT * FROM user WHERE id = ?", (r["rater_id"],)).fetchone()
        if not rater:
            continue
        cred = rater["credibility_score"]
        if cred is None:
            cred = 0.0
        weight = max(cred, 0.1)
        weighted_sum += r["stars"] * weight
        weight_total += weight
    score = weighted_sum / weight_total if weight_total > 0 else 0.0
    db.execute("UPDATE user SET match_score = ? WHERE id = ?", (score, user_id))
    db.commit()
    return score


# ---------------------------------------------------------------------------
# STATIC
# ---------------------------------------------------------------------------
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# ---------------------------------------------------------------------------
# AUTH — EMAIL VERIFICATION
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def landing():
    if get_current_user():
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login/email", methods=["POST"])
def login_email():
    email = request.form.get("email", "").strip().lower()
    if not valid_email(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("landing"))
    store_verification_code(email)
    session["pending_email"] = email
    flash("Verification code sent! Check your inbox (or server console in dev mode).", "success")
    return redirect(url_for("verify_email_page", email=email))


@app.route("/verify-email", methods=["GET"])
def verify_email_page():
    email = request.args.get("email") or session.get("pending_email", "")
    if not email:
        return redirect(url_for("landing"))
    dev_code = None
    if app.config["DEBUG"]:
        row = get_db().execute(
            "SELECT code FROM verification_code WHERE email = ? ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()
        dev_code = row["code"] if row else None
    return render_template("verify_email.html", email=email, dev_code=dev_code)


@app.route("/verify-email", methods=["POST"])
def verify_email_submit():
    email = request.form.get("email", "").strip().lower()
    code = request.form.get("code", "").strip()
    if not verify_code(email, code):
        flash("Invalid or expired code. Please try again.", "error")
        return redirect(url_for("verify_email_page", email=email))

    db = get_db()
    user = db.execute("SELECT * FROM user WHERE email = ?", (email,)).fetchone()
    session.pop("pending_email", None)

    if user:
        db.execute("UPDATE user SET email_verified = 1 WHERE id = ?", (user["id"],))
        db.commit()
        login_user(user["id"])
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    session["verified_email"] = email
    return redirect(url_for("register"))


@app.route("/register", methods=["GET", "POST"])
def register():
    email = session.get("verified_email")
    if not email:
        flash("Please verify your email first.", "warning")
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        user_type = request.form.get("user_type", "professional")
        field = request.form.get("field", "").strip()
        github = request.form.get("github_username", "").strip() or None

        if not name or not field:
            flash("Name and field are required.", "error")
            return render_template("register.html", email=email)

        db = get_db()
        existing = db.execute("SELECT id FROM user WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("Account already exists. Please sign in.", "warning")
            return redirect(url_for("landing"))

        cur = db.execute(
            "INSERT INTO user (name, email, email_verified, user_type, field, github_username, created_at) "
            "VALUES (?, ?, 1, ?, ?, ?, ?)",
            (name, email, user_type, field, github, datetime.utcnow().isoformat()),
        )
        db.commit()
        login_user(cur.lastrowid)
        session.pop("verified_email", None)
        flash(f"Welcome to Pro Jirga, {name}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html", email=email)


@app.route("/login/github", methods=["GET"])
def login_github():
    flash("GitHub OAuth coming soon. Use email sign-in for now.", "info")
    return redirect(url_for("landing"))


@app.route("/logout", methods=["GET"])
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("landing"))


# ---------------------------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------------------------
@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    user = get_current_user()
    contributions = get_user_contributions(user["id"])
    breakdown = credibility_breakdown(user["id"])
    user_data = dict(user)
    user_data["credibility_breakdown"] = breakdown
    return render_template("dashboard.html", user=user_data, contributions=contributions)


@app.route("/add-contribution", methods=["GET", "POST"], endpoint="add_contribution_page")
@login_required
def add_contribution_page():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if not title:
            flash("Title is required.", "error")
            return render_template("add_contribution.html")

        user = get_current_user()
        complexity = 1.0
        if request.files.get("proof") and request.files["proof"].filename:
            complexity = 1.5

        db = get_db()
        db.execute(
            "INSERT INTO contribution (user_id, title, description, proof_type, complexity_weight, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], title, description, "manual", complexity, datetime.utcnow().isoformat()),
        )
        db.commit()
        recalculate_credibility_score(user["id"])
        flash("Contribution logged successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_contribution.html")


@app.route("/profile/<username>", methods=["GET"])
def profile(username):
    user = find_user_by_slug(username)
    if not user:
        abort(404)
    contributions = get_user_contributions(user["id"])
    breakdown = credibility_breakdown(user["id"])
    user_data = dict(user)
    user_data["credibility_breakdown"] = breakdown
    is_own = get_current_user() and get_current_user()["id"] == user["id"]
    return render_template(
        "dashboard.html",
        user=user_data,
        contributions=contributions,
        is_profile=True,
        is_own=is_own,
        profile_slug=user_slug(user),
    )


@app.route("/company", methods=["GET"])
def company_view():
    db = get_db()
    field = request.args.get("field")
    min_rating = request.args.get("min_rating", type=float)
    sort_by = request.args.get("sort", "match_score")

    query = "SELECT * FROM user WHERE email_verified = 1"
    params = []
    if field:
        query += " AND field = ?"
        params.append(field)
    if min_rating is not None:
        query += " AND match_score >= ?"
        params.append(min_rating)
    query += " ORDER BY credibility_score DESC" if sort_by == "credibility_score" else " ORDER BY match_score DESC"

    users = db.execute(query, params).fetchall()
    candidates = []
    for u in users:
        ratings = db.execute(
            "SELECT stars FROM rating WHERE rated_user_id = ?", (u["id"],)
        ).fetchall()
        avg_stars = sum(r["stars"] for r in ratings) / len(ratings) if ratings else 0
        tags = [
            r["tag"] for r in db.execute(
                "SELECT tag FROM rating WHERE rated_user_id = ? AND tag IS NOT NULL LIMIT 3",
                (u["id"],),
            ).fetchall()
        ]
        candidates.append({
            "id": u["id"],
            "name": u["name"],
            "field": u["field"],
            "credibility_score": normalized_credibility(u["credibility_score"]),
            "match_score": round(u["match_score"], 1),
            "avg_stars": round(avg_stars, 1),
            "tags": tags or [u["field"]],
            "slug": user_slug(u),
        })

    fields = [r[0] for r in db.execute("SELECT DISTINCT field FROM user").fetchall()]
    return render_template(
        "company_view.html",
        candidates=candidates,
        fields=fields,
        current_sort=sort_by,
        current_min_rating=min_rating,
        current_field=field,
    )


@app.route("/challenge", methods=["GET"])
@login_required
def challenge_page():
    passed = request.args.get("passed") == "1"
    challenge = {
        "title": "Debug the failing checkout flow",
        "prompt": (
            "A payment webhook is intermittently double-charging users. "
            "Given the attached repo and logs, identify the root cause and submit a fix. "
            "You may submit a link to a PR or upload a patch file."
        ),
        "time_limit_min": 30,
    }
    return render_template("challenge.html", challenge=challenge, passed=passed, score_delta=7)


@app.route("/challenge/submit", methods=["POST"])
@login_required
def challenge_submit():
    user = get_current_user()
    db = get_db()
    db.execute(
        "INSERT INTO contribution (user_id, title, description, proof_type, complexity_weight, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user["id"],
            "Skill challenge: Debug checkout flow",
            "Passed skill challenge verification",
            "manual",
            1.4,
            datetime.utcnow().isoformat(),
        ),
    )
    db.commit()
    recalculate_credibility_score(user["id"])
    flash("Challenge passed! +7 credibility points.", "success")
    return redirect(url_for("challenge_page", passed=1))


@app.route("/rate/<username>", methods=["GET"])
@login_required
def rate_profile_page(username):
    user = find_user_by_slug(username)
    if not user:
        abort(404)
    if get_current_user()["id"] == user["id"]:
        flash("You cannot rate yourself.", "warning")
        return redirect(url_for("profile", username=username))
    return render_template("rate_profile.html", user=user, profile_slug=user_slug(user))


@app.route("/rate/<username>", methods=["POST"])
@login_required
def rate_profile_submit(username):
    user = find_user_by_slug(username)
    if not user:
        abort(404)
    rater = get_current_user()
    stars = int(request.form.get("stars", 0))
    tag = request.form.get("tag", "").strip()

    if not (1 <= stars <= 5):
        flash("Please select a star rating.", "error")
        return redirect(url_for("rate_profile_page", username=username))

    db = get_db()
    shared = db.execute(
        """SELECT e.id FROM endorsement e
           JOIN contribution c ON e.contribution_id = c.id
           WHERE c.user_id = ? AND e.endorser_email = ? AND e.confirmed = 1
           LIMIT 1""",
        (user["id"], rater["email"]),
    ).fetchone()
    if shared is None and rater["id"] != user["id"]:
        flash("Rating requires at least one confirmed endorsement on this profile.", "warning")
        return redirect(url_for("profile", username=username))

    existing = db.execute(
        "SELECT id FROM rating WHERE rater_id = ? AND rated_user_id = ?",
        (rater["id"], user["id"]),
    ).fetchone()
    if existing:
        flash("You have already rated this person.", "info")
        return redirect(url_for("profile", username=username))

    db.execute(
        "INSERT INTO rating (rater_id, rated_user_id, stars, tag, created_at) VALUES (?, ?, ?, ?, ?)",
        (rater["id"], user["id"], stars, tag, datetime.utcnow().isoformat()),
    )
    db.commit()
    recalculate_match_score(user["id"])
    flash("Rating submitted. Thank you!", "success")
    return redirect(url_for("profile", username=username))


@app.route("/endorse/<token>", methods=["GET"])
def endorse_confirm_page(token):
    db = get_db()
    endorsement = db.execute("SELECT * FROM endorsement WHERE token = ?", (token,)).fetchone()
    if not endorsement:
        abort(404)
    contribution = db.execute(
        "SELECT * FROM contribution WHERE id = ?", (endorsement["contribution_id"],)
    ).fetchone()
    owner = db.execute("SELECT * FROM user WHERE id = ?", (contribution["user_id"],)).fetchone()
    return render_template(
        "endorse_confirm.html",
        endorsement=endorsement,
        contribution=contribution,
        owner=owner,
        confirmed=bool(endorsement["confirmed"]),
        token=token,
    )


@app.route("/endorse/<token>", methods=["POST"])
def endorse_confirm_submit(token):
    db = get_db()
    endorsement = db.execute("SELECT * FROM endorsement WHERE token = ?", (token,)).fetchone()
    if not endorsement:
        abort(404)
    if not endorsement["confirmed"]:
        db.execute("UPDATE endorsement SET confirmed = 1 WHERE token = ?", (token,))
        db.commit()
        contribution = db.execute(
            "SELECT * FROM contribution WHERE id = ?", (endorsement["contribution_id"],)
        ).fetchone()
        recalculate_credibility_score(contribution["user_id"])
        flash("Endorsement confirmed. Thank you!", "success")
    return redirect(url_for("endorse_confirm_page", token=token))

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/login/phone', methods=['GET'])
def login_phone():
    # Phone login is not implemented yet; redirect to the landing page for login options.
    return redirect(url_for('landing'))


@app.route("/contributions/<int:contribution_id>/request-endorsement", methods=["GET", "POST"])
@login_required
def request_endorsement_page(contribution_id):
    db = get_db()
    contribution = db.execute("SELECT * FROM contribution WHERE id = ?", (contribution_id,)).fetchone()
    if not contribution:
        abort(404)
    user = get_current_user()
    if contribution["user_id"] != user["id"]:
        abort(403)

    if request.method == "POST":
        endorser_email = request.form.get("endorser_email", "").strip().lower()
        if not valid_email(endorser_email):
            flash("Please enter a valid endorser email.", "error")
            return render_template("request_endorsement.html", contribution=contribution)

        token = str(uuid.uuid4())
        db.execute(
            "INSERT INTO endorsement (contribution_id, endorser_email, token, created_at) VALUES (?, ?, ?, ?)",
            (contribution_id, endorser_email, token, datetime.utcnow().isoformat()),
        )
        db.commit()
        confirm_url = url_for("endorse_confirm_page", token=token, _external=True)
        send_verification_email(endorser_email, f"Endorsement link: {confirm_url}")
        flash(f"Endorsement request sent to {endorser_email}. Share link: {confirm_url}", "success")
        return redirect(url_for("dashboard"))

    return render_template("request_endorsement.html", contribution=contribution)


def fetch_github_repos(github_username):
    url = f"https://api.github.com/users/{github_username}/repos?sort=updated&per_page=5"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Pro-Jirga-App"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching GitHub repos: {e}")
        return None

def get_mock_github_repos(github_username):
    return [
        {
            "name": "react-dashboard-pro",
            "description": "A high-performance analytics dashboard component with smooth animations.",
            "language": "TypeScript",
            "stargazers_count": 142,
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "name": "fastapi-jwt-auth",
            "description": "Secure JWT authentication middleware for FastAPI with Redis token blacklist.",
            "language": "Python",
            "stargazers_count": 89,
            "updated_at": (datetime.utcnow() - timedelta(days=5)).isoformat()
        },
        {
            "name": "graphql-schema-linter",
            "description": "CLI tool to lint GraphQL schemas against custom style guides.",
            "language": "JavaScript",
            "stargazers_count": 45,
            "updated_at": (datetime.utcnow() - timedelta(days=12)).isoformat()
        }
    ]

@app.route("/sync-github", methods=["POST"])
@login_required
def sync_github():
    user = get_current_user()
    github_username = user["github_username"]
    if not github_username:
        flash("Please update your profile to include a GitHub username first.", "warning")
        return redirect(url_for("dashboard"))

    repos = fetch_github_repos(github_username)
    is_mock = False
    if repos is None or not isinstance(repos, list):
        repos = get_mock_github_repos(github_username)
        is_mock = True

    db = get_db()
    synced_count = 0
    for repo in repos:
        repo_name = repo.get("name")
        if not repo_name:
            continue
        title = f"{github_username}/{repo_name}"
        
        # Check if already exists
        existing = db.execute(
            "SELECT id FROM contribution WHERE user_id = ? AND title = ?",
            (user["id"], title)
        ).fetchone()
        
        if not existing:
            description = repo.get("description") or "GitHub repository"
            lang = repo.get("language")
            stars = repo.get("stargazers_count", 0)
            if lang:
                description += f" [Language: {lang}]"
            if stars > 0:
                description += f" [Stars: {stars} ★]"
                
            complexity = 1.2 + min(0.6, stars * 0.01)
            created = repo.get("updated_at") or datetime.utcnow().isoformat()
            
            db.execute(
                "INSERT INTO contribution (user_id, title, description, proof_type, complexity_weight, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], title, description, "github", complexity, created)
            )
            synced_count += 1

    if synced_count > 0:
        db.commit()
        recalculate_credibility_score(user["id"])
        recalculate_match_score(user["id"])
        if is_mock:
            flash(f"Synced mock data for '{github_username}' successfully! Synced {synced_count} repositories.", "success")
        else:
            flash(f"Successfully synced {synced_count} public repositories from GitHub!", "success")
    else:
        if is_mock:
            flash(f"Mock GitHub sync completed. No new repositories found for '{github_username}'.", "info")
        else:
            flash("GitHub sync completed. No new repositories found.", "info")

    return redirect(url_for("dashboard"))



# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json()
    required = ["name", "email", "user_type", "field"]
    if not all(k in data for k in required):
        return jsonify({"error": f"Missing fields, need: {required}"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM user WHERE email = ?", (data["email"],)).fetchone()
    if existing:
        return jsonify({"error": "Email already registered"}), 409

    cur = db.execute(
        "INSERT INTO user (name, email, email_verified, user_type, field, github_username, created_at) "
        "VALUES (?, ?, 1, ?, ?, ?, ?)",
        (
            data["name"], data["email"], data["user_type"], data["field"],
            data.get("github_username"), datetime.utcnow().isoformat(),
        ),
    )
    db.commit()
    user = db.execute("SELECT * FROM user WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(user_public_dict(user)), 201


@app.route("/api/users/<int:user_id>/contributions", methods=["POST"])
def add_contribution(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if "title" not in data:
        return jsonify({"error": "title is required"}), 400

    cur = db.execute(
        "INSERT INTO contribution (user_id, title, description, proof_type, complexity_weight, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id, data["title"], data.get("description"), data.get("proof_type", "manual"),
            float(data.get("complexity_weight", 1.0)), datetime.utcnow().isoformat(),
        ),
    )
    db.commit()
    new_score = recalculate_credibility_score(user_id)
    return jsonify({"contribution_id": cur.lastrowid, "credibility_score": round(new_score, 2)}), 201


@app.route("/api/contributions/<int:contribution_id>/request-endorsement", methods=["POST"])
def request_endorsement_api(contribution_id):
    db = get_db()
    contribution = db.execute("SELECT * FROM contribution WHERE id = ?", (contribution_id,)).fetchone()
    if not contribution:
        return jsonify({"error": "Contribution not found"}), 404

    data = request.get_json()
    if "endorser_email" not in data:
        return jsonify({"error": "endorser_email is required"}), 400

    token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO endorsement (contribution_id, endorser_email, token, created_at) VALUES (?, ?, ?, ?)",
        (contribution_id, data["endorser_email"], token, datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({
        "confirm_link": url_for("endorse_confirm_page", token=token, _external=True),
        "token": token,
    }), 201


@app.route("/api/endorsements/<token>/confirm", methods=["POST"])
def confirm_endorsement_api(token):
    db = get_db()
    endorsement = db.execute("SELECT * FROM endorsement WHERE token = ?", (token,)).fetchone()
    if not endorsement:
        return jsonify({"error": "Invalid token"}), 404
    if endorsement["confirmed"]:
        return jsonify({"message": "Already confirmed"}), 200

    db.execute("UPDATE endorsement SET confirmed = 1 WHERE token = ?", (token,))
    db.commit()
    contribution = db.execute(
        "SELECT * FROM contribution WHERE id = ?", (endorsement["contribution_id"],)
    ).fetchone()
    new_score = recalculate_credibility_score(contribution["user_id"])
    return jsonify({"message": "Endorsement confirmed", "credibility_score": round(new_score, 2)}), 200


@app.route("/api/users/<int:rated_user_id>/ratings", methods=["POST"])
def add_rating(rated_user_id):
    db = get_db()
    rated_user = db.execute("SELECT * FROM user WHERE id = ?", (rated_user_id,)).fetchone()
    if not rated_user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    required = ["rater_id", "stars"]
    if not all(k in data for k in required):
        return jsonify({"error": f"Missing fields, need: {required}"}), 400

    stars = int(data["stars"])
    if not (1 <= stars <= 5):
        return jsonify({"error": "stars must be between 1 and 5"}), 400

    rater = db.execute("SELECT email FROM user WHERE id = ?", (data["rater_id"],)).fetchone()
    if not rater:
        return jsonify({"error": "Rater not found"}), 404

    shared_interaction = db.execute(
        """SELECT e.id FROM endorsement e
           JOIN contribution c ON e.contribution_id = c.id
           WHERE c.user_id = ? AND e.endorser_email = ? AND e.confirmed = 1 LIMIT 1""",
        (rated_user_id, rater["email"]),
    ).fetchone()
    if shared_interaction is None:
        return jsonify({"error": "Rating not allowed — no confirmed shared interaction yet."}), 403

    db.execute(
        "INSERT INTO rating (rater_id, rated_user_id, stars, tag, created_at) VALUES (?, ?, ?, ?, ?)",
        (data["rater_id"], rated_user_id, stars, data.get("tag"), datetime.utcnow().isoformat()),
    )
    db.commit()
    new_match_score = recalculate_match_score(rated_user_id)
    return jsonify({"match_score": round(new_match_score, 2)}), 201


@app.route("/api/users/<int:user_id>/profile", methods=["GET"])
def public_profile(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    contributions = db.execute(
        "SELECT * FROM contribution WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    contrib_list = []
    for c in contributions:
        confirmed_count = db.execute(
            "SELECT COUNT(*) FROM endorsement WHERE contribution_id = ? AND confirmed = 1", (c["id"],)
        ).fetchone()[0]
        contrib_list.append({
            "title": c["title"],
            "description": c["description"],
            "proof_type": c["proof_type"],
            "complexity_weight": c["complexity_weight"],
            "confirmed_endorsements": confirmed_count,
            "created_at": c["created_at"],
        })

    return jsonify({**user_public_dict(user), "contributions": contrib_list})


@app.route("/api/company/candidates", methods=["GET"])
def company_candidates():
    db = get_db()
    query = "SELECT * FROM user WHERE email_verified = 1"
    params = []
    field = request.args.get("field")
    if field:
        query += " AND field = ?"
        params.append(field)
    min_rating = request.args.get("min_rating", type=float)
    if min_rating is not None:
        query += " AND match_score >= ?"
        params.append(min_rating)
    sort_by = request.args.get("sort", "match_score")
    query += " ORDER BY credibility_score DESC" if sort_by == "credibility_score" else " ORDER BY match_score DESC"
    users = db.execute(query, params).fetchall()
    return jsonify([user_public_dict(u) for u in users])


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
