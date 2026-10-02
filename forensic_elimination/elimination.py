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
import re
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
Markup = import_module("markupsafe").Markup
escape = import_module("markupsafe").escape

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

# Wrong answers (or running out of time) cost a life; a player is
# eliminated when they run out.
MAX_LIVES = 3

# Tiebreaker: if two or more survivors finish level on correct answers,
# only they play this question. They type the answer (no options). An
# exact answer wins, the fastest exact answer if several get it; if
# nobody gets it exactly, the closest guess wins.
SUDDEN_DEATH = {
    "text": (
        "In 2018 Welshman Jeffery Bevan was jailed for stealing and laundering "
        "$2.4 million from the Bermuda government. He was able to do so making "
        "payments to himself before transferring the money to the UK. How many "
        "bogus payments did he make to himself?"
    ),
    "answer": 52,
}
SUDDEN_DEATH_SECONDS = 30

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
            active_questions TEXT,
            released_round INTEGER DEFAULT 1,
            winner_revealed INTEGER DEFAULT 0,
            sudden_death_status TEXT,
            sudden_death_started_at TEXT
        )
    """)

    existing_config_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(fe_config)")
    }
    for column in ("sudden_death_status", "sudden_death_started_at"):
        if column not in existing_config_columns:
            connection.execute(f"ALTER TABLE fe_config ADD COLUMN {column} TEXT")

    if "winner_revealed" not in existing_config_columns:
        connection.execute(
            "ALTER TABLE fe_config ADD COLUMN winner_revealed INTEGER DEFAULT 0"
        )

    if "released_round" not in existing_config_columns:
        connection.execute(
            "ALTER TABLE fe_config ADD COLUMN released_round INTEGER DEFAULT 1"
        )

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
            lives INTEGER DEFAULT 3,
            question_order TEXT,
            finished_at TEXT,
            in_sudden_death INTEGER DEFAULT 0,
            sd_answer TEXT,
            sd_seconds REAL,
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

    if "in_sudden_death" not in existing_columns:
        connection.execute(
            "ALTER TABLE fe_players ADD COLUMN in_sudden_death INTEGER DEFAULT 0"
        )
    if "sd_answer" not in existing_columns:
        connection.execute("ALTER TABLE fe_players ADD COLUMN sd_answer TEXT")
    if "sd_seconds" not in existing_columns:
        connection.execute("ALTER TABLE fe_players ADD COLUMN sd_seconds REAL")

    if "finished_at" not in existing_columns:
        connection.execute(
            "ALTER TABLE fe_players ADD COLUMN finished_at TEXT"
        )

    if "question_order" not in existing_columns:
        connection.execute(
            "ALTER TABLE fe_players ADD COLUMN question_order TEXT"
        )

    if "lives" not in existing_columns:
        connection.execute(
            f"ALTER TABLE fe_players ADD COLUMN lives INTEGER DEFAULT {MAX_LIVES}"
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
            "text": "Which of the following is a common fraud red flag?",
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
            "text": "Many large frauds continue for years because:",
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
            "text": "Which company claimed its technology could perform hundreds of blood tests from a tiny blood sample?",
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
                "D": "Company assets are physically stolen"
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
                "B": "Preserve the integrity of the original evidence",
                "C": "Analyze the original device whenever possible",
                "D": "Delete irrelevant files before acquisition"
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
                "D": "They were independently verified by several firms"
            },
            "correct": "B",
            "explanation": "Madoff's reported returns were suspicious because they were remarkably consistent and showed unusually little volatility, even during periods of significant market fluctuations."
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
            "explanation": "Approximately $11 billion was involved, making it one of the largest accounting frauds in U.S. history."
        },
        {
            "round_number": 2,
            "difficulty": "INTERMEDIATE",
            "text": "The 2002 movie Catch Me If You Can is based on the real-life story of what infamous fraudster?",
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
            "text": "Which of the following is NOT a common fraud scheme perpetrated by hedge fund managers?",
            "options": {
                "A": "Late trading",
                "B": "Insider trading",
                "C": "Overvaluation of portfolios",
                "D": "Bid rigging"
            },
            "correct": "D",
            "explanation": "Bid rigging is not typically associated with hedge fund fraud, as it involves manipulating competitive bidding processes rather than misusing investor funds or assets."
        }
    ],
    3: [
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "What verification failure was central to the Wirecard scandal involving billions in reported cash?",
            "options": {
                "A": "Failure to independently verify reported funds",
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
            "explanation": "The alias 'Barry Allen' was a reference to The Flash, the fictional superhero whose civilian identity is Barry Allen."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "Under which act was Gunvor S.A. convicted?",
            "options": {
                "A": "Foreign Corrupt Practices Act",
                "B": "Foreign Extortion Prevention Act",
                "C": "Travel Act",
                "D": "Racketeer Influenced and Corrupt Organizations Act"
            },
            "correct": "A",
            "explanation": "Gunvor S.A. was convicted under the <b>Foreign Corrupt Practices Act (FCPA)</b> for bribing foreign officials to secure business."
        },
        {
            "round_number": 3,
            "difficulty": "HARD",
            "text": "Which European bank helped Manuel Chang facilitate the $2 billion scheme?",
            "options": {
                "A": "Deutsche Bank",
                "B": "Credit Suisse",
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
            "explanation": "The scheme involved manipulating the price and trading activity of Hydro (HYDRO) cryptocurrency for fraudulent profit."
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
            "text": "What type of fraud did Hegestratos attempt to commit?",
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
            "text": "Barry Minkow is a famous fraudster known for his Ponzi scheme, which used his cleaning and restoration company ________ to attract investors.",
            "options": {
                "A": "ZZZ Cleaning",
                "B": "ABCD Best",
                "C": "ZZZZ Best",
                "D": "A2Z Cleaning and Restoration"
            },
            "correct": "C",
            "explanation": "Minkow used ZZZZ Best to create the appearance of a successful business and attract investors through fraudulent financial claims."
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


def shuffled_question_order(active_rounds):
    """A random order of every question for one player. Rounds stay in
    order (Easy -> Intermediate -> Hard); only the questions inside each
    round are mixed, so players sitting together see different ones."""
    order = []
    round_ids = []
    for index, question in enumerate(active_rounds):
        if round_ids and active_rounds[round_ids[-1]]["round_number"] != question["round_number"]:
            random.shuffle(round_ids)
            order.extend(round_ids)
            round_ids = []
        round_ids.append(index)
    random.shuffle(round_ids)
    order.extend(round_ids)
    return order


def player_question_ids(config, player):
    """This player's questions, as positions in the game's question list."""
    total = len(get_active_rounds(config))
    raw = player["question_order"] if "question_order" in player.keys() else None
    if raw:
        try:
            order = json.loads(raw)
            if sorted(order) == list(range(total)):
                return order
        except (TypeError, ValueError):
            pass
    return list(range(total))


def get_player_rounds(config, player):
    """This player's questions in the order they will be asked."""
    active_rounds = get_active_rounds(config)
    return [active_rounds[i] for i in player_question_ids(config, player)]


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


