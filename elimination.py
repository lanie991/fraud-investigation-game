"""
FORENSIC ELIMINATION
A standalone Kahoot-style, single-elimination fraud trivia game that
runs alongside the existing "Who Stole the Money?" investigation game.

Each player joins with a game PIN, then works through their own set of
Easy -> Intermediate -> Hard trivia questions at their own pace. A wrong
answer eliminates them (when elimination is enabled). Anyone who survives
reaches a Final Round case file worth extra points.

The sample questions below are PLACEHOLDER CONTENT. Replace the entries
in EASY_QUESTIONS / INTERMEDIATE_QUESTIONS / HARD_QUESTIONS / FINAL_CASE
with real content whenever it's ready -- the shape of each dict is all
that matters to the rest of this file.
"""

from importlib import import_module
import random
import sqlite3
import string

flask = import_module("flask")

Blueprint = flask.Blueprint
render_template = flask.render_template
redirect = flask.redirect
request = flask.request
jsonify = flask.jsonify
url_for = flask.url_for

elimination_bp = Blueprint(
    "elimination",
    __name__,
    url_prefix="/elimination"
)

DATABASE = "fraud_game.db"

DEFAULT_TIMER_SECONDS = 20

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
            lifelines_enabled INTEGER NOT NULL DEFAULT 1
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS fe_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            avatar TEXT DEFAULT 'detective_black',
            score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'in',
            phase TEXT DEFAULT 'lobby',
            question_index INTEGER DEFAULT 0,
            answered_current INTEGER DEFAULT 0,
            last_correct INTEGER,
            last_points INTEGER DEFAULT 0,
            phase_started_at TEXT,
            lifeline_used INTEGER DEFAULT 0,
            lifeline_removed TEXT,
            final_index INTEGER DEFAULT 0,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    existing_config = connection.execute(
        "SELECT COUNT(*) AS count FROM fe_config"
    ).fetchone()

    if existing_config["count"] == 0:
        connection.execute(
            """
            INSERT INTO fe_config (id, pin, status, timer_seconds,
                                    elimination_enabled, lifelines_enabled)
            VALUES (1, ?, 'lobby', ?, 1, 1)
            """,
            (generate_pin(), DEFAULT_TIMER_SECONDS)
        )

    connection.commit()
    connection.close()


# =========================================================
# QUESTION BANK (PLACEHOLDER CONTENT -- REPLACE WHEN READY)
# =========================================================

EASY_QUESTIONS = [
    {
        "text": "Which of the following is a common red flag in financial fraud?",
        "options": {
            "A": "Consistent reconciliations",
            "B": "Unusual transactions just below approval thresholds",
            "C": "Complete documentation",
            "D": "Regular internal audits"
        },
        "correct": "B",
        "explanation": "Unusual transactions just below approval thresholds may indicate an attempt to avoid additional review or scrutiny.",
        "points": 10
    },
    {
        "text": "What does the term 'skimming' refer to in occupational fraud?",
        "options": {
            "A": "Stealing cash before it is recorded in the books",
            "B": "Overstating company revenue",
            "C": "Falsifying a resume",
            "D": "Filing a late tax return"
        },
        "correct": "A",
        "explanation": "Skimming is the theft of cash before it ever enters the accounting system, making it hard to trace.",
        "points": 10
    },
    {
        "text": "Which document is most useful for verifying that a vendor actually exists?",
        "options": {
            "A": "A birthday card",
            "B": "The company holiday schedule",
            "C": "A business registration or W-9 form",
            "D": "An employee's parking pass"
        },
        "correct": "C",
        "explanation": "Business registration and tax documents help confirm a vendor is a real, independent entity rather than a shell company.",
        "points": 10
    },
    {
        "text": "What is 'segregation of duties' designed to prevent?",
        "options": {
            "A": "Employees taking lunch breaks together",
            "B": "One person controlling an entire transaction from start to finish",
            "C": "Slow computer systems",
            "D": "Office disagreements"
        },
        "correct": "B",
        "explanation": "Splitting responsibilities across multiple people makes it harder for any single employee to commit and conceal fraud alone.",
        "points": 10
    }
]

