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
ROUND_DURATION_SECONDS = 300
INTERMISSION_SECONDS = 600

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            join_code TEXT NOT NULL,
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

    # Per-team round progression -- each team runs its own independent
    # round, timer and intermission instead of sharing one global
    # clock with every other team. This means a team that joins while
    # others are already on Round 3 still starts fresh at Round 1, and
    # nothing advances for anyone until a team actually exists.
    try:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN current_round INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    try:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN team_status TEXT DEFAULT 'lobby'"
        )
    except sqlite3.OperationalError:
        pass

    try:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN phase_started_at TEXT"
        )
    except sqlite3.OperationalError:
        pass

    try:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN intermission_until TEXT"
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

    teams = connection.execute(
        "SELECT * FROM teams ORDER BY team_name"
    ).fetchall()

    for team in teams:
        advance_team_if_needed(connection, team["id"])

    teams = connection.execute(
        "SELECT * FROM teams ORDER BY team_name"
    ).fetchall()

    connection.close()

    return render_template(
        "host.html",
        teams=teams
    )

# =========================================================
# AUTOMATIC GAME PROGRESSION (PER TEAM)
# =========================================================


def advance_team_if_needed(connection, team_id):
    """Advance a single team's own round and timer automatically."""
    team = connection.execute(
        "SELECT * FROM teams WHERE id = ?",
        (team_id,)
    ).fetchone()
    if team is None:
        return

    # 1:30 countdown before Round 1 and between Rounds 1/2, 3/4, 4/5.
    if team["team_status"] == "countdown":
        if not team["phase_started_at"]:
            return
        elapsed = connection.execute(
            "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
            (team["phase_started_at"],)
        ).fetchone()
        if elapsed["seconds"] < PRE_GAME_SECONDS:
            return

        next_round = team["current_round"] + 1
        if next_round > 5:
            return

        connection.execute(
            """
            UPDATE teams
            SET current_round = ?, team_status = 'active',
                phase_started_at = datetime('now'), intermission_until = NULL
            WHERE id = ?
            """,
            (next_round, team_id)
        )
        connection.commit()
        return

    # 10:00 intermission after Round 2.
    if team["team_status"] == "intermission":
        until = team["intermission_until"]
        if not until:
            return
        ready = connection.execute(
            "SELECT datetime('now') >= ? AS ready", (until,)
        ).fetchone()
        if not ready["ready"]:
            return

        next_round = team["current_round"] + 1
        if next_round > 5:
            return
        connection.execute(
            """
            UPDATE teams
            SET current_round = ?, team_status = 'active',
                phase_started_at = datetime('now'), intermission_until = NULL
            WHERE id = ?
            """,
            (next_round, team_id)
        )
        connection.commit()
        return

    # 5:00 question round.
    if team["team_status"] != "active":
        return

    if not team["phase_started_at"]:
        return

    elapsed = connection.execute(
        "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
        (team["phase_started_at"],)
    ).fetchone()
    if elapsed["seconds"] < ROUND_DURATION_SECONDS:
        return

    current_round = team["current_round"]

    # Round 2 -> 10 minute intermission.
    if current_round == 2:
        connection.execute(
            """
            UPDATE teams
            SET team_status = 'intermission',
                phase_started_at = NULL,
                intermission_until = datetime('now', '+10 minutes')
            WHERE id = ?
            """,
            (team_id,)
        )
        connection.commit()
        return

    # Round 5 -> final results.
    if current_round == 5:
        connection.execute(
            """
            UPDATE teams
            SET team_status = 'finished', phase_started_at = NULL
            WHERE id = ?
            """,
            (team_id,)
        )
        connection.commit()
        return

    # Round 1, 3, 4 -> 1:30 countdown before next round.
    connection.execute(
        """
        UPDATE teams
        SET team_status = 'countdown',
            phase_started_at = datetime('now'),
            intermission_until = NULL
        WHERE id = ?
        """,
        (team_id,)
    )
    connection.commit()

# =========================================================
# RESET GAME / START FRESH GAME
# =========================================================