def round_numbers(active_rounds):
    """The game's round numbers in play order, e.g. [1, 2, 3]."""
    numbers = []
    for question in active_rounds:
        if question["round_number"] not in numbers:
            numbers.append(question["round_number"])
    return numbers


def first_round_number(active_rounds):
    numbers = round_numbers(active_rounds)
    return numbers[0] if numbers else 1


def released_round(config, active_rounds):
    """The latest round players are allowed to play. Players who finish a
    round wait for the host to release the next one, so everyone can go
    over the answers together on the big screen."""
    value = config["released_round"] if "released_round" in config.keys() else None
    return value or first_round_number(active_rounds)


def round_progress(connection, config):
    """Where the game is: which round is open, how many survivors have
    finished it, and whether the big screen should show the intermission."""
    active_rounds = get_active_rounds(config)
    numbers = round_numbers(active_rounds)
    current = released_round(config, active_rounds)
    players = connection.execute("SELECT * FROM fe_players").fetchall()
    survivors = [p for p in players if p["status"] == "in"]

    def past_current_round(p):
        if p["phase"] == "finished" or p["question_index"] >= len(active_rounds):
            return True
        return active_rounds[p["question_index"]]["round_number"] > current

    done = sum(1 for p in survivors if past_current_round(p))
    complete = bool(survivors) and done == len(survivors)
    later = [n for n in numbers if n > current]

    if config["status"] != "active":
        phase = "lobby"
    elif game_is_over(players):
        # The last round's answers show first. A tie for first goes to
        # sudden death; then the host reveals the winner.
        revealed = config["winner_revealed"] if "winner_revealed" in config.keys() else 0
        sd_status, _ = sudden_death_state(connection, config)
        if revealed:
            phase = "winner"
        elif sd_status == "active":
            phase = "sudden_death"
        elif sd_status == "done":
            phase = "sudden_death_result"
        else:
            phase = "finished"
    elif complete and later:
        phase = "intermission"
    else:
        phase = "playing"

    return {
        "phase": phase,
        "round": current,
        "next_round": later[0] if later else None,
        "done": done,
        "survivors": len(survivors),
        "complete": complete,
        "tied": [p["name"] for p in top_tied(players, correct_counts(connection))]
        if phase == "finished" else [],
    }