INTERMEDIATE_QUESTIONS = [
    {
        "text": "A vendor's registered address matches an employee's home address. What does this suggest?",
        "options": {
            "A": "Nothing unusual -- coincidences happen",
            "B": "A possible conflict of interest or shell company",
            "C": "The vendor offers home delivery",
            "D": "The employee works remotely"
        },
        "correct": "B",
        "explanation": "A vendor address matching an employee's home address is a classic shell-company red flag worth investigating further.",
        "points": 20
    },
    {
        "text": "In the fraud triangle, 'rationalization' refers to:",
        "options": {
            "A": "The method used to hide the fraud",
            "B": "The justification a person uses to excuse their dishonest act",
            "C": "The financial pressure driving the fraud",
            "D": "The audit process that catches the fraud"
        },
        "correct": "B",
        "explanation": "Rationalization is the internal excuse ('I'll pay it back', 'I deserve this') that lets someone reconcile fraud with their self-image.",
        "points": 20
    },
    {
        "text": "Which of these is the strongest indicator of invoice fraud?",
        "options": {
            "A": "An invoice number formatted differently than the vendor's usual sequence",
            "B": "An invoice printed in color",
            "C": "An invoice paid by check instead of wire",
            "D": "An invoice with a due date"
        },
        "correct": "A",
        "explanation": "Inconsistent invoice numbering compared to a vendor's normal pattern can indicate a fabricated or altered invoice.",
        "points": 20
    }
]

HARD_QUESTIONS = [
    {
        "text": "A payment is split into three smaller transactions, each just under the $10,000 reporting threshold. This is best described as:",
        "options": {
            "A": "Structuring",
            "B": "Netting",
            "C": "Amortization",
            "D": "Reconciliation"
        },
        "correct": "A",
        "explanation": "Structuring (or 'smurfing') deliberately breaks up transactions to stay under reporting thresholds and avoid detection.",
        "points": 30
    },
    {
        "text": "During an investigation, an employee's login logs show activity from a location inconsistent with their claimed whereabouts. This type of evidence is called:",
        "options": {
            "A": "Circumstantial testimony",
            "B": "Digital forensic evidence",
            "C": "Hearsay",
            "D": "Character evidence"
        },
        "correct": "B",
        "explanation": "System and login logs are digital forensic evidence -- objective records that can corroborate or contradict a person's account.",
        "points": 30
    },
    {
        "text": "Which stage of money laundering involves moving illicit funds through multiple accounts or shell entities to obscure their origin?",
        "options": {
            "A": "Placement",
            "B": "Layering",
            "C": "Integration",
            "D": "Disbursement"
        },
        "correct": "B",
        "explanation": "Layering is the stage where funds are moved through a complex web of transactions specifically to break the audit trail.",
        "points": 30
    }
]

REGULAR_QUESTIONS = EASY_QUESTIONS + INTERMEDIATE_QUESTIONS + HARD_QUESTIONS

STAGE_BOUNDARIES = [
    ("EASY", len(EASY_QUESTIONS)),
    ("INTERMEDIATE", len(INTERMEDIATE_QUESTIONS)),
    ("HARD", len(HARD_QUESTIONS))
]

STAGE_NAMES = ["EASY", "INTERMEDIATE", "HARD", "FINAL"]

