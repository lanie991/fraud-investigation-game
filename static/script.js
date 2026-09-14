/* =========================================================
   FRAUD INVESTIGATION GAME
   GLOBAL JAVASCRIPT
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    /*
     * Prevent accidental double-clicking of submit buttons.
     */

    const forms = document.querySelectorAll("form");

    forms.forEach(function (form) {

        form.addEventListener("submit", function () {

            const button = form.querySelector(
                'button[type="submit"], input[type="submit"]'
            );

            if (!button) {
                return;
            }

            if (button.dataset.submitted === "true") {
                return;
            }

            button.dataset.submitted = "true";

            button.disabled = true;

            button.style.opacity = "0.65";

            button.style.cursor = "wait";

            if (button.tagName === "BUTTON") {
                button.innerText = "SUBMITTING...";
            }

        });

    });

});