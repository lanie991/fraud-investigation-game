"""
FORENSIC ELIMINATION
A standalone Kahoot-style, single-elimination fraud trivia game that
runs alongside the existing "Who Stole the Money?" investigation game.

Each player joins with a game PIN, then works through their own set of
three rounds (Easy, Intermediate, Hard) at their own pace. A wrong
answer eliminates them (when elimination is enabled).

Questions live in QUESTION_BANK, a pool per round -- add more entries to
any round's list to grow the pool further. One question per round is
drawn at random each time a game starts or is reset.
"""

from functools import wraps
from importlib import import_module
import io
import json
import os
import random
import sqlite3
import string

flask = import_module("flask")
qrcode = import_module("qrcode")

Blueprint = flask.Blueprint
render_template = flask.render_template
redirect = flask.redirect
request = flask.request
jsonify = flask.jsonify
url_for = flask.url_for
send_file = flask.send_file
session = flask.session

elimination_bp = Blueprint(
    "elimination",
    __name__
)

DATABASE = "elimination_game.db"

DEFAULT_TIMER_SECONDS = 20

# The host password gates /host, /settings, and every host-control route
# (start/kick/reset/settings). Set FE_HOST_PASSWORD in the environment to
# override the default before deploying somewhere other players can reach.
HOST_PASSWORD = os.environ.get("FE_HOST_PASSWORD", "forensics2024")

AVATAR_IMAGES = {
    "detective_black": "detective.png",
    "investigator_black": "investigator.png",
    "analyst_black": "analyst.png",
    "researcher_white": "researcher.png",
    "surveillance_black": "surveillance.png",
    "forensics_black": "forensics.png",
    "hacker_white": "hacker.png",
    "moneymover_black": "money_movers.png",
    "k9_unit": "k9.png",
    "field_agent_white": "field_agents.png"
}


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def generate_pin():
    letters = "".join(random.choice(string.ascii_uppercase) for _ in range(2))
    digits = "".join(random.choice(string.digits) for _ in range(2))
    return letters + digits


def initialize_database():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS fe_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            pin TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'lobby',
            timer_seconds INTEGER NOT NULL DEFAULT 20,
            elimination_enabled INTEGER NOT NULL DEFAULT 1,
            lifelines_enabled INTEGER NOT NULL DEFAULT 1,
            active_questions TEXT
        )
    """)

    existing_config_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(fe_config)")
    }
    if "active_questions" not in existing_config_columns:
        connection.execute(
            "ALTER TABLE fe_config ADD COLUMN active_questions TEXT"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS fe_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            avatar TEXT DEFAULT 'detective_black',
            status TEXT DEFAULT 'in',
            phase TEXT DEFAULT 'lobby',
            question_index INTEGER DEFAULT 0,
            answered_current INTEGER DEFAULT 0,
            last_correct INTEGER,
            phase_started_at TEXT,
            fifty_fifty_used INTEGER DEFAULT 0,
            lifeline_removed TEXT,
            skip_used INTEGER DEFAULT 0,
            ask_team_used INTEGER DEFAULT 0,
            option_order TEXT,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Older databases created before the three-lifeline system: add the
    # new columns and carry over the original single lifeline flag.
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(fe_players)")
    }

    if "fifty_fifty_used" not in existing_columns:
        if "lifeline_used" in existing_columns:
            connection.execute(
                "ALTER TABLE fe_players ADD COLUMN fifty_fifty_used INTEGER DEFAULT 0"
            )
            connection.execute(
                "UPDATE fe_players SET fifty_fifty_used = lifeline_used"
            )
        else:
            connection.execute(
                "ALTER TABLE fe_players ADD COLUMN fifty_fifty_used INTEGER DEFAULT 0"
            )

    for column in ("skip_used", "ask_team_used"):
        if column not in existing_columns:
            connection.execute(
                f"ALTER TABLE fe_players ADD COLUMN {column} INTEGER DEFAULT 0"
            )

    if "option_order" not in existing_columns:
        connection.execute(
            "ALTER TABLE fe_players ADD COLUMN option_order TEXT"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS fe_answer_tally (
            round_number INTEGER NOT NULL,
            option TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (round_number, option)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS fe_answer_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            answer TEXT,
            correct INTEGER NOT NULL
        )
    """)

    existing_config = connection.execute(
        "SELECT COUNT(*) AS count FROM fe_config"
    ).fetchone()

    if existing_config["count"] == 0:
        connection.execute(
            """
            INSERT INTO fe_config (id, pin, status, timer_seconds,
                                    elimination_enabled, lifelines_enabled,
                                    active_questions)
            VALUES (1, ?, 'lobby', ?, 1, 1, ?)
            """,
            (generate_pin(), DEFAULT_TIMER_SECONDS, json.dumps(pick_active_questions()))
        )
    else:
        connection.execute(
            """
            UPDATE fe_config SET active_questions = ?
            WHERE id = 1 AND (active_questions IS NULL OR active_questions = '')
            """,
            (json.dumps(pick_active_questions()),)
        )

    connection.commit()
    connection.close()


