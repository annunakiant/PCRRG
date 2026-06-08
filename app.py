import os, secrets
from io import BytesIO, StringIO
from datetime import datetime, date

from flask import (
    Flask, request, redirect, url_for, flash,
    render_template_string, send_from_directory,
    make_response, send_file, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

try:
    from flask_mail import Mail, Message
    MAIL_AVAILABLE = True
except ImportError:
    MAIL_AVAILABLE = False

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///pcrr_full_app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if MAIL_AVAILABLE:
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "YOUR_EMAIL@gmail.com")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "YOUR_APP_PASSWORD")
    mail = Mail(app)
else:
    mail = None

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------- MODELS ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    pin_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="employee")
    active = db.Column(db.Boolean, default=True)
    full_name = db.Column(db.String(200))
    phone = db.Column(db.String(50))

class Theme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    primary_color = db.Column(db.String(20), default="#004b8d")
    accent_color = db.Column(db.String(20), default="#00a3e0")
    background_color = db.Column(db.String(20), default="#f4f7fb")
    text_color = db.Column(db.String(20), default="#1f2933")
    background_image = db.Column(db.String(300))
    font_family = db.Column(db.String(200), default="system-ui, -apple-system, 'Segoe UI', sans-serif")
    logo_filename = db.Column(db.String(300))

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300))
    status = db.Column(db.String(50), default="Not Started")
    start_date = db.Column(db.Date)
    est_completion = db.Column(db.Date)
    finished_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    contract_filename = db.Column(db.String(300))
    customer_signature = db.Column(db.String(300))
    contractor_signature = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_hidden = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    customer_portal_token = db.Column(db.String(64), unique=True)

class JobCheckin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(20), default="checkin")
    job = db.relationship("Job", backref="checkins")
    user = db.relationship("User", backref="checkins")

class PackoutSheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"))
    name = db.Column(db.String(200), nullable=False)
    job = db.relationship("Job", backref="sheets")

class PackoutItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey("packout_sheet.id"))
    location = db.Column(db.String(100))
    description = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    condition = db.Column(db.String(50))
    step1_photo = db.Column(db.String(300))
    step2_photo = db.Column(db.String(300))
    step3_photo = db.Column(db.String(300))
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    sheet = db.relationship("PackoutSheet", backref="items")
    creator = db.relationship("User", foreign_keys=[created_by])
    updater = db.relationship("User", foreign_keys=[updated_by])

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    barcode = db.Column(db.String(120))
    quantity_on_hand = db.Column(db.Integer, default=0)
    photo_filename = db.Column(db.String(300))

class InventoryTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_item.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=True)
    type = db.Column(db.String(20))
    quantity = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    item = db.relationship("InventoryItem", backref="transactions")
    user = db.relationship("User")
    job = db.relationship("Job")

class SiteReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"))
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    job = db.relationship("Job", backref="reports")
    user = db.relationship("User")

class NotificationToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    token = db.Column(db.String(300), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="notification_tokens")

# ---------- HELPERS ----------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def short_tag(user):
    if not user:
        return "----"
    return (user.username or "user")[:4].ljust(4, "-")

def save_upload(file):
    if file and file.filename:
        fname = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
        file.save(path)
        return fname
    return None

def send_pdf_email(to_email, subject, body, pdf_bytes, filename):
    if not mail:
        print("Email not configured.")
        return
    msg = Message(subject, recipients=[to_email])
    msg.body = body
    msg.attach(filename, "application/pdf", pdf_bytes)
    mail.send(msg)

def send_job_notification(job_id, message):
    print(f"[NOTIFY] Job {job_id}: {message}")

