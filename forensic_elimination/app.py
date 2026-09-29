import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from elimination import elimination_bp, initialize_database

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static"
)

# Needed for the host-login session cookie. Set SECRET_KEY in the
# environment for a real deployment; this random fallback is fine for
# local play but will invalidate sessions on every restart.
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Hosting services sit behind a proxy; trust its https/host headers so
# the join link and QR code point at the real public address.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.register_blueprint(elimination_bp)

initialize_database()


if __name__ == "__main__":
    app.run(debug=True)
