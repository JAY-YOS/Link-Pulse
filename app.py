import os
import re
import secrets
import string
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db_url = os.environ.get("DATABASE_URL", "sqlite:///linkpulse.db")
if db_url.startswith("postgres://"):  # Render/Heroku style URL
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
db = SQLAlchemy(app)

RESERVED = {"api", "stats", "static", "favicon.ico", "robots.txt"}
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")


def today():
    return datetime.utcnow().date()


# ---------- models ----------
class Link(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    short_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    original_url = db.Column(db.Text, nullable=False)
    expiry_date = db.Column(db.Date)
    click_limit = db.Column(db.Integer)
    click_count = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    clicks = db.relationship("Click", backref="link", lazy=True)

    @property
    def status(self):
        if not self.is_active:
            return "Disabled"
        if self.expiry_date and today() > self.expiry_date:
            return "Expired"
        if self.click_limit and self.click_count >= self.click_limit:
            return "Limit reached"
        return "Active"


class Click(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link_id = db.Column(db.Integer, db.ForeignKey("link.id"), nullable=False, index=True)
    clicked_at = db.Column(db.DateTime, default=datetime.utcnow)
    referrer = db.Column(db.Text)
    device = db.Column(db.String(20))
    browser = db.Column(db.String(20))
    ip = db.Column(db.String(60))


with app.app_context():
    db.create_all()


# ---------- helpers ----------
def short_url(link):
    return request.host_url + link.short_code


def gen_code(n=6):
    chars = string.ascii_letters + string.digits
    while True:
        code = "".join(secrets.choice(chars) for _ in range(n))
        if not Link.query.filter_by(short_code=code).first():
            return code


def make_link(url, alias=None, expiry=None, limit=None):
    """Validate input, apply rules, store the link. Raises ValueError on bad input."""
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("Enter a valid URL starting with http:// or https://")

    alias = (alias or "").strip()
    if alias:
        if not ALIAS_RE.match(alias) or alias.lower() in RESERVED:
            raise ValueError("Alias must be 3-30 letters, numbers, - or _ (and not a reserved word)")
        if Link.query.filter_by(short_code=alias).first():
            raise ValueError("That alias is already taken")
        code = alias
    else:
        code = gen_code()

    exp = None
    if expiry:
        try:
            exp = date.fromisoformat(str(expiry))
        except ValueError:
            raise ValueError("Expiry date is not valid")
        if exp < today():
            raise ValueError("Expiry date is in the past")

    lim = None
    if limit not in (None, ""):
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            raise ValueError("Click limit must be a number")
        if lim < 1:
            raise ValueError("Click limit must be at least 1")

    link = Link(short_code=code, original_url=url, expiry_date=exp, click_limit=lim)
    db.session.add(link)
    db.session.commit()
    return link


def parse_ua(ua):
    l = (ua or "").lower()
    if "ipad" in l or "tablet" in l or ("android" in l and "mobi" not in l):
        device = "Tablet"
    elif "mobi" in l or "iphone" in l:
        device = "Mobile"
    else:
        device = "Desktop"
    if "edg" in l:
        browser = "Edge"
    elif "opr" in l or "opera" in l:
        browser = "Opera"
    elif "chrome" in l or "crios" in l:
        browser = "Chrome"
    elif "firefox" in l or "fxios" in l:
        browser = "Firefox"
    elif "safari" in l:
        browser = "Safari"
    else:
        browser = "Other"
    return device, browser


def link_stats(link):
    clicks = link.clicks
    days = [today() - timedelta(days=i) for i in range(6, -1, -1)]
    per_day = Counter(c.clicked_at.date() for c in clicks)
    hosts = Counter((urlparse(c.referrer).netloc or "Direct") if c.referrer else "Direct" for c in clicks)
    return {
        "total_clicks": len(clicks),
        "unique_visitors": len({c.ip for c in clicks}),
        "labels": [d.strftime("%d %b") for d in days],
        "daily": [per_day.get(d, 0) for d in days],
        "devices": dict(Counter(c.device for c in clicks)),
        "browsers": dict(Counter(c.browser for c in clicks)),
        "referrers": dict(hosts.most_common(5)),
    }


# ---------- routes ----------
@app.route("/", methods=["GET", "POST"])
def index():
    error = new_link = None
    if request.method == "POST":
        try:
            new_link = make_link(
                request.form.get("url"),
                request.form.get("alias"),
                request.form.get("expiry"),
                request.form.get("limit"),
            )
        except ValueError as e:
            error = str(e)
    links = Link.query.order_by(Link.created_at.desc()).all()
    return render_template(
        "index.html",
        links=links,
        error=error,
        new_link=new_link,
        new_url=short_url(new_link) if new_link else None,
        total_clicks=sum(l.click_count for l in links),
        form=request.form,
    )


@app.post("/api/links")
def api_create():
    d = request.get_json(silent=True) or {}
    try:
        link = make_link(d.get("url"), d.get("alias"), d.get("expiry_date"), d.get("click_limit"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(short_code=link.short_code, short_url=short_url(link)), 201


@app.get("/api/links/<code>/stats")
def api_stats(code):
    link = Link.query.filter_by(short_code=code).first_or_404()
    return jsonify(link_stats(link))


@app.get("/stats/<code>")
def stats(code):
    link = Link.query.filter_by(short_code=code).first_or_404()
    return render_template("stats.html", link=link, short=short_url(link), s=link_stats(link))


@app.get("/<code>")
def go(code):
    link = Link.query.filter_by(short_code=code).first_or_404()
    if link.status != "Active":
        return render_template("error.html", link=link), 410
    device, browser = parse_ua(request.headers.get("User-Agent"))
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    link.click_count += 1
    db.session.add(Click(link_id=link.id, referrer=request.referrer, device=device, browser=browser, ip=ip))
    db.session.commit()
    return redirect(link.original_url, code=302)


if __name__ == "__main__":
    app.run(debug=True)
