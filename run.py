import os
import webbrowser
from threading import Timer

from app import create_app
from app.config import settings

app = create_app()


def _open_browser() -> None:
    try:
        webbrowser.open_new(f"http://{settings.host}:{settings.port}")
    except Exception:
        pass


if __name__ == "__main__":
    if os.getenv("OPEN_BROWSER", "1").lower() not in ("0", "false", "no"):
        Timer(1.0, _open_browser).start()
    app.run(debug=settings.debug, host=settings.host, port=settings.port)
