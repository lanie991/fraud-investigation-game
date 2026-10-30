# Fraud Files: 2-Day Challenge

A copy of the Fraud Files game (`../forensic_elimination`) with two rounds
of 10 mixed-difficulty questions, played on two different days.

* Questions: `QUESTION_BANK` in `elimination.py` (round 1 and round 2,
  10 each; set `"difficulty"` on every question).
* Case files and "Did you know?" facts: `big_screen_content.py`.
* Day 1: players join, play Round 1. Do **not** press Reset afterwards.
* Day 2: players rejoin with the same name and PIN; the host presses
  START ROUND 2. Scores from both days are added together.

On Render the game's data is copied to the free Postgres database set up
in `render.yaml` (`DATABASE_URL`), so scores survive the free web
service restarting or sleeping overnight (`db_store.py`). Run locally with
`pip install -r requirements.txt` then `python app.py`; without
`DATABASE_URL` it just uses the local SQLite file.
