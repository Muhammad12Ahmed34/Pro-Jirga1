# frontend/preview_server.py
# Standalone preview — renders templates with fake data, zero backend dependency.
# Run this locally to see pages in the browser. Never merge this file into main.

from flask import Flask, render_template

app = Flask(__name__, template_folder="templates", static_folder="static")

FAKE_USER = {
    "name": "Ahmed",
    "phone": "+92-300-1234567",
    "github_username": "ahmeddev",
    "credibility_score": 78,
    "credibility_breakdown": "Frequency 30 × Complexity 2.1 × Endorsements 4",
}

FAKE_CONTRIBUTIONS = [
    {"title": "Refactored auth middleware", "description": "Cleaned up token handling",
     "source": "github", "timestamp": "2 days ago", "complexity_score": 3.2},
    {"title": "Tutored 9th class math session", "description": "Algebra revision, 1 hour",
     "source": "manual", "timestamp": "5 days ago", "complexity_score": 1.5},
]

FAKE_ENDORSEMENTS = [{"endorser_name": "Bilal", "timestamp": "1 day ago"}]

FAKE_RATINGS = [{"stars": 5, "tag": "reliable", "rater_name": "Bilal"}]
FAKE_MATCH_SCORE = 4.6

FAKE_CHALLENGE = {"title": "Build a REST endpoint", "prompt": "Create a /health route",
                   "time_limit_min": 120}

FAKE_CANDIDATES = [
    {"name": "Ahmed", "credibility_score": 78, "match_score": 4.6, "avg_stars": 4.6},
    {"name": "Sara", "credibility_score": 65, "match_score": 4.9, "avg_stars": 4.9},
]

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", user=FAKE_USER, contributions=FAKE_CONTRIBUTIONS)

@app.route("/add-contribution")
def add_contribution():
    return render_template("add_contribution.html")

@app.route("/u/<username>")
def profile(username):
    return render_template("profile.html", user=FAKE_USER, contributions=FAKE_CONTRIBUTIONS,
                            endorsements=FAKE_ENDORSEMENTS, ratings=FAKE_RATINGS,
                            match_score=FAKE_MATCH_SCORE, can_rate=True)

@app.route("/endorse-confirm")
def endorse_confirm():
    return render_template("endorse_confirm.html", user=FAKE_USER,
                            contribution=FAKE_CONTRIBUTIONS[0])

@app.route("/rate")
def rate_profile():
    return render_template("rate_profile.html", user=FAKE_USER)

@app.route("/challenge")
def challenge():
    return render_template("challenge.html", challenge=FAKE_CHALLENGE)

@app.route("/company-view")
def company_view():
    return render_template("company_view.html", candidates=FAKE_CANDIDATES)

if __name__ == "__main__":
    app.run(debug=True, port=5050)