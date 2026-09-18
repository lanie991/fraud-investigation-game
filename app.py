from importlib import import_module
import sqlite3

flask = import_module("flask")

Flask = flask.Flask
render_template = flask.render_template
redirect = flask.redirect
request = flask.request

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static"
)


DATABASE = "fraud_game.db"

PRE_GAME_SECONDS = 90
ROUND_SECONDS = 300
INTERMISSION_SECONDS = 600

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            id INTEGER PRIMARY KEY,
            current_round INTEGER DEFAULT 0,
            game_status TEXT DEFAULT 'lobby'
        )
    """)

    # Add game start timer to existing databases
    try:
            connection.execute(
                "ALTER TABLE teams ADD COLUMN avatar TEXT DEFAULT '🕵🏽'"
            )
    except sqlite3.OperationalError:
            pass

    # Add intermission timer to existing databases
    try:
        connection.execute(
            "ALTER TABLE game_state ADD COLUMN intermission_until TEXT"
        )
    except sqlite3.OperationalError:
        pass

    try:
        connection.execute(
            "ALTER TABLE game_state ADD COLUMN game_started_at TEXT"
        )
    except sqlite3.OperationalError:
        pass

    connection.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            join_code TEXT UNIQUE NOT NULL,
            total_score INTEGER DEFAULT 0,
            avatar TEXT DEFAULT '🕵🏽'
        )
    """)
    try:
        connection.execute(
        "ALTER TABLE teams ADD COLUMN avatar TEXT DEFAULT '🕵🏽'"
    )
    except sqlite3.OperationalError:
        pass

    connection.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_number INTEGER NOT NULL UNIQUE,
            round_name TEXT NOT NULL,
            points INTEGER NOT NULL,
            status TEXT DEFAULT 'locked'
        )
    """)

    try:
        connection.execute(
            "ALTER TABLE rounds ADD COLUMN started_at TEXT"
        )
    except sqlite3.OperationalError:
        pass

    connection.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            round_id INTEGER NOT NULL,
            answers TEXT,
            score INTEGER DEFAULT 0,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (round_id) REFERENCES rounds(id)
        )
    """)

    existing_game = connection.execute(
        "SELECT id FROM game_state WHERE id = 1"
    ).fetchone()

    if existing_game is None:
        connection.execute("""
            INSERT INTO game_state (id, current_round, game_status)
            VALUES (1, 0, 'lobby')
        """)

    existing_rounds = connection.execute(
        "SELECT COUNT(*) AS count FROM rounds"
    ).fetchone()

    if existing_rounds["count"] == 0:
        rounds = [
            (1, "Initial Lead", 100),
            (2, "Follow the Money", 150),
            (3, "Digital Evidence", 150),
            (4, "The Interview", 200),
            (5, "Who Stole the Money?", 400)
        ]

        connection.executemany("""
            INSERT INTO rounds
            (round_number, round_name, points, status)
            VALUES (?, ?, ?, 'locked')
        """, rounds)

    connection.commit()
    connection.close()


initialize_database()


# HOME PAGE
@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html")


# HOST PAGE
@app.route("/host")
def host():

    connection = get_db()

    # Automatically move the game forward
    advance_game_if_needed(connection)

    game = connection.execute(
        "SELECT * FROM game_state WHERE id = 1"
    ).fetchone()

    rounds = connection.execute(
        "SELECT * FROM rounds ORDER BY round_number"
    ).fetchall()

    connection.close()

    return render_template(
        "host.html",
        game=game,
        rounds=rounds
    )

# =========================================================
# AUTOMATIC GAME PROGRESSION
# =========================================================

ROUND_DURATION_SECONDS = 300
INTERMISSION_SECONDS = 600


