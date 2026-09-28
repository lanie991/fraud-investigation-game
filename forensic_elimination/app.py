from importlib import import_module

flask = import_module("flask")

Flask = flask.Flask

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static"
)

from elimination import elimination_bp, initialize_database

app.register_blueprint(elimination_bp)

initialize_database()


# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":
    app.run(debug=True, port=5001)