def round_review(connection, config, round_number):
    """Every question in a round with its correct answer, for the
    intermission screen."""
    active_rounds = get_active_rounds(config)
    questions = []
    for question in active_rounds:
        if question["round_number"] != round_number:
            continue
        questions.append({
            "text": question["text"],
            "answer": question["options"][question["correct"]],
            "explanation": str(allow_bold(question.get("explanation", ""))),
        })
    difficulty = next(
        (q["difficulty"] for q in active_rounds if q["round_number"] == round_number), ""
    )
    return {"round_number": round_number, "difficulty": difficulty, "questions": questions}


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
    question_id = player_question_ids(config, player)[player["question_index"]]
    round_data = get_active_rounds(config)[question_id]
    correct = 1 if answer == round_data["correct"] else 0

    new_status = player["status"]
    lives = player["lives"]
    if not correct and config["elimination_enabled"]:
        lives = max(0, lives - 1)
        if lives == 0:
            new_status = "eliminated"

    connection.execute(
        """
        UPDATE fe_players
        SET status = ?, lives = ?, answered_current = 1,
            last_correct = ?
        WHERE id = ?
        """,
        (new_status, lives, correct, player["id"])
    )

    if answer in round_data["options"]:
        connection.execute(
            """
            INSERT INTO fe_answer_tally (round_number, option, count)
            VALUES (?, ?, 1)
            ON CONFLICT(round_number, option)
            DO UPDATE SET count = count + 1
            """,
            (question_id, answer)
        )

    connection.execute(
        """
        INSERT INTO fe_answer_history (player_id, round_number, answer, correct)
        VALUES (?, ?, ?, ?)
        """,
        (player["id"], question_id, answer, correct)
    )

    connection.commit()