def advance_game_if_needed(connection):
    """Advance the game automatically using the requested timers."""
    game = connection.execute(
        "SELECT * FROM game_state WHERE id = 1"
    ).fetchone()
    if game is None:
        return

    # 1:30 countdown before Round 1 and between Rounds 1/2, 3/4, 4/5.
    if game["game_status"] == "countdown":
        if not game["game_started_at"]:
            return
        elapsed = connection.execute(
            "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
            (game["game_started_at"],)
        ).fetchone()
        if elapsed["seconds"] < PRE_GAME_SECONDS:
            return

        next_round = game["current_round"] + 1
        if next_round > 5:
            return

        connection.execute(
            """
            UPDATE rounds
            SET status = 'active', started_at = datetime('now')
            WHERE round_number = ?
            """,
            (next_round,)
        )
        connection.execute(
            """
            UPDATE game_state
            SET current_round = ?, game_status = 'active',
                game_started_at = NULL, intermission_until = NULL
            WHERE id = 1
            """,
            (next_round,)
        )
        connection.commit()
        return

    # 10:00 intermission after Round 2.
    if game["game_status"] == "intermission":
        until = game["intermission_until"]
        if not until:
            return
        ready = connection.execute(
            "SELECT datetime('now') >= ? AS ready", (until,)
        ).fetchone()
        if not ready["ready"]:
            return

        next_round = game["current_round"] + 1
        if next_round > 5:
            return
        connection.execute(
            """
            UPDATE rounds
            SET status = 'active', started_at = datetime('now')
            WHERE round_number = ?
            """,
            (next_round,)
        )
        connection.execute(
            """
            UPDATE game_state
            SET current_round = ?, game_status = 'active',
                game_started_at = NULL, intermission_until = NULL
            WHERE id = 1
            """,
            (next_round,)
        )
        connection.commit()
        return

    # 5:00 question round.
    if game["game_status"] != "active":
        return

    current_round = game["current_round"]
    round_data = connection.execute(
        "SELECT * FROM rounds WHERE round_number = ?",
        (current_round,)
    ).fetchone()
    if round_data is None or not round_data["started_at"]:
        return

    elapsed = connection.execute(
        "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
        (round_data["started_at"],)
    ).fetchone()
    if elapsed["seconds"] < ROUND_DURATION_SECONDS:
        return

    connection.execute(
        "UPDATE rounds SET status = 'closed' WHERE round_number = ?",
        (current_round,)
    )

    # Round 2 -> 10 minute intermission.
    if current_round == 2:
        connection.execute(
            """
            UPDATE game_state
            SET game_status = 'intermission',
                game_started_at = datetime('now'),
                intermission_until = datetime('now', '+10 minutes')
            WHERE id = 1
            """
        )
        connection.commit()
        return

    # Round 5 -> final results.
    if current_round == 5:
        connection.execute(
            "UPDATE game_state SET game_status = 'finished' WHERE id = 1"
        )
        connection.commit()
        return

    # Round 1, 3, 4 -> 1:30 countdown before next round.
    connection.execute(
        """
        UPDATE game_state
        SET game_status = 'countdown',
            game_started_at = datetime('now'),
            intermission_until = NULL
        WHERE id = 1
        """
    )
    connection.commit()


# Compatibility name used by the waiting route.
def advance_game(connection):
    return advance_game_if_needed(connection)

# =========================================================
# START GAME
# =========================================================

@app.route("/host/start-game", methods=["POST"])
def start_game():

    connection = get_db()

    # Lock all rounds
    connection.execute(
        "UPDATE rounds SET status = 'locked'"
    )

    # Start the 1:30 pre-game countdown
    connection.execute(
        """
        UPDATE game_state
        SET current_round = 0,
            game_status = 'countdown',
            game_started_at = datetime('now')
        WHERE id = 1
        """
    )

    connection.commit()
    connection.close()

    return redirect("/host")

# =========================================================
# RESET GAME / START FRESH GAME
# =========================================================

