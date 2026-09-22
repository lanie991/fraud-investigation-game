/* =========================================================
   FORENSIC ELIMINATION -- LIVE SPECTATOR STANDINGS
   Polls the leaderboard for players who are no longer actively
   playing (eliminated, or finished and waiting on others).
========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const board = document.getElementById("fe-spectate-board");
    if (!board) return;

    function statusClass(status) {
        if (status === "ELIMINATED") return "eliminated";
        if (status === "WINNER") return "winner";
        return "in";
    }

    function render(players) {
        if (!players.length) {
            board.innerHTML = '<div class="fe-player-empty">No investigators have joined yet.</div>';
            return;
        }

        let html = "";
        players.forEach(function (p, index) {
            const avatarImg = p.avatar
                ? '<img src="/static/avatars/' + p.avatar + '" alt="">'
                : "";

            html += '<div class="fe-leaderboard-row">'
                + '<div class="fe-leaderboard-rank">' + (index + 1) + "</div>"
                + '<div class="fe-player-avatar">' + avatarImg + "</div>"
                + '<div class="fe-leaderboard-name">' + p.name + "</div>"
                + '<div class="fe-leaderboard-score">' + p.score + "</div>"
                + '<span class="fe-status-pill ' + statusClass(p.status) + '">' + p.status + "</span>"
                + "</div>";
        });

        board.innerHTML = html;
    }

    function poll() {
        fetch("/elimination/leaderboard-data", { cache: "no-store" })
            .then(function (r) { return r.json(); })
            .then(function (data) { render(data.players || []); })
            .catch(function () {});
    }

    poll();
    setInterval(poll, 3000);
});