# =========================================================
# QUESTION BANK
#
# Three rounds are played in order: Round 1 (Easy) -> Round 2
# (Intermediate) -> Round 3 (Hard). Every question in each round is
# played, in the order listed (see pick_active_questions).
# =========================================================

QUESTION_BANK = {
    1: [
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "Which of the following is a common fraud red flag",
            "options": {
                "A": "Strong internal controls",
                "B": "Unexpected lifestyle changes",
                "C": "Regular vacations",
                "D": "Employee training"
            },
            "correct": "B",
            "explanation": "Unexpected lifestyle changes can be a red flag for potential fraud."
        },
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "What is phishing?",
            "options": {
                "A": "A fishing business scam",
                "B": "Theft of physical assets",
                "C": "A fraudulent attempt to obtain sensitive information",
                "D": "A type of audit"
            },
            "correct": "C",
            "explanation": "Phishing is a fraudulent attempt to obtain sensitive information by disguising as a trustworthy entity in electronic communications."
        },
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "Identity theft involves:",
            "options": {
                "A": "Creating duplicate invoices",
                "B": "Using another person's personal information without permission",
                "C": "Hacking a website",
                "D": "Preparing an incorrect bank reconciliation"
            },
            "correct": "B",
            "explanation": "Identity theft involves using another person's personal information without their permission."
        },
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "Embezzlement occurs when:",
            "options": {
                "A": "Someone steals funds entrusted to them",
                "B": "A company overpays tax",
                "C": "An employee works overtime",
                "D": "An auditor makes an error"
            },
            "correct": "A",
            "explanation": "Embezzlement occurs when someone steals funds entrusted to them."
        },
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "Many large fraud continue for years because:",
            "options": {
                "A": "Stakeholders consistently challenge management",
                "B": "Trusted individuals exploit their credibility",
                "C": "Regulators respond immediately",
                "D": "Controls operate perfectly"
            },
            "correct": "B",
            "explanation": "Many large fraud schemes continue for years because trusted individuals exploit their credibility to gain access to resources and manipulate systems without detection."
        },
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "Which company claimed its technology could perform hunderds of blood tests from a tiny blood sample?",
            "options": {
                "A": "Medtronic",
                "B": "Theranos",
                "C": "Pfizer",
                "D": "Roche"
            },
            "correct": "B",
            "explanation": "Theranos claimed its technology could perform hundreds of blood tests from a tiny blood sample, but the claims were later found to be false."
        },
        {
            "round_number": 1,
            "difficulty": "EASY",
            "text": "What is the defining feature of a Ponzi scheme?",
            "options": {
                "A": "Hidden taxes increase profits",
                "B": "Fake invoices are submitted to customers",
                "C": "Money from new investors is used to pay earlier investors",
                "D": "Company assets are phyically stolen"
            },
            "correct": "C",
            "explanation": "The defining feature of a Ponzi scheme is that money from new investors is used to pay returns to earlier investors, creating the illusion of profitability."
        }
    ],
    2: [
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "Which forensic principle is most important when handling original evidence?",
            "options": {
                "A": "Modify the evidence before analysis",
                "B": "Preserve the integrity of the orignal evidence",
                "C": "Analyze the original device whenever possible",
                "D": "Delete irrelvant files before acquistion"
            },
            "correct": "B",
            "explanation": "Preserving the integrity of original evidence is crucial in digital forensics to ensure its admissibility in court and to maintain the trustworthiness of the investigation."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "What does MD5 hashing primarily provide in digital forensics?",
            "options": {
                "A": "Encryption",
                "B": "Authentication of a user's identity",
                "C": "A value used to verify data integrity",
                "D": "Password recovery"
            },
            "correct": "C",
            "explanation": "MD5 hashing provides a unique digital fingerprint for data, allowing investigators to verify that the data has not been altered."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "Which forensic tool is commonly associated with forensic disk imaging and evidence acquisition?",
            "options": {
                "A": "Encase Forensic",
                "B": "FTK Imager",
                "C": "Autopsy",
                "D": "Cellebrite Physical Analyzer"
            },
            "correct": "B",
            "explanation": "FTK Imager is a widely used tool for creating bit-for-bit copies of storage devices for digital forensics analysis."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "Which European payments company collapsed after €1.9 billion was reported missing?",
            "options": {
                "A": "Coinbase",
                "B": "Wirecard",
                "C": "Klarna",
                "D": "Paypal"
            },
            "correct": "B",
            "explanation": "Wirecard was a European payments company that collapsed after reporting a loss of €1.9 billion."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "What made Madoff's reported investment returns suspicious?",
            "options": {
                "A": "They were always negative",
                "B": "They were unusually consistent",
                "C": "They followed the market exactly",
                "D": "They were independantly verified by several firms"
            },
            "correct": "B",
            "explanation": "Madoff's reported returns were suspicious becasue they were remarkably consistent and showed unusually little volatility, even during periods of significant market fluctuations"
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "Approximately how much was involved in the WorldCom accounting fraud?",
            "options": {
                "A": "$500 million",
                "B": "$1 billion",
                "C": "Over $10 billion",
                "D": "$100 billion"
            },
            "correct": "C",
            "explanation": "Approximately $11 million was involved, making it one of the largest accounting frauds in U.S. history."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "The 2002 Movie Catch me if you can is based on the real life story of what infamous fraudster?",
            "options": {
                "A": "Barry Allen",
                "B": "Frank Abagnale Jr.",
                "C": "Bernie Madoff",
                "D": "Barry Minkow"
            },
            "correct": "B",
            "explanation": "The film is based on Frank Abagnale Jr., who became known for impersonation and check fraud."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "Which of the following is NOT a common fraud scheme prepetrated by hedge fund managers?",
            "options": {
                "A": "Late trading",
                "B": "Insider trading",
                "C": "Overvaluation of portfolios",
                "D": "Bid rigging"
            },
            "correct": "D",
            "explanation": "Bid rigging is not typically associated with hedge fund fraud, as it involes maniuplating competitive bidding processes rather than misusing investor funds or assets."
        }
    ],
    3: [
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "What verification failure was central to the Wirecard scandal involving bilions in reported cash?",
            "options": {
                "A": "Failure to indenpendently verify reported funds",
                "B": "Failure to conduct employee background checks",
                "C": "Failure to encrypt financial records",
                "D": "Failure to separate payroll duties"
            },
            "correct": "A",
            "explanation": "The reported funds were not independently verified, allowing the company to claim billions in cash that did not actually exist."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "Frank Abagnale Jr. would frequently use aliases to commit check fraud and impersonate professionals such as pilots. One alias he used was Barry Allen, also known as?",
            "options": {
                "A": "Famous Baseball Player",
                "B": "The Flash",
                "C": "Actor",
                "D": "Inventor (Toaster)"
            },
            "correct": "B",
            "explanation": "The alias 'Barry Allen'was a reference to The Flash, the fictional superhero whose civilian identity is Barry Allen."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "What act Gunvor S.A. convicted on?",
            "options": {
                "A": "Foreign Corrupt Practices Act",
                "B": "Foreign Extortion Prevention Act",
                "C": "Travel Act",
                "D": "Racketeer Influenced and Corrupt Organizations Act"
            },
            "correct": "A",
            "explanation": "Gunvor S.A. was convicted under the <b> Foreign Corrupt Practices Act (FCPA) </b> for bribing foregin officals to secure business."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "'Which European bank helped Manuel Chang facilitate the $2 billion scheme?",
            "options": {
                "A": "Deutsche Bank",
                "B": "Credit Sussie",
                "C": "UBS",
                "D": "Barclays"
            },
            "correct": "B",
            "explanation": "Credit Suisse helped facilitate the transactions used in the $2 billion scheme involving hidden debts and corrupt payments."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "What cryptocurrency did Shane Hampton and his co-conspirators manipulate?",
            "options": {
                "A": "Ethereum",
                "B": "HYDRO",
                "C": "Solana",
                "D": "Litecoin"
            },
            "correct": "B",
            "explanation": "The scheme invovled manipulating the price and trading activity of Hydro (HYDRO) crytocurrency for fraudulent profit."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "Malware copies bank credentials and transmits them only after a specific condition occurs. Which pairing best describes it?",
            "options": {
                "A": "Keylogger + logic bomb",
                "B": "Worm + ransomware",
                "C": "Trojan + adware",
                "D": "Botnet + spoofing"
            },
            "correct": "A",
            "explanation": "A keylogger captures sensitive credentials, while a logic bomb triggers the transmission when a specific condition is met."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "What type of fraud did Hegestratos attempt to commit",
            "options": {
                "A": "Insurance fraud",
                "B": "Tax fraud",
                "C": "Securities fraud",
                "D": "Identity fraud"
            },
            "correct": "A",
            "explanation": "Hegestratos attempted insurance fraud by taking out a loan against his cargo and planning to sink the ship to avoid repayment."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "Barry Minkow is a famous fraudster known for his ponzi scheme which used his cleaning and restoration comany ________ to attract investors.",
            "options": {
                "A": "ZZZ Cleaning",
                "B": "ABCD Best",
                "C": "ZZZZ Best",
                "D": "A2Z Cleaning and Restoration"
            },
            "correct": "C",
            "explanation": "Minkow used ZZZZ Best to create the appearance of a successful business and attract investors through fraudulent financial claims"
        }
    ]
}