@app.route("/host/reset-game", methods=["POST"])
def reset_game():

    connection = get_db()

    # Remove all previous game submissions
    connection.execute(
        "DELETE FROM submissions"
    )

    # Remove all previous teams
    # This makes the next game a completely fresh game
    connection.execute(
        "DELETE FROM teams"
    )

    # Reset game state
    connection.execute(
        """
        UPDATE game_state
        SET current_round = 0,
            game_status = 'lobby'
        WHERE id = 1
        """
    )

    # Lock all rounds again
    connection.execute(
        """
        UPDATE rounds
        SET status = 'locked'
        """
    )

    connection.commit()
    connection.close()

    return redirect("/host")

# ROUTE TO UNLOCK NEXT ROUND
@app.route("/host/unlock-round/<int:round_number>", methods=["POST"])
def unlock_round(round_number):

    connection = get_db()

    connection.execute(
        """
        UPDATE rounds
        SET status = 'ready'
        WHERE round_number = ?
        """,
        (round_number,)
    )

    connection.commit()
    connection.close()

    return redirect("/host")


# JOIN PAGE
@app.route("/join", methods=["GET", "POST"])
def join():

    if request.method == "POST":

        team_name = request.form["team_name"].strip()
        game_code = request.form["game_code"].strip().upper()

        connection = get_db()

        avatar = request.form.get("avatar", "detective_black").strip()

        # The current database schema does not contain game_code.
        # Keep the join working without querying a nonexistent column.
        connection.execute(
    """
    INSERT INTO teams (team_name, join_code, avatar)
    VALUES (?, ?, ?)
    """,
    (team_name, game_code, avatar)
)
        game = connection.execute(
            "SELECT * FROM game_state WHERE id = 1"
        ).fetchone()

        if game["game_status"] == "lobby" and game["current_round"] == 0:
            connection.execute(
                """
                UPDATE game_state
                SET game_status = 'countdown',
                    game_started_at = datetime('now'),
                    intermission_until = NULL
                WHERE id = 1
                """
            )

        connection.commit()
        connection.close()

        return redirect(f"/waiting/{team_name}")

    return render_template("join.html")


# PLAYER WAITING / GAME STATUS
@app.route("/player/waiting-status/<team_name>")
def player_waiting_status(team_name):
    connection = get_db()

    # This endpoint is what keeps the player waiting page alive and
    # advances the game without requiring the host to click anything.
    advance_game_if_needed(connection)

    game = connection.execute(
        "SELECT * FROM game_state WHERE id = 1"
    ).fetchone()

    remaining = 0

    if game["game_status"] == "countdown" and game["game_started_at"]:
        row = connection.execute(
            "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
            (game["game_started_at"],)
        ).fetchone()
        remaining = max(0, int(PRE_GAME_SECONDS - row["seconds"]))

    elif game["game_status"] == "intermission" and game["intermission_until"]:
        row = connection.execute(
            "SELECT (julianday(?) - julianday('now')) * 86400 AS seconds",
            (game["intermission_until"],)
        ).fetchone()
        remaining = max(0, int(row["seconds"]))

    elif game["game_status"] == "active" and game["current_round"] > 0:
        round_data = connection.execute(
            "SELECT started_at FROM rounds WHERE round_number = ?",
            (game["current_round"],)
        ).fetchone()

        if round_data and round_data["started_at"]:
            row = connection.execute(
                "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
                (round_data["started_at"],)
            ).fetchone()
            remaining = max(0, int(ROUND_DURATION_SECONDS - row["seconds"]))

    current_status = game["game_status"]
    current_round = game["current_round"]
    connection.close()

    return {
        "game_status": current_status,
        "current_round": current_round,
        "remaining_seconds": remaining,
        "team_name": team_name
    }


