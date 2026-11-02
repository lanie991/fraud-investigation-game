"""
What the big screen shows between questions while a round is being played.

Edit freely:
  * CASE_FILES  - real fraud stories shown as a "case file" card.
                  Each needs a title, a short tagline, exactly three facts
                  (big number + small label), a story and a red flag.
                  Use <b>...</b> to make words bold in the story.
  * DID_YOU_KNOW - one-line facts for the yellow strip at the bottom.
  * PRACTICE_QUESTION - a warm-up players can try in the lobby while they
                  wait for the host. It never counts toward their score.

Tip: avoid stories that give away an answer to one of your questions.
(Enron and FTX were removed here because the 2-Day questions ask about them.)
"""

CASE_FILES = [
    {
        "title": "The McDonald's Monopoly Scam",
        "tagline": "USA · 1989–2001 · INSIDE JOB",
        "facts": [
            ("$24M", "IN PRIZES STOLEN"),
            ("12 yrs", "UNDETECTED"),
            ("50+", "PEOPLE CHARGED"),
        ],
        "story": "The man in charge of <b>security</b> for the game pieces secretly "
                 "took the winning ones and handed them to friends and family, who "
                 "\"won\" cars, cash and the $1 million prizes.",
        "red_flag": "The same small circle of people kept winning big. Who checks the checkers?",
    },
    {
        "title": "Fyre Festival",
        "tagline": "THE BAHAMAS · 2017 · INVESTOR FRAUD",
        "facts": [
            ("$26M", "TAKEN FROM INVESTORS"),
            ("6 yrs", "PRISON SENTENCE"),
            ("0", "LUXURY VILLAS BUILT"),
        ],
        "story": "Sold as a luxury music festival on a private island, promoted by "
                 "<b>supermodels and influencers</b>. Guests arrived to disaster-relief "
                 "tents and cheese sandwiches.",
        "red_flag": "Lots of hype, no proof the stages, housing or food actually existed.",
    },
    {
        "title": "Wells Fargo Fake Accounts",
        "tagline": "USA · REVEALED 2016 · SALES PRESSURE",
        "facts": [
            ("3.5M", "POSSIBLE FAKE ACCOUNTS"),
            ("$3B", "SETTLEMENT IN 2020"),
            ("5,300", "EMPLOYEES FIRED"),
        ],
        "story": "Under impossible sales targets, staff opened bank and credit card "
                 "accounts <b>customers never asked for</b>, sometimes moving their "
                 "money around to make them look real.",
        "red_flag": "Targets so high that hitting them honestly was nearly impossible.",
    },
    {
        "title": "Volkswagen \"Dieselgate\"",
        "tagline": "GERMANY · 2015 · EMISSIONS CHEATING",
        "facts": [
            ("11M", "CARS AFFECTED"),
            ("$30B+", "TOTAL COST"),
            ("40x", "OVER THE POLLUTION LIMIT"),
        ],
        "story": "Hidden software spotted when a car was being <b>tested</b> and turned "
                 "the pollution controls on. On the road, the cars polluted far more.",
        "red_flag": "Results that are perfect in the test but never in real life.",
    },
]

DID_YOU_KNOW = [
    "Organisations lose an estimated 5% of their revenue to fraud every year (ACFE).",
    "Tips are the #1 way fraud gets caught, and over half of tips come from employees (ACFE).",
    "The typical fraud runs for about a year before anyone catches it (ACFE).",
    "Most fraudsters have never been in trouble before. It's often the trusted colleague.",
    "Companies with a fraud hotline catch fraud faster and lose less money.",
    "The word \"Ponzi\" comes from Charles Ponzi, who ran a postage-stamp scheme in 1920.",
    "Unexpected lifestyle changes and never taking holidays are classic red flags.",
    "If something looks off, speak up. That's how most frauds are uncovered.",
]


PRACTICE_QUESTION = {
    "text": "Warm-up: which of these is the BEST way to keep a strong password safe?",
    "options": {
        "A": "Write it on a sticky note on your screen",
        "B": "Share it with a trusted colleague",
        "C": "Use a password manager",
        "D": "Use the same password everywhere",
    },
    "correct": "C",
    "explanation": "A password manager keeps long, unique passwords safe, so one leak doesn't unlock everything.",
}
