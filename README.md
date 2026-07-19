
# Pro-Jirga 🚀

> A Flask-powered platform for showcasing skills, tracking contributions, and building professional credibility.

## ✨ Overview

Pro-Jirga enables users to create profiles, participate in challenges, record contributions, receive endorsements, and connect with organizations through a clean web interface.

## 🛠 Tech Stack

- **Backend:** Python, Flask
- **Frontend:** HTML5, CSS3, JavaScript
- **Database:** SQLite
- **Templating:** Jinja2

## 📂 Project Structure

```text
Pro-Jirga1/
├── Backend/
│   ├── app.py
│   ├── requirements.txt
│   └── skillledger.db
├── Frontend/
│   ├── templates/
│   └── statics/
└── README.md
```

## 🌟 Features

- User registration & authentication
- Personal dashboard
- Contribution tracking
- Skill endorsements
- Company view
- Challenges
- Email verification
- Responsive interface

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/Muhammad12Ahmed34/Pro-Jirga1.git
cd Pro-Jirga1
python -m venv .venv
```

Activate the virtual environment, then:

```bash
pip install -r Backend/requirements.txt
cd Backend
python app.py
```

Open the local URL shown in the terminal.

## 🌍 Deployment

This application is built with Flask and includes a Vercel deployment config in `vercel.json`.

- Local deployment:
  1. `python -m venv .venv`
  2. Activate the venv
  3. `pip install -r Backend/requirements.txt`
  4. `cd Backend`
  5. `python app.py`

- Vercel deployment:
  1. Go to vercel.com and sign in.
  2. Import the GitHub repository using the Vercel dashboard.
  3. Use the default settings and ensure the root path is the repository root.
  4. Vercel will detect `Backend/app.py` and the `vercel.json` configuration automatically.

If you want to deploy with environment variables, set `SECRET_KEY` and `DATABASE_PATH` in the Vercel project settings.

## 🗺 Roadmap

- OAuth login
- Notifications
- Search & filtering
- REST API
- Admin dashboard
- Docker support

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome. Please fork the repository and open a pull request.

## 📄 License

MIT License.

## 👨‍💻 Founders

**Muhammad Ahmed**

- Co-Founer & CEO
- Electrical Engineering Student @ NED
- Full-Stack Web Developer
- Robotics & AI Enthusiast

**Hafiz Muhammad Shafi**

- Co-founder & CTO
- Electrical Engineering Student @ NED
- Robotics & AI Enthusiast

**Azmeer Tanveer**

- Co-Founer & C0O
- CSIT Student @ NED
- Full-Stack Web Developer

If you found this project helpful, consider giving it a ⭐ on GitHub!