TOTAL_ROUNDS = sum(len(QUESTION_BANK[r]) for r in QUESTION_BANK)


def pick_active_questions():
    """Every question, round by round, in the order listed."""
    return [q for round_number in sorted(QUESTION_BANK) for q in QUESTION_BANK[round_number]]


def get_active_rounds(config):
    """The three questions in play for the current game (same for every
    player, drawn once when the game was created or last reset)."""
    raw = config["active_questions"] if "active_questions" in config.keys() else None
    if raw:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            pass
    return pick_active_questions()


def build_round_tracker(active_rounds, question_index):
    """One entry per round for the header tracker, each with one dot per
    question. A dot lights up once that question has been answered; the
    round circle fills in only when every question in it is done."""
    tracker = []
    for index, question in enumerate(active_rounds):
        if not tracker or tracker[-1]["round_number"] != question["round_number"]:
            tracker.append({
                "round_number": question["round_number"],
                "difficulty": question["difficulty"],
                "dots": []
            })
        if index < question_index:
            dot = "done"
        elif index == question_index:
            dot = "current"
        else:
            dot = ""
        tracker[-1]["dots"].append(dot)

    for entry in tracker:
        if all(dot == "done" for dot in entry["dots"]):
            entry["state"] = "done"
        elif "current" in entry["dots"] or "done" in entry["dots"]:
            entry["state"] = "current"
        else:
            entry["state"] = ""
    return tracker