# WAITING PAGE
@app.route("/waiting/<team_name>")
def waiting(team_name):

    connection = get_db()

    from_round = request.args.get("from_round", type=int)
    timed_out = request.args.get("timed_out", type=int) == 1

    # -------------------------------------------------
    # If the player just completed/timed out of a round,
    # move the game into the correct next phase first.
    # -------------------------------------------------
    if from_round is not None:
        game = connection.execute(
            "SELECT * FROM game_state WHERE id = 1"
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE team_name = ?",
            (team_name,)
        ).fetchone()

        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (from_round,)
        ).fetchone()

        if game is not None and round_data is not None and game["current_round"] == from_round and game["game_status"] == "active":
            has_submission = False
            if team is not None:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM submissions
                    WHERE team_id = ? AND round_id = ?
                    LIMIT 1
                    """,
                    (team["id"], round_data["id"])
                ).fetchone()
                has_submission = row is not None

            # A normal submission or an explicit client timeout means
            # this team's round is finished and the next timer must start.
            if has_submission or timed_out:
                connection.execute(
                    "UPDATE rounds SET status = 'closed' WHERE round_number = ?",
                    (from_round,)
                )

                if from_round == 2:
                    connection.execute(
                        """
                        UPDATE game_state
                        SET game_status = 'intermission',
                            game_started_at = NULL,
                            intermission_until = datetime('now', '+10 minutes')
                        WHERE id = 1
                        """
                    )
                elif from_round == 5:
                    connection.execute(
                        """
                        UPDATE game_state
                        SET game_status = 'finished',
                            game_started_at = NULL,
                            intermission_until = NULL
                        WHERE id = 1
                        """
                    )
                else:
                    connection.execute(
                        """
                        UPDATE game_state
                        SET game_status = 'countdown',
                            game_started_at = datetime('now'),
                            intermission_until = NULL
                        WHERE id = 1
                        """
                    )

                connection.commit()

    # Always advance any countdown/intermission that has reached zero.
    advance_game_if_needed(connection)

    game = connection.execute(
        "SELECT * FROM game_state WHERE id = 1"
    ).fetchone()

    round_score = 0
    round_points = 0
    answers = {}

    # -------------------------------------------------
    # LOAD RESULTS FOR THE ROUND JUST COMPLETED
    # -------------------------------------------------
    if from_round is not None:
        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (from_round,)
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE team_name = ?",
            (team_name,)
        ).fetchone()

        if round_data is not None:
            round_points = round_data["points"]

        if team is not None and round_data is not None:
            submission = connection.execute(
                """
                SELECT score, answers
                FROM submissions
                WHERE team_id = ? AND round_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (team["id"], round_data["id"])
            ).fetchone()

            if submission is not None:
                round_score = submission["score"]
                if submission["answers"]:
                    for answer in submission["answers"].split(";"):
                        if "=" in answer:
                            question, value = answer.split("=", 1)
                            answers[question] = value

    # -------------------------------------------------
    # IF NEXT ROUND IS ALREADY ACTIVE, GO THERE.
    # -------------------------------------------------
    if from_round is not None and game["game_status"] == "active" and game["current_round"] > from_round:
        connection.close()
        return redirect(
            f"/player/round/{game['current_round']}/{team_name}"
        )

    # If no prior round and Round 1 is active, enter it.
    if from_round is None and game["game_status"] == "active" and game["current_round"] == 1:
        connection.close()
        return redirect(f"/player/round/1/{team_name}")

    connection.close()

    return render_template(
        "waiting.html",
        team_name=team_name,
        from_round=from_round,
        timed_out=timed_out,
        round_score=round_score,
        round_points=round_points,
        answers=answers,
        game_status=game["game_status"],
        game_started_at=game["game_started_at"],
        intermission_until=game["intermission_until"],
        current_round=game["current_round"]
    )

