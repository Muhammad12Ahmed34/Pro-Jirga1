import sqlite3
import os
import uuid
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "skillledger.db")

def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Drop existing tables to start clean
    cursor.executescript("""
    DROP TABLE IF EXISTS user;
    DROP TABLE IF EXISTS contribution;
    DROP TABLE IF EXISTS endorsement;
    DROP TABLE IF EXISTS rating;
    DROP TABLE IF EXISTS verification_code;
    """)

    # Recreate tables
    cursor.executescript("""
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

    # Add developers
    developers = [
        # name, email, user_type, field, github_username
        ("Sarah Jenkins", "sarah@pro-jirga.local", "professional", "Frontend Engineering", "sarahj"),
        ("Alex Rivera", "alex@pro-jirga.local", "professional", "Backend Systems", "alexr"),
        ("Emily Chen", "emily@pro-jirga.local", "gig_worker", "Data Science", "emilyc"),
        ("David K.", "david@pro-jirga.local", "student", "Mobile Development", None),
    ]

    now = datetime.utcnow()
    user_ids = {}
    for name, email, user_type, field, github in developers:
        created_at = (now - timedelta(days=30)).isoformat()
        cursor.execute(
            "INSERT INTO user (name, email, email_verified, user_type, field, github_username, created_at) VALUES (?, ?, 1, ?, ?, ?, ?)",
            (name, email, user_type, field, github, created_at)
        )
        user_ids[email] = cursor.lastrowid

    # Add contributions
    contributions = [
        # email, title, description, proof_type, complexity_weight, days_ago
        ("sarah@pro-jirga.local", "Built high-performance design system in CSS", "Created a customizable theme engine using CSS variables and utility classes, cutting rendering overhead by 40%.", "manual", 1.4, 25),
        ("sarah@pro-jirga.local", "sarahj/react-dashboard-component", "Open-source analytics dashboard widget library with 200+ stars on GitHub.", "github", 1.8, 15),
        ("alex@pro-jirga.local", "Designed microservices checkout orchestrator", "Implemented a distributed transaction controller utilizing the Saga pattern to handle checkouts safely.", "manual", 1.9, 20),
        ("alex@pro-jirga.local", "alexr/go-redis-queue", "Fast and lightweight Redis-backed job queue library written in Go.", "github", 1.5, 10),
        ("emily@pro-jirga.local", "Trained custom customer churn prediction model", "Built an XGBoost model predicting user churn with 94% AUC, deployed via FastAPI on AWS ECS.", "manual", 1.7, 18),
        ("david@pro-jirga.local", "Shipped SwiftUI expense tracker app", "A personal finance app featuring dynamic charts, biometric locking, and SwiftData storage.", "manual", 1.3, 5),
    ]

    contrib_ids = []
    for email, title, desc, proof_type, weight, days_ago in contributions:
        created_at = (now - timedelta(days=days_ago)).isoformat()
        cursor.execute(
            "INSERT INTO contribution (user_id, title, description, proof_type, complexity_weight, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_ids[email], title, desc, proof_type, weight, created_at)
        )
        contrib_ids.append((email, title, cursor.lastrowid, weight))

    # Add endorsements
    endorsements = [
        # (contribution owner, contribution title), endorser_email
        (("sarah@pro-jirga.local", "Built high-performance design system in CSS"), "alex@pro-jirga.local"),
        (("sarah@pro-jirga.local", "sarahj/react-dashboard-component"), "emily@pro-jirga.local"),
        (("alex@pro-jirga.local", "Designed microservices checkout orchestrator"), "sarah@pro-jirga.local"),
        (("alex@pro-jirga.local", "alexr/go-redis-queue"), "david@pro-jirga.local"),
        (("david@pro-jirga.local", "Shipped SwiftUI expense tracker app"), "sarah@pro-jirga.local"),
    ]

    for (owner_email, title), endorser_email in endorsements:
        # Find contribution id
        contrib_id = next(cid for email, t, cid, w in contrib_ids if email == owner_email and t == title)
        token = str(uuid.uuid4())
        created_at = (now - timedelta(days=2)).isoformat()
        cursor.execute(
            "INSERT INTO endorsement (contribution_id, endorser_email, token, confirmed, created_at) VALUES (?, ?, ?, 1, ?)",
            (contrib_id, endorser_email, token, created_at)
        )

    # Add ratings (must have a confirmed endorsement)
    ratings = [
        # rater_email, rated_email, stars, tag
        ("alex@pro-jirga.local", "sarah@pro-jirga.local", 5, "design system wizard"),
        ("emily@pro-jirga.local", "sarah@pro-jirga.local", 5, "excellent UI builder"),
        ("sarah@pro-jirga.local", "alex@pro-jirga.local", 5, "distributed systems expert"),
        ("david@pro-jirga.local", "alex@pro-jirga.local", 4, "clean APIs"),
        ("sarah@pro-jirga.local", "david@pro-jirga.local", 5, "great SwiftUI skills"),
    ]

    for rater_email, rated_email, stars, tag in ratings:
        created_at = (now - timedelta(days=1)).isoformat()
        cursor.execute(
            "INSERT INTO rating (rater_id, rated_user_id, stars, tag, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_ids[rater_email], user_ids[rated_email], stars, tag, created_at)
        )

    conn.commit()

    # Recalculate scores using the logic from app.py
    for email, uid in user_ids.items():
        # Recalculate credibility
        contribs = cursor.execute("SELECT id, complexity_weight FROM contribution WHERE user_id = ?", (uid,)).fetchall()
        credibility = 0.0
        for c in contribs:
            confirmed_count = cursor.execute(
                "SELECT COUNT(*) FROM endorsement WHERE contribution_id = ? AND confirmed = 1",
                (c["id"],)
            ).fetchone()[0]
            credibility += c["complexity_weight"] * (1 + 0.5 * confirmed_count)
        cursor.execute("UPDATE user SET credibility_score = ? WHERE id = ?", (credibility, uid))

    conn.commit()

    for email, uid in user_ids.items():
        # Recalculate match
        ratings = cursor.execute("SELECT rater_id, stars FROM rating WHERE rated_user_id = ?", (uid,)).fetchall()
        if not ratings:
            match_score = 0.0
        else:
            weighted_sum = 0.0
            weight_total = 0.0
            for r in ratings:
                rater = cursor.execute("SELECT credibility_score FROM user WHERE id = ?", (r["rater_id"],)).fetchone()
                weight = max(rater["credibility_score"], 0.1)
                weighted_sum += r["stars"] * weight
                weight_total += weight
            match_score = weighted_sum / weight_total if weight_total > 0 else 0.0
        cursor.execute("UPDATE user SET match_score = ? WHERE id = ?", (match_score, uid))

    conn.commit()
    conn.close()
    print("Database successfully seeded!")

if __name__ == "__main__":
    seed()