def starts_new_round(active_rounds, question_index):
    """True when question_index is the first question of a later round."""
    return (0 < question_index < len(active_rounds)
            and active_rounds[question_index]["round_number"]
            != active_rounds[question_index - 1]["round_number"])


# =========================================================
# HELPERS
# =========================================================

def get_config(connection):
    return connection.execute(
        "SELECT * FROM fe_config WHERE id = 1"
    ).fetchone()


def get_player(connection, name):
    return connection.execute(
        "SELECT * FROM fe_players WHERE name = ?", (name,)
    ).fetchone()


def players_remaining_count(connection):
    return connection.execute(
        "SELECT COUNT(*) AS count FROM fe_players WHERE status = 'in'"
    ).fetchone()["count"]


def grade_regular_answer(connection, player, config, answer):
    round_data = get_active_rounds(config)[player["question_index"]]
    correct = 1 if answer == round_data["correct"] else 0

    new_status = player["status"]
    if not correct and config["elimination_enabled"]:
        new_status = "eliminated"

    connection.execute(
        """
        UPDATE fe_players
        SET status = ?, answered_current = 1,
            last_correct = ?
        WHERE id = ?
        """,
        (new_status, correct, player["id"])
    )

    if answer in round_data["options"]:
        connection.execute(
            """
            INSERT INTO fe_answer_tally (round_number, option, count)
            VALUES (?, ?, 1)
            ON CONFLICT(round_number, option)
            DO UPDATE SET count = count + 1
            """,
            (player["question_index"], answer)
        )

    connection.execute(
        """
        INSERT INTO fe_answer_history (player_id, round_number, answer, correct)
        VALUES (?, ?, ?, ?)
        """,
        (player["id"], player["question_index"], answer, correct)
    )

    connection.commit()