BASE_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>PCRR FieldOps</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="{primary_color}">
<link rel="manifest" href="{manifest_url}">
<style>
body {{
  margin: 0;
  font-family: {font_family};
  background-color: {background_color};
  color: {text_color};
  {background_image_css}
}}
.navbar {{
  background-color: {primary_color};
  color: #fff;
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
}}
.navbar a {{
  color: #fff;
  text-decoration: none;
  margin-left: 10px;
}}
.container {{ padding: 16px; }}
.btn {{
  background-color: {primary_color};
  color: #fff;
  padding: 6px 12px;
  border-radius: 6px;
  text-decoration: none;
  display: inline-block;
  margin: 4px 0;
  border: none;
  cursor: pointer;
}}
.btn-secondary {{ background-color: {accent_color}; }}
.btn-danger {{ background-color: #b91c1c; }}
.card {{
  background: #ffffffdd;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}}
.flash {{
  background: #ffeeba;
  padding: 8px;
  border-radius: 6px;
  margin-bottom: 10px;
}}
details summary {{
  cursor: pointer;
  font-weight: bold;
  padding: 6px;
  background: #e5e7eb;
  border-radius: 4px;
}}
.packout-card {{
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 10px;
  border: 1px solid #d1d5db;
}}
.packout-header {{
  background-color: {primary_color};
  color: #fff;
  padding: 6px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
}}
.packout-body {{
  background: #ffffff;
  padding: 8px 10px;
  font-size: 0.9rem;
}}
.packout-meta {{
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 4px;
}}
.packout-actions {{
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}}
.thumb-row {{
  display: flex;
  gap: 6px;
  margin-top: 6px;
}}
.thumb-row img {{
  width: 60px;
  height: 60px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #d1d5db;
}}
input, textarea, select {{
  width: 100%;
  padding: 6px;
  margin: 4px 0 8px 0;
  box-sizing: border-box;
}}
</style>
<script>
if ("serviceWorker" in navigator) {{
  window.addEventListener("load", function() {{
    navigator.serviceWorker.register("{sw_url}");
  }});
}}
</script>
</head>
<body>
<div class="navbar">
  <div><strong>PCRR FieldOps</strong></div>
  <div>{nav_links}</div>
</div>
<div class="container">
  {flashes}
  {content}
</div>
</body>
</html>
"""

def render_page(content_html):
    theme = Theme.query.first()
    if not theme:
        theme = Theme()
        db.session.add(theme)
        db.session.commit()
    if current_user.is_authenticated:
        nav = f"""
        <span>{current_user.username}</span>
        <a href="{url_for('dashboard')}">Dashboard</a>
        <a href="{url_for('jobs')}">Jobs</a>
        <a href="{url_for('inventory')}">Inventory</a>
        <a href="{url_for('employees')}">Employees</a>
        <a href="{url_for('theme_page')}">Theme</a>
        <a href="{url_for('logout')}">Logout</a>
        """
    else:
        nav = f'<a href="{url_for("login")}">Login</a>'
    from flask import get_flashed_messages
    msgs = get_flashed_messages()
    flashes = "".join(f'<div class="flash">{m}</div>' for m in msgs)
    bg_css = ""
    if theme.background_image:
        bg_url = url_for("uploaded_file", filename=theme.background_image)
        bg_css = f"background-image:url('{bg_url}');background-size:cover;background-attachment:fixed;"
    return BASE_HTML.format(
        primary_color=theme.primary_color,
        accent_color=theme.accent_color,
        background_color=theme.background_color,
        text_color=theme.text_color,
        font_family=theme.font_family,
        background_image_css=bg_css,
        manifest_url=url_for("manifest"),
        sw_url=url_for("service_worker"),
        nav_links=nav,
        flashes=flashes,
        content=content_html,
    )

# ---------- AUTH ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        pin = request.form.get("pin") or ""
        user = User.query.filter_by(username=username, active=True).first()
        if user and check_password_hash(user.pin_hash, pin):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid username or PIN")
    content = """
    <h2>Login</h2>
    <form method="POST">
      <label>Username</label>
      <input name="username" required>
      <label>PIN (4 digits)</label>
      <input name="pin" type="password" maxlength="4" required>
      <button class="btn" type="submit">Login</button>
    </form>
    """
    return render_template_string(render_page(content))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ---------- DASHBOARD ----------
@app.route("/")
@login_required
def dashboard():
    job_count = Job.query.filter_by(is_deleted=False).count()
    open_jobs = Job.query.filter(Job.status != "Completed", Job.is_deleted == False).count()
    inv_items = InventoryItem.query.count()
    staff = User.query.filter_by(active=True).count()
    content = f"""
    <h2>Dashboard</h2>
    <div class="card">
      <p>Jobs: {job_count} (Open: {open_jobs})</p>
      <p>Inventory Items: {inv_items}</p>
      <p>Active Staff: {staff}</p>
    </div>
    <div class="card">
      <a class="btn" href="{url_for('jobs')}">Jobs</a>
      <a class="btn" href="{url_for('inventory')}">Inventory</a>
      <a class="btn" href="{url_for('employees')}">Employees</a>
      <a class="btn" href="{url_for('theme_page')}">Theme</a>
    </div>
    """
    return render_template_string(render_page(content))

# ---------- JOBS + GPS ----------
ROOM_OPTIONS = [
    "Kitchen", "Living Room", "Bedroom 1", "Bedroom 2", "Bedroom 3", "Bedroom 4",
    "Bathroom", "Basement", "Dining Room", "Attic", "Hallway", "Closet", "Other"
]
CONDITION_OPTIONS = ["Salvageable", "Non-salvageable", "Retained"]
MAX_ITEMS_PER_SHEET = 50

@app.route("/jobs")
@login_required
def jobs():
    q = (request.args.get("q") or "").strip()
    query = Job.query.filter_by(is_deleted=False)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Job.customer_name.ilike(like), Job.address.ilike(like)))
    jobs = query.order_by(Job.created_at.desc()).all()
    rows = ""
    for j in jobs:
        if j.is_hidden and current_user.role != "admin":
            continue
        rows += f"""
        <div class='card'>
          <strong>{j.customer_name}</strong><br>
          {j.address or ''}<br>
          Status: {j.status}<br>
          <a class='btn' href='{url_for('job_detail', job_id=j.id)}'>Open</a>
        </div>
        """
    content = f"""
    <h2>Jobs</h2>
    <form method="GET">
      <input name="q" placeholder="Search" value="{q}">
      <button class="btn" type="submit">Search</button>
      <a class="btn btn-secondary" href="{url_for('jobs')}">Clear</a>
    </form>
    <a class="btn" href="{url_for('job_create')}">Create Job</a>
    <br><br>
    {rows or "<p>No jobs yet.</p>"}
    """
    return render_template_string(render_page(content))

@app.route("/jobs/create", methods=["GET", "POST"])
@login_required
def job_create():
    if request.method == "POST":
        customer_name = (request.form.get("customer_name") or "").strip()
        address = (request.form.get("address") or "").strip()
        notes = request.form.get("notes") or ""
        start = request.form.get("start_date") or None
        est = request.form.get("est_completion") or None
        if not customer_name:
            flash("Customer name required")
        else:
            token = secrets.token_hex(16)
            job = Job(
                customer_name=customer_name,
                address=address or None,
                notes=notes,
                start_date=date.fromisoformat(start) if start else None,
                est_completion=date.fromisoformat(est) if est else None,
                status="Not Started",
                customer_portal_token=token,
            )
            db.session.add(job)
            db.session.commit()
            db.session.add(PackoutSheet(job_id=job.id, name="Packout Sheet"))
            db.session.commit()
            flash("Job created")
            return redirect(url_for("jobs"))
    content = """
    <h2>Create Job</h2>
    <form method="POST">
      <label>Customer Name</label>
      <input name="customer_name" required>
      <label>Address</label>
      <input name="address">
      <label>Start Date</label>
      <input type="date" name="start_date">
      <label>Estimated Completion</label>
      <input type="date" name="est_completion">
      <label>Notes</label>
      <textarea name="notes"></textarea>
      <button class="btn" type="submit">Create</button>
    </form>
    """
    return render_template_string(render_page(content))

@app.route("/jobs/<int:job_id>", methods=["GET", "POST"])
@login_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    sheet = job.sheets[0] if job.sheets else None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_status":
            job.status = request.form.get("status") or job.status
            if job.status == "Completed" and not job.finished_date:
                job.finished_date = date.today()
            db.session.commit()
            send_job_notification(job.id, f"Status changed to {job.status}")
            flash("Status updated")
            return redirect(url_for("job_detail", job_id=job.id))
        if action == "gps_check":
            lat = float(request.form.get("lat") or 0)
            lng = float(request.form.get("lng") or 0)
            ctype = request.form.get("ctype") or "checkin"
            chk = JobCheckin(job_id=job.id, user_id=current_user.id,
                             latitude=lat, longitude=lng, type=ctype)
            db.session.add(chk)
            db.session.commit()
            flash(f"GPS {ctype} recorded")
            return redirect(url_for("job_detail", job_id=job.id))
        if action == "upload_contract":
            f = request.files.get("contract")
            fname = save_upload(f)
            if fname:
                job.contract_filename = fname
                db.session.commit()
                flash("Contract uploaded")
            return redirect(url_for("job_detail", job_id=job.id))
        if action == "sign_customer":
            sig = request.files.get("customer_signature")
            fname = save_upload(sig)
            if fname:
                job.customer_signature = fname
                db.session.commit()
                flash("Customer signed")
            return redirect(url_for("job_detail", job_id=job.id))
        if action == "sign_contractor":
            sig = request.files.get("contractor_signature")
            fname = save_upload(sig)
            if fname:
                job.contractor_signature = fname
                db.session.commit()
                flash("Contractor signed")
            return redirect(url_for("job_detail", job_id=job.id))
        if action == "add_report":
            st = request.form.get("report_status") or ""
            notes = request.form.get("report_notes") or ""
            r = SiteReport(job_id=job.id, created_by=current_user.id, status=st, notes=notes)
            db.session.add(r)
            db.session.commit()
            flash("Report saved")
            return redirect(url_for("job_detail", job_id=job.id))
        if action == "add_item":
            if not sheet:
                sheet = PackoutSheet(job_id=job.id, name="Packout Sheet")
                db.session.add(sheet)
                db.session.commit()
            if len(sheet.items) >= MAX_ITEMS_PER_SHEET:
                flash("Max 50 items per sheet")
                return redirect(url_for("job_detail", job_id=job.id))
            location = request.form.get("location") or "Other"
            description = (request.form.get("description") or "").strip()
            quantity = int(request.form.get("quantity") or 1)
            condition = request.form.get("condition") or "Salvageable"
            if not description:
                flash("Description required")
            else:
                now = datetime.utcnow()
                it = PackoutItem(
                    sheet_id=sheet.id,
                    location=location,
                    description=description,
                    quantity=quantity,
                    condition=condition,
                    created_by=current_user.id,
                    updated_by=current_user.id,
                    created_at=now,
                    updated_at=now,
                )
                db.session.add(it)
                db.session.commit()
                flash("Item added")
            return redirect(url_for("job_detail", job_id=job.id))
    gps_html = ""
    for c in job.checkins[-10:]:
        gps_html += f"<div>{c.timestamp} — {c.type} by {short_tag(c.user)} @ ({c.latitude}, {c.longitude})</div>"
    portal_url = url_for("customer_portal", token=job.customer_portal_token, _external=True)
    room_opts = "".join(f"<option value='{r}'>{r}</option>" for r in ROOM_OPTIONS)
    cond_opts = "".join(f"<option value='{c}'>{c}</option>" for c in CONDITION_OPTIONS)
    # Packout cards
    items_html = ""
    if sheet:
        for it in sheet.items:
            def img_tag(fn):
                return f"<a href='{url_for('uploaded_file', filename=fn)}' target='_blank'><img src='{url_for('uploaded_file', filename=fn)}'></a>" if fn else ""
            thumbs = f"""
            <div class="thumb-row">
              {img_tag(it.step1_photo)}
              {img_tag(it.step2_photo)}
              {img_tag(it.step3_photo)}
            </div>
            """
            items_html += f"""
            <div class="packout-card">
              <div class="packout-header">
                <div>{it.location or "Location"} — {it.description}</div>
                <div>Qty {it.quantity} · {it.condition or ""}</div>
              </div>
              <div class="packout-body">
                {thumbs}
                <div class="packout-meta">
                  Created: {it.created_at} by {short_tag(it.creator)}<br>
                  Updated: {it.updated_at} by {short_tag(it.updater)}
                </div>
                <div class="packout-actions">
                  <a class="btn btn-secondary" href="{url_for('packout_edit', job_id=job.id, item_id=it.id)}">📝 Edit</a>
                  <a class="btn btn-secondary" href="{url_for('packout_photos', job_id=job.id, item_id=it.id)}">📷 Photos</a>
                  <a class="btn btn-danger" href="{url_for('packout_delete', job_id=job.id, item_id=it.id)}" onclick="return confirm('Delete item?');">🗑 Delete</a>
                </div>
              </div>
            </div>
            """
    reports_html = "".join(
        f"<div>{r.created_at} — {r.status}<br>{r.notes}</div><hr>" for r in job.reports
    ) or "<p>No reports.</p>"
    content = f"""
    <h2>Job: {job.customer_name}</h2>
    <p><strong>Address:</strong> {job.address or "-"}</p>
    <p><strong>Status:</strong> {job.status}</p>
    <p><strong>Customer Portal:</strong><br>
      <a href="{portal_url}" target="_blank">{portal_url}</a>
    </p>

    <div class="card">
      <h3>Status</h3>
      <form method="POST">
        <input type="hidden" name="action" value="update_status">
        <select name="status">
          <option value="Not Started" {"selected" if job.status=="Not Started" else ""}>Not Started</option>
          <option value="In Progress" {"selected" if job.status=="In Progress" else ""}>In Progress</option>
          <option value="Completed" {"selected" if job.status=="Completed" else ""}>Completed</option>
        </select>
        <button class="btn" type="submit">Save</button>
      </form>
    </div>

    <details open>
      <summary>GPS Check‑In / Out</summary>
      <div class="card">
        <form method="POST">
          <input type="hidden" name="action" value="gps_check">
          <label>Latitude</label>
          <input name="lat" required>
          <label>Longitude</label>
          <input name="lng" required>
          <label>Type</label>
          <select name="ctype">
            <option value="checkin">Check‑In</option>
            <option value="checkout">Check‑Out</option>
          </select>
          <button class="btn" type="submit">Record</button>
        </form>
        <h4>Recent</h4>
        {gps_html or "<p>No GPS activity yet.</p>"}
      </div>
    </details>

    <details open>
      <summary>Packout Inventory</summary>
      <div class="card">
        <h3>Add Item</h3>
        <form method="POST">
          <input type="hidden" name="action" value="add_item">
          <label>Location</label>
          <select name="location">{room_opts}</select>
          <label>Description</label>
          <input name="description" required>
          <label>Quantity</label>
          <input type="number" name="quantity" value="1">
          <label>Condition</label>
          <select name="condition">{cond_opts}</select>
          <button class="btn" type="submit">Add</button>
        </form>
      </div>
      {items_html or "<p>No items yet.</p>"}
      <div class="card">
        <a class="btn btn-secondary" href="{url_for('packout_csv', job_id=job.id)}">Export Packout CSV</a>
        <a class="btn btn-secondary" href="{url_for('job_closeout_pdf', job_id=job.id)}">Job Closeout PDF</a>
      </div>
    </details>

    <details>
      <summary>Contract & Signatures</summary>
      <div class="card">
        <h3>Contract</h3>
        {"<a href='" + url_for('uploaded_file', filename=job.contract_filename) + "' target='_blank'>Open</a>" if job.contract_filename else "<p>No contract uploaded.</p>"}
        <form method="POST" enctype="multipart/form-data">
          <input type="hidden" name="action" value="upload_contract">
          <input type="file" name="contract">
          <button class="btn" type="submit">Upload</button>
        </form>
      </div>
      <div class="card">
        <h3>Customer Signature</h3>
        {("<img src='" + url_for('uploaded_file', filename=job.customer_signature) + "' style='max-width:200px;'>") if job.customer_signature else "<p>Not signed.</p>"}
        <form method="POST" enctype="multipart/form-data">
          <input type="hidden" name="action" value="sign_customer">
          <input type="file" name="customer_signature" accept="image/*" capture="environment">
          <button class="btn" type="submit">Sign</button>
        </form>
        <h3>Contractor Signature</h3>
        {("<img src='" + url_for('uploaded_file', filename=job.contractor_signature) + "' style='max-width:200px;'>") if job.contractor_signature else "<p>Not signed.</p>"}
        <form method="POST" enctype="multipart/form-data">
          <input type="hidden" name="action" value="sign_contractor">
          <input type="file" name="contractor_signature" accept="image/*" capture="environment">
          <button class="btn" type="submit">Sign</button>
        </form>
      </div>
    </details>

    <details>
      <summary>Site Reports</summary>
      <div class="card">
        <h3>Add Report</h3>
        <form method="POST">
          <input type="hidden" name="action" value="add_report">
          <label>Status</label>
          <input name="report_status">
          <label>Notes</label>
          <textarea name="report_notes"></textarea>
          <button class="btn" type="submit">Save</button>
        </form>
        {reports_html}
      </div>
    </details>
    """
    return render_template_string(render_page(content))

# ---------- PACKOUT EDIT / DELETE / PHOTOS ----------
@app.route("/jobs/<int:job_id>/packout/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def packout_edit(job_id, item_id):
    job = Job.query.get_or_404(job_id)
    item = PackoutItem.query.get_or_404(item_id)
    if request.method == "POST":
        item.location = request.form.get("location") or item.location
        item.description = (request.form.get("description") or "").strip() or item.description
        item.quantity = int(request.form.get("quantity") or item.quantity)
        item.condition = request.form.get("condition") or item.condition
        item.updated_by = current_user.id
        item.updated_at = datetime.utcnow()
        db.session.commit()
        flash("Item updated")
        return redirect(url_for("job_detail", job_id=job.id))
    room_opts = "".join(
        f"<option value='{r}' {'selected' if r==item.location else ''}>{r}</option>"
        for r in ROOM_OPTIONS
    )
    cond_opts = "".join(
        f"<option value='{c}' {'selected' if c==item.condition else ''}>{c}</option>"
        for c in CONDITION_OPTIONS
    )
    content = f"""
    <h2>Edit Packout Item</h2>
    <div class="card">
      <form method="POST">
        <label>Location</label>
        <select name="location">{room_opts}</select>
        <label>Description</label>
        <input name="description" value="{item.description}">
        <label>Quantity</label>
        <input type="number" name="quantity" value="{item.quantity}">
        <label>Condition</label>
        <select name="condition">{cond_opts}</select>
        <button class="btn" type="submit">Save</button>
        <a class="btn btn-secondary" href="{url_for('job_detail', job_id=job.id)}">Back</a>
      </form>
    </div>
    """
    return render_template_string(render_page(content))

@app.route("/jobs/<int:job_id>/packout/<int:item_id>/photos", methods=["GET", "POST"])
@login_required
def packout_photos(job_id, item_id):
    job = Job.query.get_or_404(job_id)
    item = PackoutItem.query.get_or_404(item_id)
    if request.method == "POST":
        for step in ["step1_photo", "step2_photo", "step3_photo"]:
            f = request.files.get(step)
            if f and f.filename:
                fname = save_upload(f)
                setattr(item, step, fname)
        item.updated_by = current_user.id
        item.updated_at = datetime.utcnow()
        db.session.commit()
        flash("Photos updated")
        return redirect(url_for("job_detail", job_id=job.id))
    def img(fn):
        return f"<img src='{url_for('uploaded_file', filename=fn)}' style='max-width:120px;'>" if fn else "<p>No photo.</p>"
    content = f"""
    <h2>Item Photos</h2>
    <div class="card">
      <form method="POST" enctype="multipart/form-data">
        <h3>Step 1</h3>
        {img(item.step1_photo)}
        <input type="file" name="step1_photo" accept="image/*" capture="environment">
        <h3>Step 2</h3>
        {img(item.step2_photo)}
        <input type="file" name="step2_photo" accept="image/*" capture="environment">
        <h3>Step 3</h3>
        {img(item.step3_photo)}
        <input type="file" name="step3_photo" accept="image/*" capture="environment">
        <button class="btn" type="submit">Save</button>
        <a class="btn btn-secondary" href="{url_for('job_detail', job_id=job.id)}">Back</a>
      </form>
    </div>
    """
    return render_template_string(render_page(content))

@app.route("/jobs/<int:job_id>/packout/<int:item_id>/delete")
@login_required
def packout_delete(job_id, item_id):
    job = Job.query.get_or_404(job_id)
    item = PackoutItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item deleted")
    return redirect(url_for("job_detail", job_id=job.id))

# ---------- CSV + PDF ----------
@app.route("/jobs/<int:job_id>/packout.csv")
@login_required
def packout_csv(job_id):
    job = Job.query.get_or_404(job_id)
    sheet = job.sheets[0] if job.sheets else None
    si = StringIO()
    si.write("Location,Description,Quantity,Condition,CreatedAt,UpdatedAt\n")
    if sheet:
        for it in sheet.items:
            si.write(f'"{it.location}","{it.description}",{it.quantity},"{it.condition}",{it.created_at},{it.updated_at}\n')
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=job_{job.id}_packout.csv"
    output.headers["Content-Type"] = "text/csv"
    return output

@app.route("/jobs/<int:job_id>/closeout.pdf")
@login_required
def job_closeout_pdf(job_id):
    job = Job.query.get_or_404(job_id)
    sheet = job.sheets[0] if job.sheets else None
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    w, h = letter
    y = h - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Job Closeout Report - {job.customer_name}")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Address: {job.address or '-'}")
    y -= 14
    c.drawString(40, y, f"Status: {job.status}")
    y -= 14
    c.drawString(40, y, f"Start: {job.start_date}  Est: {job.est_completion}  Finished: {job.finished_date}")
    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Packout Items")
    y -= 16
    c.setFont("Helvetica", 9)
    if sheet and sheet.items:
        for it in sheet.items:
            if y < 60:
                c.showPage(); y = h - 40
            c.drawString(40, y, f"{it.location} - {it.description}  Qty:{it.quantity}  Cond:{it.condition}")
            y -= 12
    else:
        c.drawString(40, y, "No items.")
        y -= 12
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Site Reports")
    y -= 16
    c.setFont("Helvetica", 9)
    if job.reports:
        for r in job.reports:
            if y < 60:
                c.showPage(); y = h - 40
            c.drawString(40, y, f"{r.created_at} - {r.status}: {r.notes[:80]}")
            y -= 12
    else:
        c.drawString(40, y, "No reports.")
        y -= 12
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Signatures")
    y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Customer signed: {'Yes' if job.customer_signature else 'No'}")
    y -= 12
    c.drawString(40, y, f"Contractor signed: {'Yes' if job.contractor_signature else 'No'}")
    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name=f"job_{job.id}_closeout.pdf",
                     mimetype="application/pdf")

# ---------- CUSTOMER PORTAL ----------
@app.route("/portal/<token>", methods=["GET", "POST"])
def customer_portal(token):
    job = Job.query.filter_by(customer_portal_token=token, is_deleted=False).first_or_404()
    msg = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "sign_customer":
            sig = request.files.get("customer_signature")
            fname = save_upload(sig)
            if fname:
                job.customer_signature = fname
                db.session.commit()
                msg = "Signature saved."
        elif action == "upload_photo":
            photo = request.files.get("photo")
            fname = save_upload(photo)
            if fname:
                job.notes = (job.notes or "") + f"\nCustomer photo: {fname}"
                db.session.commit()
                msg = "Photo uploaded."
    sig_html = f"<img src='{url_for('uploaded_file', filename=job.customer_signature)}' style='max-width:200px;'>" if job.customer_signature else "<p>No signature on file.</p>"
    content = f"""
    <h2>Customer Portal</h2>
    <p>Job for: <strong>{job.customer_name}</strong></p>
    <p>Address: {job.address or "-"}</p>
    <p>Status: {job.status}</p>
    <p style="color:green;">{msg}</p>
    <div class="card">
      <h3>Sign Authorization</h3>
      {sig_html}
      <form method="POST" enctype="multipart/form-data">
        <input type="hidden" name="action" value="sign_customer">
        <input type="file" name="customer_signature" accept="image/*" capture="environment" required>
        <button class="btn" type="submit">Sign</button>
      </form>
    </div>
    <div class="card">
      <h3>Upload Site Photo</h3>
      <form method="POST" enctype="multipart/form-data">
        <input type="hidden" name="action" value="upload_photo">
        <input type="file" name="photo" accept="image/*" capture="environment" required>
        <button class="btn" type="submit">Upload</button>
      </form>
    </div>
    """
    return render_template_string(render_page(content))

# ---------- INVENTORY ----------
@app.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        barcode = (request.form.get("barcode") or "").strip()
        qty = int(request.form.get("quantity") or 0)
        if not name:
            flash("Name required")
        else:
            it = InventoryItem(name=name, barcode=barcode or None, quantity_on_hand=qty)
            db.session.add(it)
            db.session.commit()
            flash("Item added")
            return redirect(url_for("inventory"))
    items = InventoryItem.query.order_by(InventoryItem.name).all()
    rows = ""
    for it in items:
        rows += f"<div class='card'><strong>{it.name}</strong><br>Barcode: {it.barcode or '-'}<br>On hand: {it.quantity_on_hand}</div>"
    content = f"""
    <h2>Inventory</h2>
    <form method="POST">
      <label>Name</label>
      <input name="name" required>
      <label>Barcode</label>
      <input name="barcode">
      <label>Quantity</label>
      <input type="number" name="quantity" value="0">
      <button class="btn" type="submit">Save</button>
    </form>
    <h3>Items</h3>
    {rows or "<p>No items.</p>"}
    """
    return render_template_string(render_page(content))

# ---------- EMPLOYEES + ANALYTICS ----------
@app.route("/employees")
@login_required
def employees():
    if current_user.role != "admin":
        flash("Admin only")
        return redirect(url_for("dashboard"))
    staff = User.query.order_by(User.username).all()
    rows = ""
    for u in staff:
        rows += f"""
        <div class="card">
          <strong>{u.username}</strong> — {u.role} — {'Active' if u.active else 'Inactive'}<br>
          Name: {u.full_name or '-'} | Phone: {u.phone or '-'}<br>
          <a class="btn btn-secondary" href="{url_for('employee_analytics', user_id=u.id)}">Analytics</a>
        </div>
        """
    content = f"""
    <h2>Employees</h2>
    <a class="btn" href="{url_for('employee_create')}">Add Employee</a>
    <br><br>
    {rows or "<p>No employees yet.</p>"}
    """
    return render_template_string(render_page(content))

@app.route("/employees/create", methods=["GET", "POST"])
@login_required
def employee_create():
    if current_user.role != "admin":
        flash("Admin only")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        pin = request.form.get("pin") or ""
        role = request.form.get("role") or "employee"
        full_name = (request.form.get("full_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        if not username or not pin or len(pin) != 4:
            flash("Username and 4-digit PIN required")
        elif User.query.filter_by(username=username).first():
            flash("Username exists")
        else:
            u = User(
                username=username,
                pin_hash=generate_password_hash(pin),
                role=role,
                full_name=full_name,
                phone=phone,
            )
            db.session.add(u)
            db.session.commit()
            flash("Employee created")
            return redirect(url_for("employees"))
    content = """
    <h2>Add Employee</h2>
    <form method="POST">
      <label>Username</label>
      <input name="username" required>
      <label>PIN (4 digits)</label>
      <input name="pin" type="password" maxlength="4" required>
      <label>Role</label>
      <select name="role">
        <option value="employee">Employee</option>
        <option value="manager">Manager</option>
        <option value="admin">Admin</option>
      </select>
      <label>Full Name</label>
      <input name="full_name">
      <label>Phone</label>
      <input name="phone">
      <button class="btn" type="submit">Save</button>
    </form>
    """
    return render_template_string(render_page(content))

@app.route("/employees/<int:user_id>/analytics")
@login_required
def employee_analytics(user_id):
    if current_user.role not in ("admin", "manager") and current_user.id != user_id:
        flash("Not allowed")
        return redirect(url_for("dashboard"))
    user = User.query.get_or_404(user_id)
    packout_created = PackoutItem.query.filter_by(created_by=user.id).count()
    packout_updated = PackoutItem.query.filter_by(updated_by=user.id).count()
    reports_count = SiteReport.query.filter_by(created_by=user.id).count()
    inv_tx_count = InventoryTransaction.query.filter_by(user_id=user.id).count()
    checkins = JobCheckin.query.filter_by(user_id=user.id).order_by(JobCheckin.timestamp.desc()).all()
    checkin_html = "".join(
        f"<div>{c.timestamp} — {c.type} @ ({c.latitude}, {c.longitude}) Job {c.job_id}</div>"
        for c in checkins[:20]
    ) or "<p>No check-ins yet.</p>"
    content = f"""
    <h2>Analytics: {user.username}</h2>
    <div class="card">
      <p>Packout Items Created: {packout_created}</p>
      <p>Packout Items Updated: {packout_updated}</p>
      <p>Site Reports Submitted: {reports_count}</p>
      <p>Inventory Transactions: {inv_tx_count}</p>
    </div>
    <div class="card">
      <h3>Recent GPS Check-ins</h3>
      {checkin_html}
    </div>
    <div class="card">
      <a class="btn" href="{url_for('employee_activity_pdf', user_id=user.id)}">Download Activity PDF</a>
    </div>
    """
    return render_template_string(render_page(content))

@app.route("/employees/<int:user_id>/activity_pdf")
@login_required
def employee_activity_pdf(user_id):
    user = User.query.get_or_404(user_id)
    packout_created = PackoutItem.query.filter_by(created_by=user.id).all()
    packout_updated = PackoutItem.query.filter_by(updated_by=user.id).all()
    reports = SiteReport.query.filter_by(created_by=user.id).all()
    inventory_tx = InventoryTransaction.query.filter_by(user_id=user.id).all()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    w, h = letter
    y = h - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Employee Activity: {user.username}")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Name: {user.full_name or '-'}  Phone: {user.phone or '-'}")
    y -= 30
    def section(title):
        nonlocal y
        if y < 80:
            c.showPage(); y = h - 50
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, title)
        y -= 20
        c.setFont("Helvetica", 9)
    section("Packout Items Created")
    for it in packout_created:
        if y < 60: c.showPage(); y = h - 50
        c.drawString(40, y, f"{it.created_at} — {it.description} ({it.location}) Qty:{it.quantity}")
        y -= 12
    section("Packout Items Updated")
    for it in packout_updated:
        if y < 60: c.showPage(); y = h - 50
        c.drawString(40, y, f"{it.updated_at} — {it.description} ({it.location}) Qty:{it.quantity}")
        y -= 12
    section("Site Reports")
    for r in reports:
        if y < 60: c.showPage(); y = h - 50
        c.drawString(40, y, f"{r.created_at} — {r.status}: {(r.notes or '')[:60]}")
        y -= 12
    section("Inventory Transactions")
    for t in inventory_tx:
        if y < 60: c.showPage(); y = h - 50
        job_name = t.job.customer_name if t.job else "-"
        c.drawString(40, y, f"{t.timestamp} — {t.type} {t.quantity} of {t.item.name} (Job: {job_name})")
        y -= 12
    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{user.username}_activity.pdf",
        mimetype="application/pdf",
    )

# ---------- THEME ----------
@app.route("/theme", methods=["GET", "POST"])
@login_required
def theme_page():
    if current_user.role != "admin":
        flash("Admin only")
        return redirect(url_for("dashboard"))
    theme = Theme.query.first()
    if request.method == "POST":
        theme.primary_color = request.form.get("primary_color") or theme.primary_color
        theme.accent_color = request.form.get("accent_color") or theme.accent_color
        theme.background_color = request.form.get("background_color") or theme.background_color
        theme.text_color = request.form.get("text_color") or theme.text_color
        theme.font_family = request.form.get("font_family") or theme.font_family
        bg = save_upload(request.files.get("background_image"))
        logo = save_upload(request.files.get("logo"))
        if bg: theme.background_image = bg
        if logo: theme.logo_filename = logo
        db.session.commit()
        flash("Theme updated")
        return redirect(url_for("theme_page"))
    content = f"""
    <h2>Theme</h2>
    <form method="POST" enctype="multipart/form-data">
      <label>Primary Color</label>
      <input type="color" name="primary_color" value="{theme.primary_color}">
      <label>Accent Color</label>
      <input type="color" name="accent_color" value="{theme.accent_color}">
      <label>Background Color</label>
      <input type="color" name="background_color" value="{theme.background_color}">
      <label>Text Color</label>
      <input type="color" name="text_color" value="{theme.text_color}">
      <label>Font Family</label>
      <input name="font_family" value="{theme.font_family}">
      <label>Background Image</label>
      <input type="file" name="background_image" accept="image/*">
      <label>Logo</label>
      <input type="file" name="logo" accept="image/*">
      <button class="btn" type="submit">Save</button>
    </form>
    """
    return render_template_string(render_page(content))

# ---------- PWA ----------
@app.route("/manifest.json")
def manifest():
    theme = Theme.query.first() or Theme()
    data = f"""
{{
  "name": "PCRR FieldOps",
  "short_name": "FieldOps",
  "start_url": "/",
  "display": "standalone",
  "background_color": "{theme.background_color}",
  "theme_color": "{theme.primary_color}",
  "icons": []
}}
"""
    resp = make_response(data)
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp

@app.route("/service-worker.js")
def service_worker():
    js = """
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => clients.claim());
self.addEventListener("fetch", e => e.respondWith(fetch(e.request)));
"""
    resp = make_response(js)
    resp.headers["Content-Type"] = "application/javascript"
    return resp

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------- INIT ----------
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                pin_hash=generate_password_hash("1234"),
                role="admin",
                full_name="Admin",
            )
            db.session.add(admin)
        if not Theme.query.first():
            db.session.add(Theme())
        db.session.commit()

# Initialize database on startup
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
