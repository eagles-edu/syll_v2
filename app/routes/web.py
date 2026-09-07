from flask import Blueprint, render_template, request

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.post("/lookup")
def lookup():
    word = (request.form.get("word") or "").strip()
    return render_template("index.html", word=word)


__all__ = ["bp"]
