/* =========================================================
   FORENSIC ELIMINATION -- SYNTHESIZED SOUND EFFECTS
   Small Web Audio API tones, generated on the fly. No audio
   files needed. Silently does nothing if the browser blocks
   audio until a user gesture, or has no Web Audio support.
========================================================= */

window.FE_SFX = (function () {
    let ctx = null;

    // Players can switch sound off; the choice is remembered on their phone.
    let muted = false;
    try { muted = localStorage.getItem("fe_sound") === "off"; } catch (e) {}

    function getCtx() {
        if (muted) return null;
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return null;
        if (!ctx) {
            try {
                ctx = new AudioContextClass();
            } catch (e) {
                return null;
            }
        }
        if (ctx.state === "suspended") {
            ctx.resume().catch(function () {});
        }
        return ctx;
    }

    function tone(audioCtx, freq, startTime, duration, type, gainPeak) {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = type || "sine";
        osc.frequency.setValueAtTime(freq, startTime);
        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(gainPeak || 0.2, startTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(startTime);
        osc.stop(startTime + duration + 0.05);
    }

    function playCorrect() {
        const audioCtx = getCtx();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        tone(audioCtx, 660, now, 0.15, "sine", 0.22);
        tone(audioCtx, 880, now + 0.12, 0.2, "sine", 0.22);
    }

    function playIncorrect() {
        const audioCtx = getCtx();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        tone(audioCtx, 220, now, 0.28, "sawtooth", 0.15);
        tone(audioCtx, 180, now + 0.14, 0.3, "sawtooth", 0.15);
    }

    function playTick() {
        const audioCtx = getCtx();
        if (!audioCtx) return;
        tone(audioCtx, 1000, audioCtx.currentTime, 0.06, "square", 0.08);
    }

    function playWin() {
        const audioCtx = getCtx();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        [523.25, 659.25, 783.99, 1046.5].forEach(function (freq, i) {
            tone(audioCtx, freq, now + i * 0.15, 0.35, "triangle", 0.2);
        });
    }

    function playEliminated() {
        const audioCtx = getCtx();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        tone(audioCtx, 300, now, 0.3, "sawtooth", 0.18);
        tone(audioCtx, 220, now + 0.22, 0.35, "sawtooth", 0.18);
        tone(audioCtx, 140, now + 0.46, 0.5, "sawtooth", 0.18);
    }

    // "Dun dun": our own take on a TV crime-drama sting. Two heavy hits,
    // each a deep thump, a burst of noise and a metallic clang, the second
    // a little lower. Built from scratch here; no recording is used.
    function hit(audioCtx, at, pitch) {
        const out = audioCtx.createGain();
        out.gain.value = 0.9;
        out.connect(audioCtx.destination);

        // Deep body that drops in pitch.
        const body = audioCtx.createOscillator();
        const bodyGain = audioCtx.createGain();
        body.type = "triangle";
        body.frequency.setValueAtTime(pitch * 1.6, at);
        body.frequency.exponentialRampToValueAtTime(pitch, at + 0.12);
        bodyGain.gain.setValueAtTime(0.0001, at);
        bodyGain.gain.exponentialRampToValueAtTime(0.55, at + 0.01);
        bodyGain.gain.exponentialRampToValueAtTime(0.0001, at + 1.1);
        body.connect(bodyGain);
        bodyGain.connect(out);
        body.start(at);
        body.stop(at + 1.2);

        // Metallic clang: a few out-of-tune partials that ring briefly.
        [2.76, 4.07, 5.43, 6.8].forEach(function (ratio, i) {
            const osc = audioCtx.createOscillator();
            const g = audioCtx.createGain();
            osc.type = "square";
            osc.frequency.setValueAtTime(pitch * ratio, at);
            g.gain.setValueAtTime(0.0001, at);
            g.gain.exponentialRampToValueAtTime(0.05 / (i + 1), at + 0.005);
            g.gain.exponentialRampToValueAtTime(0.0001, at + 0.5 - i * 0.07);
            osc.connect(g);
            g.connect(out);
            osc.start(at);
            osc.stop(at + 0.6);
        });

        // Short burst of noise for the "slam".
        const length = Math.floor(audioCtx.sampleRate * 0.25);
        const buffer = audioCtx.createBuffer(1, length, audioCtx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < length; i++) {
            data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 3);
        }
        const noise = audioCtx.createBufferSource();
        const filter = audioCtx.createBiquadFilter();
        const noiseGain = audioCtx.createGain();
        noise.buffer = buffer;
        filter.type = "lowpass";
        filter.frequency.value = 1800;
        noiseGain.gain.value = 0.35;
        noise.connect(filter);
        filter.connect(noiseGain);
        noiseGain.connect(out);
        noise.start(at);
    }

    function playDunDun() {
        const audioCtx = getCtx();
        if (!audioCtx) return;
        const now = audioCtx.currentTime + 0.05;
        hit(audioCtx, now, 82);          // DUN
        hit(audioCtx, now + 0.62, 69);   // DUN
    }

    // Some browsers only let an AudioContext run after a user
    // gesture. Try to unlock it on the first click/key/touch anywhere.
    function unlock() {
        getCtx();
        document.removeEventListener("click", unlock);
        document.removeEventListener("keydown", unlock);
        document.removeEventListener("touchstart", unlock);
    }
    document.addEventListener("click", unlock);
    document.addEventListener("keydown", unlock);
    document.addEventListener("touchstart", unlock);

    function isMuted() {
        return muted;
    }

    function setMuted(value) {
        muted = !!value;
        try { localStorage.setItem("fe_sound", muted ? "off" : "on"); } catch (e) {}
        if (muted && ctx && ctx.state === "running") {
            ctx.suspend().catch(function () {});
        }
    }

    return {
        isMuted: isMuted,
        setMuted: setMuted,
        playCorrect: playCorrect,
        playIncorrect: playIncorrect,
        playTick: playTick,
        playWin: playWin,
        playEliminated: playEliminated,
        playDunDun: playDunDun
    };
})();
