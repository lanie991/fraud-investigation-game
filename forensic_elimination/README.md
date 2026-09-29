# Forensic Elimination

A standalone Kahoot-style, single-elimination fraud trivia game, separate
from "Who Stole the Money?" (the app in the repo root).

## Run it

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

## Questions

Edit `QUESTION_BANK` in `elimination.py`. Every question in each round is
played, in the order listed. After changing questions, restart the app and
press Reset on the Host page.