# PLAYER ROUND PAGE
@app.route("/player/round/<int:round_number>/<team_name>", methods=["GET", "POST"])
def player_round(round_number, team_name):

    # -------------------------
    # ROUND 1 SUBMISSION
    # -------------------------

    if request.method == "POST" and round_number == 1:

        q1 = request.form.get("q1")
        q2 = request.form.get("q2")
        q3 = request.form.get("q3")

        score = 0

        if q1 == "invoice_after_payment":
            score += 34

        if q2 == "hold_vs_proceed":
            score += 33

        if q3 == "identifies_reviewer":
            score += 33

        connection = get_db()

        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (round_number,)
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE team_name = ?",
            (team_name,)
        ).fetchone()

        connection.execute(
            """
            INSERT INTO submissions
            (team_id, round_id, answers, score)
            VALUES (?, ?, ?, ?)
            """,
            (
                team["id"],
                round_data["id"],
                f"q1={q1};q2={q2};q3={q3}",
                score
            )
        )

        connection.execute(
            """
            UPDATE teams
            SET total_score = total_score + ?
            WHERE id = ?
            """,
            (score, team["id"])
        )

        connection.commit()
        connection.close()

        return redirect(
    f"/waiting/{team_name}?from_round={round_number}"
)

    # -------------------------
    # ROUND 2 SUBMISSION
    # -------------------------

    if request.method == "POST" and round_number == 2:

        q1 = request.form.get("q1")
        q2 = request.form.get("q2")
        q3 = request.form.get("q3")
        q4 = request.form.get("q4")

        score = 0

        if q1 == "money_circular":
            score += 38

        if q2 == "transaction3":
            score += 37

        if q3 == "layering":
            score += 38

        if q4 == "carter_advisory":
            score += 37

        connection = get_db()

        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (round_number,)
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE team_name = ?",
            (team_name,)
        ).fetchone()

        connection.execute(
            """
            INSERT INTO submissions
            (team_id, round_id, answers, score)
            VALUES (?, ?, ?, ?)
            """,
            (
                team["id"],
                round_data["id"],
                f"q1={q1};q2={q2};q3={q3};q4={q4}",
                score
            )
        )

        connection.execute(
            """
            UPDATE teams
            SET total_score = total_score + ?
            WHERE id = ?
            """,
            (score, team["id"])
        )

        connection.commit()
        connection.close()

        return redirect(
            f"/waiting/{team_name}?from_round={round_number}"
        )

    # -------------------------
    # ROUND 3 SUBMISSION
    # -------------------------

    if request.method == "POST" and round_number == 3:

        q1 = request.form.get("q1")
        q2 = request.form.get("q2")
        q3 = request.form.get("q3")
        q4 = request.form.get("q4")

        score = 0

        if q1 == "login_location":
            score += 38

        if q2 == "payment_user":
            score += 37

        if q3 == "created_before_payment":
            score += 38

        if q4 == "investigation_timeline":
            score += 37

        connection = get_db()

        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (round_number,)
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE team_name = ?",
            (team_name,)
        ).fetchone()

        connection.execute(
            """
            INSERT INTO submissions
            (team_id, round_id, answers, score)
            VALUES (?, ?, ?, ?)
            """,
            (
                team["id"],
                round_data["id"],
                f"q1={q1};q2={q2};q3={q3};q4={q4}",
                score
            )
        )

        connection.execute(
            """
            UPDATE teams
            SET total_score = total_score + ?
            WHERE id = ?
            """,
            (score, team["id"])
        )

        connection.commit()
        connection.close()

        return redirect(
    f"/waiting/{team_name}?from_round={round_number}"
)


    # -------------------------
    # ROUND 4 SUBMISSION
    # -------------------------

    if request.method == "POST" and round_number == 4:

        q1 = request.form.get("q1")
        q2 = request.form.get("q2")
        q3 = request.form.get("q3")
        q4 = request.form.get("q4")

        score = 0

        if q1 == "denied_payment":
            score += 50

        if q2 == "overseas":
            score += 50

        if q3 == "login":
            score += 50

        if q4 == "multiple_conflicts":
            score += 50

        connection = get_db()

        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (round_number,)
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE team_name = ?",
            (team_name,)
        ).fetchone()

        connection.execute(
            """
            INSERT INTO submissions
            (team_id, round_id, answers, score)
            VALUES (?, ?, ?, ?)
            """,
            (
                team["id"],
                round_data["id"],
                f"q1={q1};q2={q2};q3={q3};q4={q4}",
                score
            )
        )

        connection.execute(
            """
            UPDATE teams
            SET total_score = total_score + ?
            WHERE id = ?
            """,
            (score, team["id"])
        )

        connection.commit()
        connection.close()

        return redirect(
    f"/waiting/{team_name}?from_round={round_number}"
)


    # -------------------------
    # ROUND 5 SUBMISSION
    # -------------------------

    if request.method == "POST" and round_number == 5:

        q1 = request.form.get("q1")
        q2 = request.form.get("q2")
        q3 = request.form.get("q3")
        q4 = request.form.get("q4")
        q5 = request.form.get("q5")

        score = 0

        # Q1 — Sarah's access is relevant but not proof of authorization
        if q1 == "relevant_not_proof":
            score += 70

        # Q2 — The payment authorization log distinguishes the authorizer
        if q2 == "payment_authorization_log":
            score += 70

        # Q3 — MCARTER login/activity logs contradict the laptop claim
        if q3 == "mcarter_login_logs":
            score += 70

        # Q4 — Correct chronological sequence
        if q4 == "timeline":
            score += 70

        # Q5 — Final verdict: Michael Carter
        if q5 == "michael":
            score += 120


        # -------------------------
        # SAVE ROUND 5 SUBMISSION
        # -------------------------

        connection = get_db()

        round_data = connection.execute(
            """
            SELECT *
            FROM rounds
            WHERE round_number = ?
            """,
            (round_number,)
        ).fetchone()

        team = connection.execute(
            """
            SELECT *
            FROM teams
            WHERE team_name = ?
            """,
            (team_name,)
        ).fetchone()


        if round_data is None:
            connection.close()
            return "Round 5 not found.", 404


        if team is None:
            connection.close()
            return "Team not found.", 404


        connection.execute(
            """
            INSERT INTO submissions
            (team_id, round_id, answers, score)
            VALUES (?, ?, ?, ?)
            """,
            (
                team["id"],
                round_data["id"],
                (
                    f"q1={q1};"
                    f"q2={q2};"
                    f"q3={q3};"
                    f"q4={q4};"
                    f"q5={q5}"
                ),
                score
            )
        )


        connection.execute(
            """
            UPDATE teams
            SET total_score = total_score + ?
            WHERE id = ?
            """,
            (score, team["id"])
        )


        connection.commit()
        connection.close()


        # -------------------------
        # SEND PLAYER TO WAITING PAGE
        # -------------------------

        return redirect(
    f"/waiting/{team_name}?from_round={round_number}"
)

    # -------------------------
    # LOAD ACTIVE ROUND
    # -------------------------

    connection = get_db()

    game = connection.execute(
        "SELECT * FROM game_state WHERE id = 1"
    ).fetchone()

    round_data = connection.execute(
        """
        SELECT *
        FROM rounds
        WHERE round_number = ?
        """,
        (round_number,)
    ).fetchone()

    connection.close()


    if round_data is None:
        return "Round not found.", 404


    # Host has not activated this round yet.
    # The waiting page will poll the status endpoint.
    if game["current_round"] < round_number:
        return render_template(
            "waiting.html",
            team_name=team_name,
            round_number=round_number
        )


    # Do not allow a player to go backward into an already completed round.
    if game["current_round"] > round_number:
        return "This round has already been completed.", 403


    # -------------------------
    # LOAD ACTUAL QUESTIONS
    # -------------------------

    if round_number == 1:
        return render_template(
            "round1.html",
            team_name=team_name,
            round_data=round_data
        )

    if round_number == 2:
        return render_template(
            "round2.html",
            team_name=team_name,
            round_data=round_data
        )

    if round_number == 3:
        return render_template(
            "round3.html",
            team_name=team_name,
            round_data=round_data
        )

    if round_number == 4:
        return render_template(
            "round4.html",
            team_name=team_name,
            round_data=round_data
        )

    if round_number == 5:
        return render_template(
            "round5.html",
            team_name=team_name,
            round_data=round_data
        )

    return "Round not built yet.", 404


