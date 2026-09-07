from flask import Flask

from app.config import settings
from app.logging_config import setup_logging


def create_app() -> Flask:
    setup_logging(
        settings.log_file,
        settings.log_level,
        settings.markdown_trace_file,
        settings.logic_disagreement_file,
    )
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=settings.secret_key,
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        DEBUG=settings.debug,
    )

    from app.routes import api, web

    app.register_blueprint(api.bp)
    app.register_blueprint(web.bp)
    return app


__all__ = ["create_app"]