FINAL_CASE = {
    "title": "CASE INVESTIGATION",
    "points": 50,
    "body": (
        "A finance manager creates a new vendor. The manager approves "
        "the vendor and their invoices. Over 12 months, the company "
        "pays the vendor $475,000. The vendor's registered address is "
        "connected to a person related to the manager. No competitive "
        "bids were obtained and several invoices contain nearly "
        "identical descriptions. The manager says the vendor provided "
        "\"special consulting services.\""
    ),
    "questions": [
        {
            "label": "Control weakness",
            "text": "What is the primary internal control weakness in this scenario?",
            "options": {
                "A": "The vendor was paid by direct deposit",
                "B": "The same person created, approved and managed the vendor relationship",
                "C": "The invoices were sent by email",
                "D": "The company used accounting software"
            },
            "correct": "B",
            "explanation": "One person controlling vendor setup, approval and payment removes the checks that segregation of duties provides.",
            "points": 10
        },
        {
            "label": "Fraud scheme",
            "text": "What type of fraud scheme does this scenario most closely resemble?",
            "options": {
                "A": "Payroll fraud",
                "B": "Shell company / conflict-of-interest vendor fraud",
                "C": "Expense reimbursement fraud",
                "D": "Check tampering"
            },
            "correct": "B",
            "explanation": "A vendor connected to the approving manager, with no competitive bidding, is a textbook shell-company conflict of interest scheme.",
            "points": 10
        },
        {
            "label": "Evidence to obtain",
            "text": "Which piece of evidence would be most valuable to obtain next?",
            "options": {
                "A": "The vendor's business registration and ownership records",
                "B": "The office lunch menu",
                "C": "The company's parking policy",
                "D": "The manager's calendar for next month"
            },
            "correct": "A",
            "explanation": "Ownership and registration records can confirm whether the vendor is genuinely independent or connected to the manager.",
            "points": 10
        },
        {
            "label": "Fraud Triangle",
            "text": "Which leg of the Fraud Triangle does the manager's approval authority over the vendor represent?",
            "options": {
                "A": "Pressure",
                "B": "Rationalization",
                "C": "Opportunity",
                "D": "Detection"
            },
            "correct": "C",
            "explanation": "Unchecked authority to create, approve and pay a vendor is what creates the opportunity to commit the fraud.",
            "points": 10
        },
        {
            "label": "Conclusion",
            "text": "Based on the evidence, what is the most appropriate next step?",
            "options": {
                "A": "Take no action since invoices exist",
                "B": "Escalate to a formal fraud investigation and suspend further payments",
                "C": "Ask the manager to review their own vendor file",
                "D": "Close the case with no further review"
            },
            "correct": "B",
            "explanation": "Given the conflict of interest and lack of competitive bidding, the matter should be escalated and payments paused pending investigation.",
            "points": 10
        }
    ]
}


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


def current_stage_label(question_index):
    seen = 0
    for label, count in STAGE_BOUNDARIES:
        seen += count
        if question_index < seen:
            return label
    return "FINAL"


def grade_regular_answer(connection, player, config, answer):
    question = REGULAR_QUESTIONS[player["question_index"]]
    correct = 1 if answer == question["correct"] else 0
    points = question["points"] if correct else 0

    new_status = player["status"]
    if not correct and config["elimination_enabled"]:
        new_status = "eliminated"

    connection.execute(
        """
        UPDATE fe_players
        SET score = score + ?, status = ?, answered_current = 1,
            last_correct = ?, last_points = ?
        WHERE id = ?
        """,
        (points, new_status, correct, points, player["id"])
    )
    connection.commit()


def grade_final_answer(connection, player, answer):
    question = FINAL_CASE["questions"][player["final_index"]]
    correct = 1 if answer == question["correct"] else 0
    points = question["points"] if correct else 0

    connection.execute(
        """
        UPDATE fe_players
        SET score = score + ?, final_index = final_index + 1
        WHERE id = ?
        """,
        (points, player["id"])
    )
    connection.commit()