# ROUND RESULTS
@app.route("/host/results/<int:round_number>")
def round_results(round_number):

    connection = get_db()

    round_data = connection.execute(
        "SELECT * FROM rounds WHERE round_number = ?",
        (round_number,)
    ).fetchone()

    if round_data is None:
        connection.close()
        return "Round not found.", 404

    results = connection.execute(
        """
        SELECT
            teams.team_name,
            submissions.score
        FROM submissions
        JOIN teams
            ON submissions.team_id = teams.id
        WHERE submissions.round_id = ?
        ORDER BY submissions.score DESC
        """,
        (round_data["id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "round_results.html",
        round_data=round_data,
        results=results
    )

# =========================
# FINAL LEADERBOARD
# =========================

@app.route("/host/final_results")
def final_results():
    connection = get_db()

    results = connection.execute(
        """
        SELECT
            team_name,
            total_score,
            avatar
        FROM teams
        ORDER BY total_score DESC, team_name ASC
        """
    ).fetchall()

    connection.close()

    return render_template(
        "final_results.html",
        results=results
    )

# PLAYER ROUND TIMER
@app.route("/player/round-time/<int:round_number>")
def round_time(round_number):

    connection = get_db()

    round_data = connection.execute(
        "SELECT started_at, status FROM rounds WHERE round_number = ?",
        (round_number,)
    ).fetchone()

    remaining = 0

    if round_data and round_data["started_at"]:
        row = connection.execute(
            "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
            (round_data["started_at"],)
        ).fetchone()
        remaining = max(0, int(ROUND_DURATION_SECONDS - row["seconds"]))

    closed = round_data["status"] == "closed" if round_data else False

    connection.close()

    return {
        "remaining_seconds": remaining,
        "closed": closed
    }


# PLAYER ROUND STATUS CHECK
@app.route("/player/check-round/<int:round_number>/<team_name>")
def check_round(round_number, team_name):

    connection = get_db()

    game = connection.execute(
        """
        SELECT *
        FROM game_state
        WHERE id = 1
        """
    ).fetchone()

    round_data = connection.execute(
        """
        SELECT *
        FROM rounds
        WHERE round_number = ?
        """,
        (round_number,)
    ).fetchone()

    team = connection.execute(
        """
        SELECT *
        FROM teams
        WHERE team_name = ?
        """,
        (team_name,)
    ).fetchone()


    if round_data is None or team is None:
        connection.close()
        return {
            "active": False,
            "closed": False
        }


    active = game["current_round"] >= round_number


    submission = connection.execute(
    """
    SELECT score, answers
    FROM submissions
    WHERE team_id = ?
    AND round_id = ?
    ORDER BY id DESC
    LIMIT 1
    """,
    (
        team["id"],
        round_data["id"]
    )
).fetchone()

    connection.close()


    # Round is still open.
    if round_data["status"] != "closed":
        return {
            "active": active,
            "closed": False
        }


    # Round is closed but this team did not submit.
    if submission is None:
        return {
            "active": active,
            "closed": True,
            "score": 0,
            "points": round_data["points"],
            "next_round": None
        }


    next_round = None

    if round_number < 5:
        next_round = round_number + 1

    return {
        "active": active,
        "closed": True,
        "score": submission["score"],
        "points": round_data["points"],
        "next_round": next_round
    }


# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)