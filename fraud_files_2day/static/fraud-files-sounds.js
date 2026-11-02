/* =========================================================
   FRAUD FILES -- SOUND DESIGN
   Short, soft, modern sounds built in the browser (no audio
   files). Each voice takes (ctx, time, output) so the same
   code can play live or be rendered to a file for preview.
========================================================= */

window.FE_VOICES = (function () {

    function env(ctx, at, attack, peak, decay) {
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, at);
        g.gain.exponentialRampToValueAtTime(peak, at + attack);
        g.gain.exponentialRampToValueAtTime(0.0001, at + attack + decay);
        return g;
    }

    function osc(ctx, type, freq, at, stopAt) {
        const o = ctx.createOscillator();
        o.type = type;
        o.frequency.setValueAtTime(freq, at);
        o.start(at);
        o.stop(stopAt);
        return o;
    }

    // A soft mallet note: sine body + a quiet higher partial, quick decay.
    function mallet(ctx, out, at, freq, peak, decay) {
        const g = env(ctx, at, 0.004, peak, decay);
        const g2 = env(ctx, at, 0.002, peak * 0.25, decay * 0.35);
        osc(ctx, "sine", freq, at, at + decay + 0.1).connect(g);
        osc(ctx, "sine", freq * 4.01, at, at + decay * 0.4 + 0.1).connect(g2);
        g.connect(out);
        g2.connect(out);
    }

    function noise(ctx, seconds) {
        const length = Math.floor(ctx.sampleRate * seconds);
        const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
        return buffer;
    }

    return {
        // Right answer: two soft rising mallet notes (a fifth apart).
        correct: function (ctx, at, out) {
            mallet(ctx, out, at, 783.99, 0.28, 0.45);
            mallet(ctx, out, at + 0.09, 1174.66, 0.24, 0.6);
        },

        // Wrong answer: a low, muted double knock. No buzzer.
        wrong: function (ctx, at, out) {
            [0, 0.13].forEach(function (offset, i) {
                const t = at + offset;
                const lp = ctx.createBiquadFilter();
                lp.type = "lowpass";
                lp.frequency.value = 700;
                const g = env(ctx, t, 0.005, 0.35, 0.22);
                const o = osc(ctx, "triangle", i ? 155 : 185, t, t + 0.3);
                o.frequency.exponentialRampToValueAtTime(i ? 120 : 140, t + 0.2);
                o.connect(lp);
                lp.connect(g);
                g.connect(out);
            });
        },

        // Last seconds of the timer: a quiet wooden click.
        tick: function (ctx, at, out) {
            const bp = ctx.createBiquadFilter();
            bp.type = "bandpass";
            bp.frequency.value = 1900;
            bp.Q.value = 6;
            const src = ctx.createBufferSource();
            src.buffer = noise(ctx, 0.05);
            const g = env(ctx, at, 0.001, 1.4, 0.05);
            src.connect(bp);
            bp.connect(g);
            g.connect(out);
            src.start(at);
        },

        // A new round / new case file: a soft airy whoosh.
        whoosh: function (ctx, at, out) {
            const src = ctx.createBufferSource();
            src.buffer = noise(ctx, 0.9);
            const bp = ctx.createBiquadFilter();
            bp.type = "bandpass";
            bp.Q.value = 1.2;
            bp.frequency.setValueAtTime(300, at);
            bp.frequency.exponentialRampToValueAtTime(2600, at + 0.45);
            bp.frequency.exponentialRampToValueAtTime(900, at + 0.85);
            const g = ctx.createGain();
            g.gain.setValueAtTime(0.0001, at);
            g.gain.exponentialRampToValueAtTime(0.5, at + 0.35);
            g.gain.exponentialRampToValueAtTime(0.0001, at + 0.85);
            src.connect(bp);
            bp.connect(g);
            g.connect(out);
            src.start(at);
        },

        // Someone moves up the leaderboard: a single gentle glass blip.
        blip: function (ctx, at, out) {
            mallet(ctx, out, at, 1318.5, 0.14, 0.35);
        },

        // Round finished: three calm rising notes.
        roundDone: function (ctx, at, out) {
            [523.25, 659.25, 783.99].forEach(function (f, i) {
                mallet(ctx, out, at + i * 0.12, f, 0.22, 0.7);
            });
        },

        // Winner reveal: a warm chord that swells in, with a soft shimmer.
        winner: function (ctx, at, out) {
            [261.63, 329.63, 392.0, 523.25].forEach(function (f, i) {
                const g = ctx.createGain();
                g.gain.setValueAtTime(0.0001, at);
                g.gain.exponentialRampToValueAtTime(0.08, at + 0.6);
                g.gain.exponentialRampToValueAtTime(0.0001, at + 3.2);
                const lp = ctx.createBiquadFilter();
                lp.type = "lowpass";
                lp.frequency.value = 2400;
                [-4, 4].forEach(function (cents) {
                    const o = osc(ctx, "sawtooth", f, at, at + 3.3);
                    o.detune.value = cents;
                    o.connect(lp);
                });
                lp.connect(g);
                g.connect(out);
            });
            [1046.5, 1318.5, 1568.0, 2093.0].forEach(function (f, i) {
                mallet(ctx, out, at + 0.5 + i * 0.11, f, 0.1, 0.9);
            });
        }
    };
})();
