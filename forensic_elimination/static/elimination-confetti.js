window.FE_CONFETTI = (function () {

    var COLORS = ["#facc15", "#f97316", "#ef4444", "#22d3ee", "#a78bfa", "#4ade80", "#f8fafc"];

    function burst(durationMs) {
        durationMs = durationMs || 4000;

        var canvas = document.createElement("canvas");
        canvas.style.position = "fixed";
        canvas.style.top = "0";
        canvas.style.left = "0";
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        canvas.style.zIndex = "999";
        canvas.style.pointerEvents = "none";
        document.body.appendChild(canvas);

        var ctx = canvas.getContext("2d");
        var dpr = window.devicePixelRatio || 1;

        function resize() {
            canvas.width = window.innerWidth * dpr;
            canvas.height = window.innerHeight * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }
        resize();
        window.addEventListener("resize", resize);

        var pieceCount = 140;
        var pieces = [];
        for (var i = 0; i < pieceCount; i++) {
            pieces.push({
                x: Math.random() * window.innerWidth,
                y: -20 - Math.random() * window.innerHeight * 0.5,
                w: 6 + Math.random() * 6,
                h: 8 + Math.random() * 10,
                color: COLORS[Math.floor(Math.random() * COLORS.length)],
                rotation: Math.random() * Math.PI * 2,
                rotationSpeed: (Math.random() - 0.5) * 0.3,
                vy: 2 + Math.random() * 3,
                vx: (Math.random() - 0.5) * 2,
                sway: Math.random() * Math.PI * 2,
                swaySpeed: 0.02 + Math.random() * 0.02
            });
        }

        var startTime = performance.now();
        var fadeStart = durationMs - 800;
        var rafId = null;

        function frame(now) {
            var elapsed = now - startTime;
            ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

            var opacity = elapsed > fadeStart
                ? Math.max(0, 1 - (elapsed - fadeStart) / 800)
                : 1;

            pieces.forEach(function (p) {
                p.y += p.vy;
                p.sway += p.swaySpeed;
                p.x += p.vx + Math.sin(p.sway) * 1.2;
                p.rotation += p.rotationSpeed;

                ctx.save();
                ctx.globalAlpha = opacity;
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rotation);
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
                ctx.restore();
            });

            if (elapsed < durationMs) {
                rafId = requestAnimationFrame(frame);
            } else {
                window.removeEventListener("resize", resize);
                canvas.remove();
            }
        }

        rafId = requestAnimationFrame(frame);
    }

    return { burst: burst };
})();
