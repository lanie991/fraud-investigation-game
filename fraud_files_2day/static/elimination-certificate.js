/* Draws the player's certificate on a canvas and saves it as a PNG. */
(function () {
    const btn = document.getElementById("fe-cert-btn");
    if (!btn) return;
    const cert = JSON.parse(btn.dataset.cert);

    function loadImage(src) {
        return new Promise(function (resolve) {
            if (!src) return resolve(null);
            const img = new Image();
            img.onload = function () { resolve(img); };
            img.onerror = function () { resolve(null); };
            img.src = src;
        });
    }

    function fitText(ctx, text, maxWidth, size, weight, family) {
        let s = size;
        do {
            ctx.font = weight + " " + s + "px " + family;
            s -= 2;
        } while (ctx.measureText(text).width > maxWidth && s > 20);
    }

    async function draw() {
        const W = 1600, H = 1131;
        const canvas = document.createElement("canvas");
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext("2d");
        try {
            await Promise.all([
                document.fonts.load("800 80px Rajdhani"),
                document.fonts.load("700 30px 'DM Sans'"),
                document.fonts.load("700 24px 'JetBrains Mono'")
            ]);
        } catch (e) {}
        const [icon, flagImg, avatar] = await Promise.all([
            loadImage(cert.icon), loadImage(cert.flag), loadImage(cert.avatar)
        ]);

        // Background and gold frame
        const bg = ctx.createLinearGradient(0, 0, W, H);
        bg.addColorStop(0, "#0b1120");
        bg.addColorStop(1, "#111a2e");
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = 10;
        ctx.strokeRect(40, 40, W - 80, H - 80);
        ctx.lineWidth = 2;
        ctx.strokeRect(62, 62, W - 124, H - 124);

        ctx.textAlign = "center";
        const mid = W / 2;

        if (icon) ctx.drawImage(icon, mid - 45, 100, 90, 90);
        ctx.fillStyle = "#facc15";
        ctx.font = "800 40px Rajdhani, Arial";
        ctx.fillText("FRAUD FILES  ·  2-DAY CHALLENGE", mid, 240);

        ctx.fillStyle = "#f8fafc";
        fitText(ctx, cert.title, W - 260, 84, "800", "Rajdhani, Arial");
        ctx.fillText(cert.title, mid, 345);

        ctx.fillStyle = "#94a3b8";
        ctx.font = "500 30px 'DM Sans', Arial";
        ctx.fillText("This certifies that", mid, 420);

        if (avatar) {
            ctx.save();
            ctx.beginPath();
            ctx.arc(mid, 515, 70, 0, Math.PI * 2);
            ctx.fillStyle = "#0d1220";
            ctx.fill();
            ctx.clip();
            ctx.drawImage(avatar, mid - 70, 445, 140, 140);
            ctx.restore();
            ctx.strokeStyle = "#facc15";
            ctx.lineWidth = 5;
            ctx.beginPath();
            ctx.arc(mid, 515, 70, 0, Math.PI * 2);
            ctx.stroke();
        }

        ctx.fillStyle = "#facc15";
        fitText(ctx, cert.name, W - 300, 96, "800", "Rajdhani, Arial");
        ctx.fillText(cert.name, mid, 680);

        ctx.fillStyle = "#e2e8f0";
        fitText(ctx, cert.line, W - 300, 36, "700", "'DM Sans', Arial");
        ctx.fillText(cert.line, mid, 750);

        if (flagImg) {
            ctx.drawImage(flagImg, mid - 45, 790, 90, 62);
        }
        ctx.fillStyle = "#cbd5e1";
        ctx.font = "700 30px 'DM Sans', Arial";
        ctx.fillText(cert.island, mid, 895);

        ctx.fillStyle = "#94a3b8";
        ctx.font = "700 26px 'JetBrains Mono', monospace";
        ctx.fillText(cert.stats, mid, 965);
        ctx.font = "500 22px 'JetBrains Mono', monospace";
        ctx.fillText(cert.date, mid, 1015);

        return canvas;
    }

    btn.addEventListener("click", async function () {
        btn.disabled = true;
        const canvas = await draw();
        const url = canvas.toDataURL("image/png");
        const preview = document.getElementById("fe-cert-preview");
        preview.src = url;
        preview.hidden = false;
        document.getElementById("fe-cert-hint").hidden = false;
        const link = document.createElement("a");
        link.href = url;
        link.download = "fraud-files-certificate.png";
        document.body.appendChild(link);
        link.click();
        link.remove();
        btn.disabled = false;
    });
})();
