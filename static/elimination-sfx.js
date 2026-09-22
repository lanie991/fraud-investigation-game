/* =========================================================
   FORENSIC ELIMINATION -- SYNTHESIZED SOUND EFFECTS
   Small Web Audio API tones, generated on the fly. No audio
   files needed. Silently does nothing if the browser blocks
   audio until a user gesture, or has no Web Audio support.
========================================================= */

window.FE_SFX = (function () {
    let ctx = null;

    function getCtx() {
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

    return {
        playCorrect: playCorrect,
        playIncorrect: playIncorrect,
        playTick: playTick,
        playWin: playWin,
        playEliminated: playEliminated
    };
})();
