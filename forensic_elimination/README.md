# Forensic Elimination

A standalone Kahoot-style, single-elimination fraud trivia game. It is a
separate app from "Who Stole the Money?" (the app in the repo root) and has
its own templates, static files and database (`elimination_game.db`).

## Run it

```
cd forensic_elimination
pip install -r requirements.txt
python app.py
```

It runs on http://127.0.0.1:5001 so it can run at the same time as
"Who Stole the Money?" (which uses port 5000).

- Home: `/`
- Host screen: `/host`
- Players join: `/join`
- Big-screen display: `/display`

To deploy with gunicorn: `gunicorn app:app` from inside this folder.