def is_declared_winner(connection, player):
    """Best-effort winner check under independent, per-player pacing.

    Since every player advances on their own clock instead of a single
    host-driven round, we can only call someone the last investigator
    standing once every other player has either been eliminated or has
    also finished the game.
    """
    if player["status"] != "in" or player["phase"] != "finished":
        return False

    others = connection.execute(
        "SELECT * FROM fe_players WHERE id != ?", (player["id"],)
    ).fetchall()

    if not others:
        return True

    for other in others:
        still_playing = other["status"] == "in" and other["phase"] != "finished"
        if still_playing:
            return False

    top_score = max(
        [player["score"]] + [o["score"] for o in others if o["status"] == "in"]
    )

    return player["score"] == top_score


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
    return render_template(
        "fe_case_files.html",
        easy_questions=EASY_QUESTIONS,
        intermediate_questions=INTERMEDIATE_QUESTIONS,
        hard_questions=HARD_QUESTIONS,
        final_case=FINAL_CASE,
        active_nav="case_files"
    )


# =========================================================
# HOST
# =========================================================

@elimination_bp.route("/host")
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
        avatar_images=AVATAR_IMAGES
    )


@elimination_bp.route("/host/settings", methods=["POST"])
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


@elimination_bp.route("/host/reset", methods=["POST"])
def host_reset():
    connection = get_db()
    connection.execute("DELETE FROM fe_players")
    connection.execute(
        "UPDATE fe_config SET pin = ?, status = 'lobby' WHERE id = 1",
        (generate_pin(),)
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
        active_nav="play"
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
        avatar_images=AVATAR_IMAGES
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


# =========================================================
# REGULAR QUESTIONS (EASY / INTERMEDIATE / HARD)
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

    if player["phase"] == "final":
        connection.close()
        return redirect(url_for("elimination.final_round", name=name))

    if player["phase"] == "finished":
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    if player["phase"] != "question":
        connection.close()
        return redirect(url_for("elimination.waiting", name=name))

    if player["question_index"] >= len(REGULAR_QUESTIONS):
        connection.execute(
            "UPDATE fe_players SET phase = 'final', final_index = 0 WHERE id = ?",
            (player["id"],)
        )
        connection.commit()
        connection.close()
        return redirect(url_for("elimination.final_round", name=name))

    if request.method == "POST":
        if not player["answered_current"]:
            answer = request.form.get("answer")
            grade_regular_answer(connection, player, config, answer)
        connection.close()
        return redirect(url_for("elimination.feedback", name=name))

    if player["answered_current"]:
        connection.close()
        return redirect(url_for("elimination.feedback", name=name))

    if not player["phase_started_at"]:
        connection.execute(
            "UPDATE fe_players SET phase_started_at = datetime('now') WHERE id = ?",
            (player["id"],)
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

    question = REGULAR_QUESTIONS[player["question_index"]]
    removed_options = set()
    if player["lifeline_removed"]:
        removed_options = set(player["lifeline_removed"].split(","))

    connection.close()

    return render_template(
        "fe_question.html",
        name=name,
        player=player,
        question=question,
        question_number=player["question_index"] + 1,
        total_questions=len(REGULAR_QUESTIONS),
        stage=current_stage_label(player["question_index"]),
        stage_names=STAGE_NAMES,
        timer_seconds=config["timer_seconds"],
        remaining_seconds=max(0, int(config["timer_seconds"] - elapsed)),
        lifelines_enabled=config["lifelines_enabled"],
        removed_options=removed_options
    )


@elimination_bp.route("/lifeline/<name>", methods=["POST"])
def use_lifeline(name):
    connection = get_db()
    player = get_player(connection, name)
    config = get_config(connection)

    if (player is not None and config["lifelines_enabled"]
            and not player["lifeline_used"] and player["phase"] == "question"
            and not player["answered_current"]
            and player["question_index"] < len(REGULAR_QUESTIONS)):

        question = REGULAR_QUESTIONS[player["question_index"]]
        wrong_options = [key for key in question["options"] if key != question["correct"]]
        random.shuffle(wrong_options)
        removed = ",".join(wrong_options[:2])

        connection.execute(
            """
            UPDATE fe_players
            SET lifeline_used = 1, lifeline_removed = ?
            WHERE id = ?
            """,
            (removed, player["id"])
        )
        connection.commit()

    connection.close()
    return redirect(url_for("elimination.play", name=name))


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

    if not player["answered_current"] or player["question_index"] >= len(REGULAR_QUESTIONS):
        connection.close()
        return redirect(url_for("elimination.play", name=name))

    question = REGULAR_QUESTIONS[player["question_index"]]
    connection.close()

    return render_template(
        "fe_feedback.html",
        name=name,
        player=player,
        question=question,
        correct=bool(player["last_correct"]),
        points=player["last_points"],
        eliminated=(player["status"] == "eliminated")
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

    if next_index >= len(REGULAR_QUESTIONS):
        connection.execute(
            """
            UPDATE fe_players
            SET phase = 'final', question_index = ?, answered_current = 0,
                last_correct = NULL, phase_started_at = NULL, final_index = 0
            WHERE id = ?
            """,
            (next_index, player["id"])
        )
    else:
        connection.execute(
            """
            UPDATE fe_players
            SET question_index = ?, answered_current = 0,
                last_correct = NULL, phase_started_at = NULL, lifeline_removed = NULL
            WHERE id = ?
            """,
            (next_index, player["id"])
        )

    connection.commit()
    connection.close()

    if next_index >= len(REGULAR_QUESTIONS):
        return redirect(url_for("elimination.final_round", name=name))
    return redirect(url_for("elimination.play", name=name))


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
        question_number=min(player["question_index"] + 1, len(REGULAR_QUESTIONS))
    )


# =========================================================
# FINAL ROUND (CASE FILE)
# =========================================================

@elimination_bp.route("/final/<name>", methods=["GET", "POST"])
def final_round(name):
    connection = get_db()
    player = get_player(connection, name)

    if player is None:
        connection.close()
        return redirect(url_for("elimination.join"))

    if player["status"] == "eliminated":
        connection.close()
        return redirect(url_for("elimination.eliminated", name=name))

    if player["phase"] == "finished":
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    if player["phase"] != "final":
        connection.close()
        return redirect(url_for("elimination.play", name=name))

    if player["final_index"] >= len(FINAL_CASE["questions"]):
        connection.execute(
            "UPDATE fe_players SET phase = 'finished' WHERE id = ?",
            (player["id"],)
        )
        connection.commit()
        connection.close()
        return redirect(url_for("elimination.results", name=name))

    if request.method == "POST":
        answer = request.form.get("answer")
        grade_final_answer(connection, player, answer)
        player = get_player(connection, player["name"])

        if player["final_index"] >= len(FINAL_CASE["questions"]):
            connection.execute(
                "UPDATE fe_players SET phase = 'finished' WHERE id = ?",
                (player["id"],)
            )
            connection.commit()
            connection.close()
            return redirect(url_for("elimination.results", name=name))

        connection.close()
        return redirect(url_for("elimination.final_round", name=name))

    question = FINAL_CASE["questions"][player["final_index"]]
    connection.close()

    return render_template(
        "fe_final.html",
        name=name,
        player=player,
        case=FINAL_CASE,
        question=question,
        question_number=player["final_index"] + 1,
        total_questions=len(FINAL_CASE["questions"])
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
        return render_template("fe_winner.html", name=name, player=player)

    return render_template("fe_results.html", name=name, player=player)


# =========================================================
# LEADERBOARD
# =========================================================

@elimination_bp.route("/leaderboard")
def leaderboard():
    connection = get_db()
    players = connection.execute(
        "SELECT * FROM fe_players ORDER BY score DESC, name ASC"
    ).fetchall()

    winners = {
        p["name"] for p in players if is_declared_winner(connection, p)
    }

    connection.close()

    return render_template(
        "fe_leaderboard.html",
        players=players,
        avatar_images=AVATAR_IMAGES,
        winners=winners,
        active_nav="leaderboard"
    )