@app.route("/host/reset-game", methods=["POST"])
def reset_game():

    connection = get_db()

    # Removing every team and submission is the entire reset, since
    # each team's round progression now lives on its own row.
    connection.execute(
        "DELETE FROM submissions"
    )

    connection.execute(
        "DELETE FROM teams"
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

        # Every team starts its own independent 1:30 pre-game
        # countdown the moment it joins, regardless of what round any
        # other team is currently on.
        connection.execute(
            """
            INSERT INTO teams
            (team_name, join_code, avatar, current_round, team_status, phase_started_at)
            VALUES (?, ?, ?, 0, 'countdown', datetime('now'))
            """,
            (team_name, game_code, avatar)
        )

        connection.commit()
        connection.close()

        return redirect(f"/waiting/{team_name}")

    return render_template("join.html")


# PLAYER WAITING / GAME STATUS
@app.route("/player/waiting-status/<team_name>")
def player_waiting_status(team_name):
    connection = get_db()

    team = connection.execute(
        "SELECT * FROM teams WHERE team_name = ?",
        (team_name,)
    ).fetchone()

    if team is None:
        connection.close()
        return {
            "game_status": "lobby",
            "current_round": 0,
            "remaining_seconds": 0,
            "team_name": team_name
        }

    # This endpoint is what keeps the player waiting page alive and
    # advances this team's own game without requiring the host to
    # click anything.
    advance_team_if_needed(connection, team["id"])

    team = connection.execute(
        "SELECT * FROM teams WHERE id = ?",
        (team["id"],)
    ).fetchone()

    remaining = 0

    if team["team_status"] == "countdown" and team["phase_started_at"]:
        row = connection.execute(
            "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
            (team["phase_started_at"],)
        ).fetchone()
        remaining = max(0, int(PRE_GAME_SECONDS - row["seconds"]))

    elif team["team_status"] == "intermission" and team["intermission_until"]:
        row = connection.execute(
            "SELECT (julianday(?) - julianday('now')) * 86400 AS seconds",
            (team["intermission_until"],)
        ).fetchone()
        remaining = max(0, int(row["seconds"]))

    elif team["team_status"] == "active" and team["current_round"] > 0:
        if team["phase_started_at"]:
            row = connection.execute(
                "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
                (team["phase_started_at"],)
            ).fetchone()
            remaining = max(0, int(ROUND_DURATION_SECONDS - row["seconds"]))

    current_status = team["team_status"]
    current_round = team["current_round"]
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

    team = connection.execute(
        "SELECT * FROM teams WHERE team_name = ?",
        (team_name,)
    ).fetchone()

    if team is None:
        connection.close()
        return redirect("/join")

    # -------------------------------------------------
    # If the player just completed/timed out of a round,
    # move this team into the correct next phase first.
    # -------------------------------------------------
    if from_round is not None:
        round_data = connection.execute(
            "SELECT * FROM rounds WHERE round_number = ?",
            (from_round,)
        ).fetchone()

        if round_data is not None and team["current_round"] == from_round and team["team_status"] == "active":
            has_submission = connection.execute(
                """
                SELECT 1
                FROM submissions
                WHERE team_id = ? AND round_id = ?
                LIMIT 1
                """,
                (team["id"], round_data["id"])
            ).fetchone() is not None

            # A normal submission or an explicit client timeout means
            # this team's round is finished and the next timer must start.
            if has_submission or timed_out:
                if from_round == 2:
                    connection.execute(
                        """
                        UPDATE teams
                        SET team_status = 'intermission',
                            phase_started_at = NULL,
                            intermission_until = datetime('now', '+10 minutes')
                        WHERE id = ?
                        """,
                        (team["id"],)
                    )
                elif from_round == 5:
                    connection.execute(
                        """
                        UPDATE teams
                        SET team_status = 'finished',
                            phase_started_at = NULL,
                            intermission_until = NULL
                        WHERE id = ?
                        """,
                        (team["id"],)
                    )
                else:
                    connection.execute(
                        """
                        UPDATE teams
                        SET team_status = 'countdown',
                            phase_started_at = datetime('now'),
                            intermission_until = NULL
                        WHERE id = ?
                        """,
                        (team["id"],)
                    )

                connection.commit()

    # Always advance any countdown/intermission that has reached zero.
    advance_team_if_needed(connection, team["id"])

    team = connection.execute(
        "SELECT * FROM teams WHERE id = ?",
        (team["id"],)
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

        if round_data is not None:
            round_points = round_data["points"]

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
    if from_round is not None and team["team_status"] == "active" and team["current_round"] > from_round:
        connection.close()
        return redirect(
            f"/player/round/{team['current_round']}/{team_name}"
        )

    # If no prior round and Round 1 is active, enter it.
    if from_round is None and team["team_status"] == "active" and team["current_round"] == 1:
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
        game_status=team["team_status"],
        game_started_at=team["phase_started_at"],
        intermission_until=team["intermission_until"],
        current_round=team["current_round"]
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

    team = connection.execute(
        "SELECT * FROM teams WHERE team_name = ?",
        (team_name,)
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


    if team is None:
        return redirect("/join")


    # This team has not reached this round yet.
    # The waiting page will poll the status endpoint.
    if team["current_round"] < round_number:
        return render_template(
            "waiting.html",
            team_name=team_name,
            round_number=round_number
        )


    # Do not allow a player to go backward into an already completed round.
    if team["current_round"] > round_number:
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
@app.route("/player/round-time/<int:round_number>/<team_name>")
def round_time(round_number, team_name):

    connection = get_db()

    team = connection.execute(
        "SELECT * FROM teams WHERE team_name = ?",
        (team_name,)
    ).fetchone()

    if team is None:
        connection.close()
        return {"remaining_seconds": 0, "closed": True}

    advance_team_if_needed(connection, team["id"])

    team = connection.execute(
        "SELECT * FROM teams WHERE id = ?",
        (team["id"],)
    ).fetchone()

    remaining = 0
    closed = True

    if team["current_round"] == round_number and team["team_status"] == "active":
        if team["phase_started_at"]:
            row = connection.execute(
                "SELECT (julianday('now') - julianday(?)) * 86400 AS seconds",
                (team["phase_started_at"],)
            ).fetchone()
            remaining = max(0, int(ROUND_DURATION_SECONDS - row["seconds"]))
        closed = False

    connection.close()

    return {
        "remaining_seconds": remaining,
        "closed": closed
    }


# PLAYER ROUND STATUS CHECK
@app.route("/player/check-round/<int:round_number>/<team_name>")
def check_round(round_number, team_name):

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


    if round_data is None or team is None:
        connection.close()
        return {
            "active": False,
            "closed": False
        }


    active = team["current_round"] >= round_number

    closed = team["current_round"] > round_number or (
        team["current_round"] == round_number and team["team_status"] != "active"
    )

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


    # Round is still open for this team.
    if not closed:
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