def host_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("fe_is_host"):
            return redirect(url_for("elimination.host_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def is_declared_winner(connection, player):
    """Best-effort winner check under independent, per-player pacing.

    Since every player advances on their own clock instead of a single
    host-driven round, we can only call someone the last investigator
    standing once every other player has either been eliminated or has
    also finished the game. There's no score to break ties with -- if
    more than one player survives to the end, they're declared joint
    winners.
    """
    if player["status"] != "in" or player["phase"] != "finished":
        return False

    others = connection.execute(
        "SELECT * FROM fe_players WHERE id != ?", (player["id"],)
    ).fetchall()

    for other in others:
        still_playing = other["status"] == "in" and other["phase"] != "finished"
        if still_playing:
            return False

    return True


# =========================================================
# HOME / RULES / CASE FILES
# =========================================================

@elimination_bp.route("/")
def home():
    return render_template("fe_home.html", active_nav="home")


@elimination_bp.route("/rules")
def rules():
    return render_template("fe_rules.html", active_nav="rules")


@elimination_bp.route("/case-files")
def case_files():
    preview_rounds = [QUESTION_BANK[round_number][0] for round_number in sorted(QUESTION_BANK)]
    return render_template(
        "fe_case_files.html",
        rounds=preview_rounds,
        active_nav="case_files"
    )


@elimination_bp.route("/settings")
@host_required
def settings():
    return redirect(url_for("elimination.host"))


# =========================================================
# HOST
# =========================================================

@elimination_bp.route("/host-login", methods=["GET", "POST"])
def host_login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == HOST_PASSWORD:
            session["fe_is_host"] = True
            next_url = request.form.get("next", "")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("elimination.host")
            return redirect(next_url)
        error = "Incorrect host password."

    return render_template(
        "fe_host_login.html",
        error=error,
        next=request.args.get("next", ""),
        active_nav="settings"
    )


@elimination_bp.route("/host-logout", methods=["POST"])
def host_logout():
    session.pop("fe_is_host", None)
    return redirect(url_for("elimination.home"))


@elimination_bp.route("/host")
@host_required
def host():
    connection = get_db()
    config = get_config(connection)
    players = connection.execute(
        "SELECT * FROM fe_players ORDER BY joined_at"
    ).fetchall()
    connection.close()

    return render_template(
        "fe_host.html",
        config=config,
        players=players,
        total_rounds=TOTAL_ROUNDS,
        avatar_images=AVATAR_IMAGES,
        active_nav="settings"
    )


@elimination_bp.route("/qr.png")
def qr_png():
    connection = get_db()
    config = get_config(connection)
    connection.close()

    join_url = url_for("elimination.join", pin=config["pin"], _external=True)

    img = qrcode.make(join_url, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(buffer, mimetype="image/png")


@elimination_bp.route("/host/settings", methods=["POST"])
@host_required
def host_settings():
    connection = get_db()
    config = get_config(connection)

    if config["status"] == "lobby":
        try:
            timer_seconds = max(5, int(request.form.get("timer_seconds", DEFAULT_TIMER_SECONDS)))
        except ValueError:
            timer_seconds = DEFAULT_TIMER_SECONDS

        elimination_enabled = 1 if request.form.get("elimination_enabled") == "on" else 0
        lifelines_enabled = 1 if request.form.get("lifelines_enabled") == "on" else 0

        connection.execute(
            """
            UPDATE fe_config
            SET timer_seconds = ?, elimination_enabled = ?, lifelines_enabled = ?
            WHERE id = 1
            """,
            (timer_seconds, elimination_enabled, lifelines_enabled)
        )
        connection.commit()

    connection.close()
    return redirect(url_for("elimination.host"))


@elimination_bp.route("/host/start", methods=["POST"])
@host_required
def host_start():
    connection = get_db()
    config = get_config(connection)

    if config["status"] == "lobby":
        connection.execute(
            "UPDATE fe_config SET status = 'active' WHERE id = 1"
        )
        connection.execute(
            """
            UPDATE fe_players
            SET phase = 'question', question_index = 0,
                answered_current = 0, phase_started_at = NULL
            WHERE phase = 'lobby'
            """
        )
        connection.commit()

    connection.close()
    return redirect(url_for("elimination.host"))


@elimination_bp.route("/host/kick/<name>", methods=["POST"])
@host_required
def host_kick(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is not None:
        connection.execute("DELETE FROM fe_answer_history WHERE player_id = ?", (player["id"],))
        connection.execute("DELETE FROM fe_players WHERE id = ?", (player["id"],))
        connection.commit()

    connection.close()
    return redirect(url_for("elimination.host"))


@elimination_bp.route("/host/reset", methods=["POST"])
@host_required
def host_reset():
    connection = get_db()
    connection.execute("DELETE FROM fe_players")
    connection.execute("DELETE FROM fe_answer_tally")
    connection.execute("DELETE FROM fe_answer_history")
    connection.execute(
        "UPDATE fe_config SET pin = ?, status = 'lobby', active_questions = ? WHERE id = 1",
        (generate_pin(), json.dumps(pick_active_questions()))
    )
    connection.commit()
    connection.close()
    return redirect(url_for("elimination.host"))


# =========================================================
# JOIN / WAITING
# =========================================================

@elimination_bp.route("/join", methods=["GET", "POST"])
def join():
    connection = get_db()
    config = get_config(connection)
    error = None

    if request.method == "POST":
        name = request.form.get("player_name", "").strip()
        pin = request.form.get("game_pin", "").strip().upper()
        avatar = request.form.get("avatar", "detective_black").strip()

        if not name:
            error = "Enter your investigator name."
        elif pin != config["pin"]:
            error = "That game PIN doesn't match. Ask the host for the current PIN."
        elif config["status"] != "lobby":
            error = "This game has already started. Ask the host to reset for a new game."
        elif get_player(connection, name) is not None:
            error = "That name is already taken this game. Try another."
        else:
            connection.execute(
                """
                INSERT INTO fe_players (name, avatar, status, phase)
                VALUES (?, ?, 'in', 'lobby')
                """,
                (name, avatar)
            )
            connection.commit()
            connection.close()
            return redirect(url_for("elimination.waiting", name=name))

    connection.close()
    return render_template(
        "fe_join.html",
        error=error,
        avatar_images=AVATAR_IMAGES,
        active_nav="play",
        prefill_pin=request.args.get("pin", "").strip().upper()
    )


@elimination_bp.route("/waiting/<name>")
def waiting(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    config = get_config(connection)
    connection.close()

    if config["status"] == "active" and player["phase"] == "question":
        return redirect(url_for("elimination.play", name=name))

    return render_template(
        "fe_waiting.html",
        name=name,
        avatar=player["avatar"],
        avatar_images=AVATAR_IMAGES,
        active_nav="play"
    )


@elimination_bp.route("/status/<name>")
def player_status(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return jsonify({"phase": "unknown"})

    config = get_config(connection)
    connection.close()

    return jsonify({
        "game_status": config["status"],
        "phase": player["phase"],
        "status": player["status"]
    })


@elimination_bp.route("/players-status")
def players_status_json():
    connection = get_db()
    players = connection.execute(
        "SELECT name, avatar, status FROM fe_players ORDER BY joined_at"
    ).fetchall()
    connection.close()

    return jsonify({
        "players": [dict(p) for p in players],
        "remaining": sum(1 for p in players if p["status"] == "in")
    })


# =========================================================
# PLAYING A ROUND
# =========================================================

@elimination_bp.route("/play/<name>", methods=["GET", "POST"])
def play(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    config = get_config(connection)

    if player["status"] == "eliminated":
        connection.close()
        return redirect(url_for("elimination.eliminated", name=name))

    if player["phase"] == "finished":
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    if player["phase"] != "question":
        connection.close()
        return redirect(url_for("elimination.waiting", name=name))

    if player["question_index"] >= TOTAL_ROUNDS:
        connection.execute(
            "UPDATE fe_players SET phase = 'finished' WHERE id = ?",
            (player["id"],)
        )
        connection.commit()
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    active_rounds = get_active_rounds(config)

    if request.method == "POST":
        if not player["answered_current"]:
            answer = request.form.get("answer")
            grade_regular_answer(connection, player, config, answer)
        connection.close()
        return redirect(url_for("elimination.feedback", name=name))

    if player["answered_current"]:
        connection.close()
        return redirect(url_for("elimination.feedback", name=name))

    round_data = active_rounds[player["question_index"]]

    if not player["phase_started_at"]:
        shuffled_keys = list(round_data["options"].keys())
        random.shuffle(shuffled_keys)
        connection.execute(
            """
            UPDATE fe_players
            SET phase_started_at = datetime('now'), option_order = ?
            WHERE id = ?
            """,
            (",".join(shuffled_keys), player["id"])
        )
        connection.commit()
        player = get_player(connection, player["name"])

    elapsed = connection.execute(
        "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
        (player["phase_started_at"],)
    ).fetchone()["seconds"]

    if elapsed >= config["timer_seconds"]:
        grade_regular_answer(connection, player, config, None)
        connection.close()
        return redirect(url_for("elimination.feedback", name=name))

    removed_options = set()
    if player["lifeline_removed"]:
        removed_options = set(player["lifeline_removed"].split(","))

    display_letters = "ABCDEFGH"
    order = (player["option_order"] or ",".join(round_data["options"].keys())).split(",")
    ordered_options = [
        (display_letters[i], key, round_data["options"][key])
        for i, key in enumerate(order)
        if key in round_data["options"]
    ]

    players = connection.execute(
        "SELECT name, avatar, status FROM fe_players ORDER BY joined_at"
    ).fetchall()
    remaining = sum(1 for p in players if p["status"] == "in")

    connection.close()

    return render_template(
        "fe_question.html",
        name=name,
        player=player,
        question=round_data,
        ordered_options=ordered_options,
        rounds=active_rounds,
        tracker=build_round_tracker(active_rounds, player["question_index"]),
        current_round=round_data["round_number"],
        timer_seconds=config["timer_seconds"],
        remaining_seconds=max(0, int(config["timer_seconds"] - elapsed)),
        lifelines_enabled=config["lifelines_enabled"],
        removed_options=removed_options,
        players=players,
        players_remaining=remaining,
        avatar_images=AVATAR_IMAGES,
        active_nav="play"
    )


@elimination_bp.route("/lifeline/fifty-fifty/<name>", methods=["POST"])
def use_fifty_fifty(name):
    connection = get_db()
    player = get_player(connection, name)
    config = get_config(connection)

    if (player is not None and config["lifelines_enabled"]
            and not player["fifty_fifty_used"] and player["phase"] == "question"
            and not player["answered_current"]
            and player["question_index"] < TOTAL_ROUNDS):

        round_data = get_active_rounds(config)[player["question_index"]]
        wrong_options = [key for key in round_data["options"] if key != round_data["correct"]]
        random.shuffle(wrong_options)
        removed = ",".join(wrong_options[:2])

        connection.execute(
            """
            UPDATE fe_players
            SET fifty_fifty_used = 1, lifeline_removed = ?
            WHERE id = ?
            """,
            (removed, player["id"])
        )
        connection.commit()

    connection.close()
    return redirect(url_for("elimination.play", name=name))


@elimination_bp.route("/lifeline/skip/<name>", methods=["POST"])
def use_skip(name):
    connection = get_db()
    player = get_player(connection, name)
    config = get_config(connection)

    if (player is not None and config["lifelines_enabled"]
            and not player["skip_used"] and player["phase"] == "question"
            and not player["answered_current"]
            and player["question_index"] < TOTAL_ROUNDS):

        next_index = player["question_index"] + 1
        finished = next_index >= TOTAL_ROUNDS

        connection.execute(
            """
            UPDATE fe_players
            SET skip_used = 1, question_index = ?, answered_current = 0,
                last_correct = NULL, phase_started_at = NULL, lifeline_removed = NULL, option_order = NULL,
                phase = ?
            WHERE id = ?
            """,
            (next_index, "finished" if finished else "question", player["id"])
        )
        connection.commit()

        if not finished and starts_new_round(get_active_rounds(config), next_index):
            connection.close()
            return redirect(url_for("elimination.round_cleared", name=name))

    connection.close()
    return redirect(url_for("elimination.play", name=name))


@elimination_bp.route("/lifeline/ask-team/<name>", methods=["POST"])
def use_ask_team(name):
    connection = get_db()
    player = get_player(connection, name)
    config = get_config(connection)

    if player is None:
        connection.close()
        return jsonify({"error": "not_found"}), 404

    if (not config["lifelines_enabled"] or player["ask_team_used"]
            or player["phase"] != "question" or player["answered_current"]
            or player["question_index"] >= TOTAL_ROUNDS):
        connection.close()
        return jsonify({"error": "unavailable"}), 400

    round_data = get_active_rounds(config)[player["question_index"]]

    connection.execute(
        "UPDATE fe_players SET ask_team_used = 1 WHERE id = ?",
        (player["id"],)
    )
    connection.commit()

    rows = connection.execute(
        "SELECT option, count FROM fe_answer_tally WHERE round_number = ?",
        (player["question_index"],)
    ).fetchall()
    connection.close()

    tally = {row["option"]: row["count"] for row in rows}
    total = sum(tally.values())

    display_letters = "ABCDEFGH"
    order = (player["option_order"] or ",".join(round_data["options"].keys())).split(",")

    percentages = {}
    for i, canonical_key in enumerate(order):
        if canonical_key not in round_data["options"]:
            continue
        votes = tally.get(canonical_key, 0)
        percentages[display_letters[i]] = round((votes / total) * 100) if total else 0

    return jsonify({"percentages": percentages, "responses": total})


@elimination_bp.route("/timer/<name>")
def timer(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None or player["phase"] != "question" or player["status"] == "eliminated":
        connection.close()
        return jsonify({"remaining_seconds": 0, "closed": True})

    config = get_config(connection)

    if player["answered_current"] or not player["phase_started_at"]:
        connection.close()
        return jsonify({"remaining_seconds": config["timer_seconds"], "closed": bool(player["answered_current"])})

    elapsed = connection.execute(
        "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
        (player["phase_started_at"],)
    ).fetchone()["seconds"]

    connection.close()

    remaining = max(0, int(config["timer_seconds"] - elapsed))
    return jsonify({"remaining_seconds": remaining, "closed": remaining <= 0})


@elimination_bp.route("/feedback/<name>")
def feedback(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    if not player["answered_current"] or player["question_index"] >= TOTAL_ROUNDS:
        connection.close()
        return redirect(url_for("elimination.play", name=name))

    config = get_config(connection)
    question = get_active_rounds(config)[player["question_index"]]
    connection.close()

    return render_template(
        "fe_feedback.html",
        name=name,
        player=player,
        question=question,
        correct=bool(player["last_correct"]),
        eliminated=(player["status"] == "eliminated"),
        active_nav="play"
    )


@elimination_bp.route("/advance/<name>", methods=["POST"])
def advance(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    if player["status"] == "eliminated":
        connection.close()
        return redirect(url_for("elimination.eliminated", name=name))

    next_index = player["question_index"] + 1
    finished = next_index >= TOTAL_ROUNDS

    connection.execute(
        """
        UPDATE fe_players
        SET question_index = ?, answered_current = 0, last_correct = NULL,
            phase_started_at = NULL, lifeline_removed = NULL, option_order = NULL,
            phase = ?
        WHERE id = ?
        """,
        (next_index, "finished" if finished else "question", player["id"])
    )

    connection.commit()
    active_rounds = get_active_rounds(get_config(connection))
    connection.close()

    if finished:
        return redirect(url_for("elimination.results", name=name))
    if starts_new_round(active_rounds, next_index):
        return redirect(url_for("elimination.round_cleared", name=name))
    return redirect(url_for("elimination.play", name=name))


@elimination_bp.route("/round-cleared/<name>")
def round_cleared(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    active_rounds = get_active_rounds(get_config(connection))
    connection.close()

    index = player["question_index"]
    if (player["status"] != "in" or player["phase"] != "question"
            or player["answered_current"] or player["phase_started_at"]
            or not starts_new_round(active_rounds, index)):
        return redirect(url_for("elimination.play", name=name))

    return render_template(
        "fe_round_cleared.html",
        name=name,
        player=player,
        cleared=active_rounds[index - 1],
        upcoming=active_rounds[index],
        active_nav="play"
    )


@elimination_bp.route("/eliminated/<name>")
def eliminated(name):
    connection = get_db()
    player = get_player(connection, name)
    connection.close()

    if player is None:
        return redirect(url_for("elimination.join"))

    return render_template(
        "fe_eliminated.html",
        name=name,
        player=player,
        question_number=min(player["question_index"] + 1, TOTAL_ROUNDS),
        active_nav="play"
    )


@elimination_bp.route("/results/<name>")
def results(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    if player["status"] == "eliminated":
        connection.close()
        return redirect(url_for("elimination.eliminated", name=name))

    winner = is_declared_winner(connection, player)
    connection.close()

    if winner:
        return render_template(
            "fe_winner.html", name=name, player=player,
            total_rounds=TOTAL_ROUNDS, active_nav="play"
        )

    return render_template(
        "fe_results.html", name=name, player=player,
        total_rounds=TOTAL_ROUNDS, active_nav="play"
    )


# =========================================================
# LEADERBOARD
# =========================================================

@elimination_bp.route("/leaderboard")
def leaderboard():
    connection = get_db()
    players = connection.execute(
        "SELECT * FROM fe_players ORDER BY (status = 'eliminated') ASC, question_index DESC, name ASC"
    ).fetchall()

    winners = {
        p["name"] for p in players if is_declared_winner(connection, p)
    }

    connection.close()

    return render_template(
        "fe_leaderboard.html",
        players=players,
        total_rounds=TOTAL_ROUNDS,
        avatar_images=AVATAR_IMAGES,
        winners=winners,
        active_nav="leaderboard"
    )


@elimination_bp.route("/leaderboard-data")
def leaderboard_data():
    connection = get_db()
    players = connection.execute(
        "SELECT * FROM fe_players ORDER BY (status = 'eliminated') ASC, question_index DESC, name ASC"
    ).fetchall()

    winners = {p["name"] for p in players if is_declared_winner(connection, p)}
    connection.close()

    rows = []
    for p in players:
        if p["status"] == "eliminated":
            status = "ELIMINATED"
        elif p["name"] in winners:
            status = "WINNER"
        else:
            status = "STILL IN"

        rows.append({
            "name": p["name"],
            "avatar": AVATAR_IMAGES.get(p["avatar"]),
            "progress": f"{min(p['question_index'], TOTAL_ROUNDS)}/{TOTAL_ROUNDS}",
            "status": status
        })

    return jsonify({"players": rows})


# =========================================================
# BIG-SCREEN DISPLAY (for projecting during an in-person game)
# =========================================================

@elimination_bp.route("/display")
def display():
    return render_template(
        "fe_display.html",
        join_url=url_for("elimination.join", _external=True)
    )


@elimination_bp.route("/display-data")
def display_data():
    connection = get_db()
    config = get_config(connection)
    players = connection.execute(
        "SELECT * FROM fe_players ORDER BY (status = 'eliminated') ASC, question_index DESC, name ASC"
    ).fetchall()

    winners = {p["name"] for p in players if is_declared_winner(connection, p)}
    connection.close()

    active_rounds = get_active_rounds(config)
    round_counts = {q["round_number"]: 0 for q in active_rounds}
    eliminated_count = 0
    finished_count = 0

    rows = []
    for p in players:
        round_number = None

        if p["status"] == "eliminated":
            status = "ELIMINATED"
            eliminated_count += 1
        elif p["name"] in winners:
            status = "WINNER"
            finished_count += 1
        elif p["phase"] == "finished":
            status = "STILL IN"
            finished_count += 1
        elif p["phase"] == "question" and p["question_index"] < TOTAL_ROUNDS:
            status = "STILL IN"
            round_number = active_rounds[p["question_index"]]["round_number"]
            round_counts[round_number] = round_counts.get(round_number, 0) + 1
        else:
            status = "STILL IN"

        rows.append({
            "name": p["name"],
            "avatar": AVATAR_IMAGES.get(p["avatar"]),
            "progress": f"{min(p['question_index'], TOTAL_ROUNDS)}/{TOTAL_ROUNDS}",
            "status": status,
            "round_number": round_number
        })

    return jsonify({
        "game_status": config["status"],
        "pin": config["pin"],
        "players": rows,
        "round_counts": round_counts,
        "eliminated_count": eliminated_count,
        "finished_count": finished_count
    })


# =========================================================
# ANSWER REVIEW
# =========================================================

@elimination_bp.route("/review/<name>")
def review(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    config = get_config(connection)
    history_rows = connection.execute(
        """
        SELECT * FROM fe_answer_history
        WHERE player_id = ?
        ORDER BY round_number ASC
        """,
        (player["id"],)
    ).fetchall()
    connection.close()

    active_rounds = get_active_rounds(config)

    reviewed = []
    for row in history_rows:
        if row["round_number"] >= len(active_rounds):
            continue
        round_data = active_rounds[row["round_number"]]
        reviewed.append({
            "round_number": round_data["round_number"],
            "difficulty": round_data["difficulty"],
            "text": round_data["text"],
            "options": round_data["options"],
            "correct_answer": round_data["correct"],
            "explanation": round_data["explanation"],
            "player_answer": row["answer"],
            "was_correct": bool(row["correct"])
        })

    return render_template(
        "fe_review.html",
        name=name,
        player=player,
        reviewed=reviewed,
        active_nav="play"
    )
