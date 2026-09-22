"""
FORENSIC ELIMINATION
A standalone Kahoot-style, single-elimination fraud trivia game that
runs alongside the existing "Who Stole the Money?" investigation game.

Each player joins with a game PIN, then works through their own set of
three rounds (Easy, Intermediate, Hard) at their own pace. A wrong
answer eliminates them (when elimination is enabled).

The sample questions below are PLACEHOLDER CONTENT. Replace the entries
in ROUNDS with real content whenever it's ready -- the shape of each
dict is all that matters to the rest of this file.
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
            fifty_fifty_used INTEGER DEFAULT 0,
            lifeline_removed TEXT,
            skip_used INTEGER DEFAULT 0,
            ask_team_used INTEGER DEFAULT 0,
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
            correct INTEGER NOT NULL,
            points INTEGER NOT NULL DEFAULT 0
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
#
# ROUNDS is played in order: Round 1 (Easy) -> Round 2 (Intermediate)
# -> Round 3 (Hard). Each entry's shape is all that matters.
# =========================================================

ROUNDS = [
    {
        "round_number": 1,
        "difficulty": "EASY",
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
        "round_number": 2,
        "difficulty": "INTERMEDIATE",
        "text": "Which of the following best describes a hash value in digital forensics?",
        "options": {
            "A": "A file's unique digital fingerprint used to verify integrity",
            "B": "A method used to encrypt deleted files",
            "C": "A tool for recovering lost passwords",
            "D": "A type of malware used to hide data"
        },
        "correct": "A",
        "explanation": "A hash value is a fixed-length fingerprint of a file's contents -- if the file changes at all, the hash changes, which is how investigators verify evidence hasn't been altered.",
        "points": 20
    },
    {
        "round_number": 3,
        "difficulty": "HARD",
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
    }
]


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
    round_data = ROUNDS[player["question_index"]]
    correct = 1 if answer == round_data["correct"] else 0
    points = round_data["points"] if correct else 0

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

    if answer in round_data["options"]:
        connection.execute(
            """
            INSERT INTO fe_answer_tally (round_number, option, count)
            VALUES (?, ?, 1)
            ON CONFLICT(round_number, option)
            DO UPDATE SET count = count + 1
            """,
            (round_data["round_number"], answer)
        )

    connection.execute(
        """
        INSERT INTO fe_answer_history (player_id, round_number, answer, correct, points)
        VALUES (?, ?, ?, ?, ?)
        """,
        (player["id"], round_data["round_number"], answer, correct, points)
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
        rounds=ROUNDS,
        active_nav="case_files"
    )


@elimination_bp.route("/settings")
def settings():
    return redirect(url_for("elimination.host"))


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
        avatar_images=AVATAR_IMAGES,
        active_nav="settings"
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
    connection.execute("DELETE FROM fe_answer_tally")
    connection.execute("DELETE FROM fe_answer_history")
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
# ROUNDS 1-5
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

    if player["question_index"] >= len(ROUNDS):
        connection.execute(
            "UPDATE fe_players SET phase = 'finished' WHERE id = ?",
            (player["id"],)
        )
        connection.commit()
        connection.close()
        return redirect(url_for("elimination.results", name=name))

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

    round_data = ROUNDS[player["question_index"]]
    removed_options = set()
    if player["lifeline_removed"]:
        removed_options = set(player["lifeline_removed"].split(","))

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
        rounds=ROUNDS,
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
            and player["question_index"] < len(ROUNDS)):

        round_data = ROUNDS[player["question_index"]]
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
            and player["question_index"] < len(ROUNDS)):

        next_index = player["question_index"] + 1
        finished = next_index >= len(ROUNDS)

        connection.execute(
            """
            UPDATE fe_players
            SET skip_used = 1, question_index = ?, answered_current = 0,
                last_correct = NULL, phase_started_at = NULL, lifeline_removed = NULL,
                phase = ?
            WHERE id = ?
            """,
            (next_index, "finished" if finished else "question", player["id"])
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
            or player["question_index"] >= len(ROUNDS)):
        connection.close()
        return jsonify({"error": "unavailable"}), 400

    round_data = ROUNDS[player["question_index"]]

    connection.execute(
        "UPDATE fe_players SET ask_team_used = 1 WHERE id = ?",
        (player["id"],)
    )
    connection.commit()

    rows = connection.execute(
        "SELECT option, count FROM fe_answer_tally WHERE round_number = ?",
        (round_data["round_number"],)
    ).fetchall()
    connection.close()

    tally = {row["option"]: row["count"] for row in rows}
    total = sum(tally.values())
    percentages = {}
    for letter in round_data["options"]:
        votes = tally.get(letter, 0)
        percentages[letter] = round((votes / total) * 100) if total else 0

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

    if not player["answered_current"] or player["question_index"] >= len(ROUNDS):
        connection.close()
        return redirect(url_for("elimination.play", name=name))

    question = ROUNDS[player["question_index"]]
    connection.close()

    return render_template(
        "fe_feedback.html",
        name=name,
        player=player,
        question=question,
        correct=bool(player["last_correct"]),
        points=player["last_points"],
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
    finished = next_index >= len(ROUNDS)

    connection.execute(
        """
        UPDATE fe_players
        SET question_index = ?, answered_current = 0, last_correct = NULL,
            phase_started_at = NULL, lifeline_removed = NULL,
            phase = ?
        WHERE id = ?
        """,
        (next_index, "finished" if finished else "question", player["id"])
    )

    connection.commit()
    connection.close()

    if finished:
        return redirect(url_for("elimination.results", name=name))
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
        question_number=min(player["question_index"] + 1, len(ROUNDS)),
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
        return render_template("fe_winner.html", name=name, player=player, active_nav="play")

    return render_template("fe_results.html", name=name, player=player, active_nav="play")


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


@elimination_bp.route("/leaderboard-data")
def leaderboard_data():
    connection = get_db()
    players = connection.execute(
        "SELECT * FROM fe_players ORDER BY score DESC, name ASC"
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
            "score": p["score"],
            "status": status
        })

    return jsonify({"players": rows})


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

    history_rows = connection.execute(
        """
        SELECT * FROM fe_answer_history
        WHERE player_id = ?
        ORDER BY round_number ASC
        """,
        (player["id"],)
    ).fetchall()
    connection.close()

    rounds_by_number = {r["round_number"]: r for r in ROUNDS}

    reviewed = []
    for row in history_rows:
        round_data = rounds_by_number.get(row["round_number"])
        if round_data is None:
            continue
        reviewed.append({
            "round_number": row["round_number"],
            "difficulty": round_data["difficulty"],
            "text": round_data["text"],
            "options": round_data["options"],
            "correct_answer": round_data["correct"],
            "explanation": round_data["explanation"],
            "player_answer": row["answer"],
            "was_correct": bool(row["correct"]),
            "points": row["points"]
        })

    return render_template(
        "fe_review.html",
        name=name,
        player=player,
        reviewed=reviewed,
        active_nav="play"
    )