def host_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("fe_is_host"):
            return redirect(url_for("elimination.host_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@elimination_bp.app_template_filter("allow_bold")
def allow_bold(text):
    """Escape question text but keep <b>...</b> so explanations can bold
    key words."""
    escaped = str(escape(text or ""))
    return Markup(escaped.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"))


def correct_counts(connection):
    """How many questions each player has answered correctly, by player id."""
    return {
        row["player_id"]: row["correct"]
        for row in connection.execute(
            "SELECT player_id, SUM(correct) AS correct FROM fe_answer_history GROUP BY player_id"
        )
    }


def rank_players(connection):
    """Players still in first, then most correct answers, then furthest
    along, then whoever finished first."""
    players = connection.execute("SELECT * FROM fe_players").fetchall()
    correct = correct_counts(connection)
    players.sort(key=lambda p: (
        p["status"] == "eliminated",
        -correct.get(p["id"], 0),
        sudden_death_rank(p),
        -p["question_index"],
        p["finished_at"] is None,
        p["finished_at"] or "",
        p["name"].lower()
    ))
    return players, correct


def game_is_over(players):
    """True once nobody is still answering questions."""
    return bool(players) and not any(
        p["status"] == "in" and p["phase"] != "finished" for p in players
    )


def parse_guess(text):
    """The number in a typed sudden-death answer ("52", "52 payments", "1,000")."""
    match = re.search(r"-?\d[\d,]*", text or "")
    if not match:
        return None
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return None


def sudden_death_rank(player):
    """Sort key among tied players: exact/closest answer first, then fastest."""
    if not player["in_sudden_death"]:
        return (float("inf"), float("inf"))
    guess = parse_guess(player["sd_answer"])
    distance = abs(guess - SUDDEN_DEATH["answer"]) if guess is not None else float("inf")
    seconds = player["sd_seconds"] if player["sd_seconds"] is not None else float("inf")
    return (distance, seconds)


def top_tied(players, correct):
    """Survivors level on the most correct answers, if two or more are."""
    survivors = [p for p in players if p["status"] == "in" and p["phase"] == "finished"]
    if len(survivors) < 2:
        return []
    best = max(correct.get(p["id"], 0) for p in survivors)
    tied = [p for p in survivors if correct.get(p["id"], 0) == best]
    return tied if len(tied) >= 2 else []


def sudden_death_state(connection, config):
    """(status, seconds_left). Closes sudden death once every tied player
    has answered or the time is up."""
    status = config["sudden_death_status"] if "sudden_death_status" in config.keys() else None
    if status != "active":
        return status, 0

    elapsed = connection.execute(
        "SELECT (julianday('now') - julianday(?)) * 86400 AS s",
        (config["sudden_death_started_at"],)
    ).fetchone()["s"] or 0
    waiting = connection.execute(
        "SELECT COUNT(*) AS c FROM fe_players WHERE in_sudden_death = 1 AND sd_seconds IS NULL"
    ).fetchone()["c"]

    # A couple of seconds' grace so an answer sent at 0 still counts.
    if waiting == 0 or elapsed >= SUDDEN_DEATH_SECONDS + 2:
        connection.execute("UPDATE fe_config SET sudden_death_status = 'done' WHERE id = 1")
        connection.commit()
        return "done", 0

    return "active", max(0, int(SUDDEN_DEATH_SECONDS - elapsed + 0.999))


def is_declared_winner(connection, player):
    """The single winner: once nobody is still playing, the surviving
    investigator with the most correct answers. A tie for first is
    settled by sudden death."""
    if player["status"] != "in" or player["phase"] != "finished":
        return False

    players, correct = rank_players(connection)
    if not game_is_over(players):
        return False

    if top_tied(players, correct):
        status, _ = sudden_death_state(connection, get_config(connection))
        if status != "done":
            return False

    return players[0]["id"] == player["id"]


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
    progress = round_progress(connection, config)
    connection.close()

    return render_template(
        "fe_host.html",
        config=config,
        progress=progress,
        players=players,
        total_rounds=TOTAL_ROUNDS,
        max_lives=MAX_LIVES,
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

    response = send_file(buffer, mimetype="image/png")
    # The PIN changes on every reset, so never let a browser reuse an old code.
    response.headers["Cache-Control"] = "no-store"
    return response


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
            "UPDATE fe_config SET status = 'active', released_round = ?, winner_revealed = 0, sudden_death_status = NULL, sudden_death_started_at = NULL WHERE id = 1",
            (first_round_number(get_active_rounds(config)),)
        )
        connection.execute(
            """
            UPDATE fe_players
            SET phase = 'question', question_index = 0,
                answered_current = 0, phase_started_at = NULL, lives = ?
            WHERE phase = 'lobby'
            """,
            (MAX_LIVES,)
        )

        # Every player gets their own shuffle of the questions in each round.
        active_rounds = get_active_rounds(config)
        for row in connection.execute(
            "SELECT id FROM fe_players WHERE phase = 'question'"
        ).fetchall():
            connection.execute(
                "UPDATE fe_players SET question_order = ? WHERE id = ?",
                (json.dumps(shuffled_question_order(active_rounds)), row["id"])
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
        "UPDATE fe_config SET pin = ?, status = 'lobby', active_questions = ?, released_round = 1, winner_revealed = 0, sudden_death_status = NULL, sudden_death_started_at = NULL WHERE id = 1",
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

        existing = get_player(connection, name) if name else None

        if not name:
            error = "Enter your investigator name."
        elif pin != config["pin"]:
            error = "That game PIN doesn't match. Ask the host for the current PIN."
        elif existing is not None and (
                config["status"] != "lobby"
                or session.get("fe_player_name") == name):
            # Rejoin: a player whose tab closed or phone died comes back
            # with the same name and PIN and carries on where they left off.
            connection.close()
            session["fe_player_name"] = name
            return redirect(url_for("elimination.waiting", name=name))
        elif existing is not None:
            error = "That name is already taken this game. Try another."
        elif config["status"] != "lobby":
            error = "This game has already started. Ask the host to reset for a new game."
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
            session["fe_player_name"] = name
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

    if player["status"] == "eliminated":
        return redirect(url_for("elimination.eliminated", name=name))
    if player["phase"] == "finished":
        return redirect(url_for("elimination.results", name=name))
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
            "UPDATE fe_players SET phase = 'finished', finished_at = COALESCE(finished_at, datetime('now')) WHERE id = ?",
            (player["id"],)
        )
        connection.commit()
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    active_rounds = get_player_rounds(config, player)

    if (active_rounds[player["question_index"]]["round_number"]
            > released_round(config, active_rounds)):
        connection.close()
        return redirect(url_for("elimination.round_cleared", name=name))

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
        lives_enabled=config["elimination_enabled"],
        max_lives=MAX_LIVES,
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

        round_data = get_player_rounds(config, player)[player["question_index"]]
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

    question_id = player_question_ids(config, player)[player["question_index"]]
    round_data = get_active_rounds(config)[question_id]

    connection.execute(
        "UPDATE fe_players SET ask_team_used = 1 WHERE id = ?",
        (player["id"],)
    )
    connection.commit()

    rows = connection.execute(
        "SELECT option, count FROM fe_answer_tally WHERE round_number = ?",
        (question_id,)
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
    question = get_player_rounds(config, player)[player["question_index"]]
    connection.close()

    # Options were shuffled on screen, so name the correct answer by the
    # letter the player actually saw, plus its text.
    order = (player["option_order"] or ",".join(question["options"].keys())).split(",")
    shown_letter = "ABCDEFGH"[order.index(question["correct"])] if question["correct"] in order else question["correct"]
    correct_answer = f'{shown_letter}. {question["options"][question["correct"]]}'

    return render_template(
        "fe_feedback.html",
        name=name,
        player=player,
        question=question,
        correct=bool(player["last_correct"]),
        correct_answer=correct_answer,
        eliminated=(player["status"] == "eliminated"),
        lives_enabled=config["elimination_enabled"],
        max_lives=MAX_LIVES,
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
            phase = ?,
            finished_at = CASE WHEN ? THEN datetime('now') ELSE finished_at END
        WHERE id = ?
        """,
        (next_index, "finished" if finished else "question", finished, player["id"])
    )

    connection.commit()
    active_rounds = get_player_rounds(get_config(connection), player)
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

    config = get_config(connection)
    active_rounds = get_player_rounds(config, player)
    progress = round_progress(connection, config)
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
        released=active_rounds[index]["round_number"] <= released_round(config, active_rounds),
        progress=progress,
        active_nav="play"
    )


@elimination_bp.route("/round-status/<name>")
def round_status(name):
    """Polled by the round-cleared screen while a player waits."""
    connection = get_db()
    player = get_player(connection, name)
    if player is None:
        connection.close()
        return jsonify({"released": True})

    config = get_config(connection)
    active_rounds = get_player_rounds(config, player)
    progress = round_progress(connection, config)
    connection.close()

    index = min(player["question_index"], len(active_rounds) - 1)
    return jsonify({
        "released": active_rounds[index]["round_number"] <= released_round(config, active_rounds),
        "done": progress["done"],
        "survivors": progress["survivors"],
    })


@elimination_bp.route("/host/next-round", methods=["POST"])
@host_required
def host_next_round():
    """Open the next round for everyone waiting at the round-cleared screen."""
    connection = get_db()
    config = get_config(connection)
    progress = round_progress(connection, config)
    if config["status"] == "active" and progress["next_round"]:
        connection.execute(
            "UPDATE fe_config SET released_round = ? WHERE id = 1",
            (progress["next_round"],)
        )
        connection.commit()
    connection.close()

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return redirect(url_for("elimination.host"))


@elimination_bp.route("/host/sudden-death", methods=["POST"])
@host_required
def host_sudden_death():
    """Start the tiebreaker for the players level on first place."""
    connection = get_db()
    config = get_config(connection)
    progress = round_progress(connection, config)
    if progress["phase"] == "finished" and progress["tied"]:
        players, correct = rank_players(connection)
        for p in top_tied(players, correct):
            connection.execute(
                "UPDATE fe_players SET in_sudden_death = 1, sd_answer = NULL, sd_seconds = NULL WHERE id = ?",
                (p["id"],)
            )
        connection.execute(
            "UPDATE fe_config SET sudden_death_status = 'active', sudden_death_started_at = datetime('now') WHERE id = 1"
        )
        connection.commit()
    connection.close()

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return redirect(url_for("elimination.host"))


@elimination_bp.route("/sudden-death/<name>", methods=["GET", "POST"])
def sudden_death(name):
    connection = get_db()
    player = get_player(connection, name)
    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))
    if not player["in_sudden_death"]:
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    config = get_config(connection)
    status, seconds_left = sudden_death_state(connection, config)

    if request.method == "POST":
        if status == "active" and player["sd_seconds"] is None:
            elapsed = connection.execute(
                "SELECT (julianday('now') - julianday(?)) * 86400 AS s",
                (config["sudden_death_started_at"],)
            ).fetchone()["s"]
            answer = (request.form.get("answer") or "").strip()[:40]
            connection.execute(
                "UPDATE fe_players SET sd_answer = ?, sd_seconds = ? WHERE id = ?",
                (answer, round(elapsed, 2), player["id"])
            )
            connection.commit()
        connection.close()
        return redirect(url_for("elimination.sudden_death", name=name))

    connection.close()
    if status != "active":
        return redirect(url_for("elimination.results", name=name))

    return render_template(
        "fe_sudden_death.html",
        name=name,
        question=SUDDEN_DEATH["text"],
        answered=player["sd_seconds"] is not None,
        answer=player["sd_answer"],
        seconds_left=seconds_left,
        total_seconds=SUDDEN_DEATH_SECONDS,
        active_nav="play"
    )


@elimination_bp.route("/sudden-death-status/<name>")
def sudden_death_status(name):
    connection = get_db()
    config = get_config(connection)
    status, seconds_left = sudden_death_state(connection, config)
    connection.close()
    return jsonify({"status": status, "seconds_left": seconds_left})


@elimination_bp.route("/host/show-winner", methods=["POST"])
@host_required
def host_show_winner():
    """Switch the big screen from the last round's answers to the winner."""
    connection = get_db()
    config = get_config(connection)
    progress = round_progress(connection, config)
    if (progress["phase"] == "finished" and not progress["tied"]) or progress["phase"] == "sudden_death_result":
        connection.execute("UPDATE fe_config SET winner_revealed = 1 WHERE id = 1")
        connection.commit()
    connection.close()

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return redirect(url_for("elimination.host"))


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

    config = get_config(connection)
    sd_status, _ = sudden_death_state(connection, config)
    if sd_status == "active" and player["in_sudden_death"] and player["sd_seconds"] is None:
        connection.close()
        return redirect(url_for("elimination.sudden_death", name=name))

    winner = is_declared_winner(connection, player)
    players, correct = rank_players(connection)
    tied_names = [p["name"] for p in top_tied(players, correct)]
    connection.close()

    game_over = game_is_over(players)
    placement = next(i for i, p in enumerate(players, 1) if p["id"] == player["id"])
    # First place is still being decided (tie, sudden death not finished).
    deciding = game_over and bool(tied_names) and sd_status != "done"

    return render_template(
        "fe_winner.html" if winner else "fe_results.html",
        name=name, player=player, correct=correct.get(player["id"], 0),
        game_over=game_over, placement=placement, player_count=len(players),
        deciding=deciding, in_tie=name in tied_names, sd_status=sd_status or "",
        total_rounds=TOTAL_ROUNDS, active_nav="play"
    )


# =========================================================
# LEADERBOARD
# =========================================================

@elimination_bp.route("/leaderboard")
def leaderboard():
    connection = get_db()
    players, correct = rank_players(connection)

    winners = {
        p["name"] for p in players if is_declared_winner(connection, p)
    }

    connection.close()

    return render_template(
        "fe_leaderboard.html",
        players=players,
        correct=correct,
        total_rounds=TOTAL_ROUNDS,
        avatar_images=AVATAR_IMAGES,
        winners=winners,
        active_nav="leaderboard"
    )


@elimination_bp.route("/leaderboard-data")
def leaderboard_data():
    connection = get_db()
    players, correct = rank_players(connection)

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
            "progress": f"{correct.get(p['id'], 0)}/{TOTAL_ROUNDS} correct",
            "status": status
        })

    sd_connection = get_db()
    sd_status, _ = sudden_death_state(sd_connection, get_config(sd_connection))
    sd_connection.close()
    return jsonify({
        "players": rows,
        "game_over": game_is_over(players),
        "sd_status": sd_status or ""
    })


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
    players, correct = rank_players(connection)

    winners = {p["name"] for p in players if is_declared_winner(connection, p)}
    connection.close()

    active_rounds = get_active_rounds(config)
    round_counts = {q["round_number"]: 0 for q in active_rounds}
    open_round = released_round(config, active_rounds)
    eliminated_count = 0
    finished_count = 0
    waiting_count = 0

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
            if round_number > open_round:
                # Done with the open round, waiting for the next to start.
                status = "WAITING"
                waiting_count += 1
                round_number = None
            else:
                round_counts[round_number] = round_counts.get(round_number, 0) + 1
        else:
            status = "STILL IN"

        rows.append({
            "name": p["name"],
            "avatar": AVATAR_IMAGES.get(p["avatar"]),
            "progress": f"{correct.get(p['id'], 0)}/{TOTAL_ROUNDS} correct",
            "status": status,
            "round_number": round_number
        })

    review_connection = get_db()
    progress = round_progress(review_connection, config)
    review = None
    if progress["phase"] in ("intermission", "finished"):
        review = round_review(review_connection, config, progress["round"])

    sudden = None
    if progress["phase"] in ("sudden_death", "sudden_death_result", "winner"):
        _, seconds_left = sudden_death_state(review_connection, get_config(review_connection))
        contenders = [p for p in players if p["in_sudden_death"]]
        if contenders:
            reveal = progress["phase"] != "sudden_death"
            if not reveal:
                # Ranked order would hint at who's closer, so list by name until the reveal.
                contenders.sort(key=lambda p: p["name"].lower())
            sudden = {
                "question": SUDDEN_DEATH["text"],
                "answer": SUDDEN_DEATH["answer"] if reveal else None,
                "seconds_left": seconds_left,
                "total_seconds": SUDDEN_DEATH_SECONDS,
                "players": [
                    {
                        "name": p["name"],
                        "answered": p["sd_seconds"] is not None,
                        # Guesses stay hidden until sudden death is over.
                        "guess": (p["sd_answer"] or "-") if reveal else None,
                        "seconds": p["sd_seconds"] if reveal else None,
                        "exact": reveal and parse_guess(p["sd_answer"]) == SUDDEN_DEATH["answer"],
                    }
                    # players is already ranked, so the sudden-death winner is first.
                    for p in contenders
                ],
            }
    review_connection.close()

    return jsonify({
        "phase": progress["phase"],
        "progress": progress,
        "review": review,
        "sudden_death": sudden,
        "is_host": bool(session.get("fe_is_host")),
        "game_status": config["status"],
        "pin": config["pin"],
        "players": rows,
        "round_counts": round_counts,
        "eliminated_count": eliminated_count,
        "finished_count": finished_count,
        "waiting_count": waiting_count
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
        ORDER BY rowid ASC
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
