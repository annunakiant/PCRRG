import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_file, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///pcrrg.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
CONTRACT_FOLDER = os.path.join(UPLOAD_FOLDER, "contracts")
PHOTO_FOLDER = os.path.join(UPLOAD_FOLDER, "photos")

os.makedirs(CONTRACT_FOLDER, exist_ok=True)
os.makedirs(PHOTO_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")

db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# MODELS (explicit foreign_keys to avoid ambiguity)
# ---------------------------------------------------------------------
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="contractor")

    # Explicit relationships: tell SQLAlchemy which FK to use
    jobs_assigned = db.relationship(
        "Job",
        foreign_keys="Job.assigned_to_id",
        backref="assigned_to_user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    jobs_admin = db.relationship(
        "Job",
        foreign_keys="Job.admin_id",
        backref="admin_user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_number = db.Column(db.String(100), unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    client_name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default="open")
    service_type = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Two explicit foreign keys to User.id
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    checklists = db.relationship("JobChecklist", backref="job", lazy=True, cascade="all, delete-orphan")
    photos = db.relationship("Photo", backref="job", lazy=True, cascade="all, delete-orphan")
    contracts = db.relationship("Contract", backref="job", lazy=True, cascade="all, delete-orphan")

    # Backwards-compatible properties so templates using job.assigned_to or job.admin still work
    @property
    def assigned_to(self):
        return getattr(self, "assigned_to_user", None)

    @property
    def admin(self):
        return getattr(self, "admin_user", None)

class ChecklistTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    service_type = db.Column(db.String(100), nullable=False)

    items = db.relationship("ChecklistItemTemplate", backref="template", lazy=True, cascade="all, delete-orphan")


class ChecklistItemTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("checklist_template.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)


class JobChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    template_name = db.Column(db.String(255), nullable=False)
    service_type = db.Column(db.String(100), nullable=False)

    items = db.relationship("JobChecklistItem", backref="checklist", lazy=True, cascade="all, delete-orphan")


class JobChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey("job_checklist.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    room = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    signed = db.Column(db.Boolean, default=False)
    signed_at = db.Column(db.DateTime, nullable=True)
    signer_name = db.Column(db.String(255), nullable=True)
    signer_email = db.Column(db.String(255), nullable=True)
    signature_image = db.Column(db.String(255), nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------------------------------------------------------------
# UTILS
# ---------------------------------------------------------------------

def is_admin() -> bool:
    return current_user.is_authenticated and current_user.role == "admin"

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return func(*args, **kwargs)
    return wrapper

# ---------------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("name")
        password = request.form.get("password")
        role = request.form.get("role", "contractor")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        user = User(email=email, name=name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("User registered. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ---------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    if is_admin():
        jobs = Job.query.order_by(Job.created_at.desc()).all()
    else:
        jobs = Job.query.filter(
            (Job.assigned_to_id == current_user.id) |
            (Job.admin_id == current_user.id)
        ).order_by(Job.created_at.desc()).all()

    return render_template("dashboard.html", jobs=jobs, is_admin=is_admin())

# ---------------------------------------------------------------------
# ADMIN CHECKLIST TEMPLATES
# ---------------------------------------------------------------------

@app.route("/admin/checklists", methods=["GET", "POST"])
@login_required
@admin_required
def admin_checklists():
    if request.method == "POST":
        name = request.form.get("name")
        service_type = request.form.get("service_type")
        items_raw = request.form.get("items")

        template = ChecklistTemplate(name=name, service_type=service_type)
        db.session.add(template)
        db.session.flush()

        for line in items_raw.splitlines():
            line = line.strip()
            if line:
                db.session.add(ChecklistItemTemplate(template_id=template.id, description=line))

        db.session.commit()
        flash("Checklist template created.", "success")
        return redirect(url_for("admin_checklists"))

    templates = ChecklistTemplate.query.all()
    return render_template("admin_checklists.html", templates=templates)

@app.route("/admin/checklists/<int:template_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_checklist_template(template_id):
    template = ChecklistTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    flash("Checklist template deleted.", "info")
    return redirect(url_for("admin_checklists"))

# ---------------------------------------------------------------------
# JOBS
# ---------------------------------------------------------------------

@app.route("/jobs/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_job():
    templates = ChecklistTemplate.query.all()
    users = User.query.all()

    if request.method == "POST":
        job_number = request.form.get("job_number")
        title = request.form.get("title")
        client_name = request.form.get("client_name")
        address = request.form.get("address")
        service_type = request.form.get("service_type")
        assigned_to_id = request.form.get("assigned_to_id")

        if Job.query.filter_by(job_number=job_number).first():
            flash("Job number already exists.", "danger")
            return redirect(url_for("create_job"))

        job = Job(
            job_number=job_number,
            title=title,
            client_name=client_name,
            address=address,
            service_type=service_type,
            admin_id=current_user.id,
            assigned_to_id=int(assigned_to_id) if assigned_to_id else None,
        )
        db.session.add(job)
        db.session.flush()

        template_id = request.form.get("template_id")
        if template_id:
            template = ChecklistTemplate.query.get(int(template_id))
            if template:
                checklist = JobChecklist(
                    job_id=job.id,
                    template_name=template.name,
                    service_type=template.service_type,
                )
                db.session.add(checklist)
                db.session.flush()

                for item_template in template.items:
                    db.session.add(JobChecklistItem(
                        checklist_id=checklist.id,
                        description=item_template.description,
                        completed=False,
                    ))

        db.session.commit()
        flash("Job created.", "success")
        return redirect(url_for("view_job", job_id=job.id))

    return render_template("create_job.html", templates=templates, users=users)


@app.route("/jobs/<int:job_id>")
@login_required
def view_job(job_id):
    job = Job.query.get_or_404(job_id)
    checklists = JobChecklist.query.filter_by(job_id=job.id).all()
    photos = Photo.query.filter_by(job_id=job.id).order_by(Photo.uploaded_at.desc()).all()
    contracts = Contract.query.filter_by(job_id=job.id).order_by(Contract.uploaded_at.desc()).all()

    google_maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    maps_url = f"https://www.google.com/maps/embed/v1/place?key={google_maps_api_key}&q={job.address}"

    return render_template(
        "view_job.html",
        job=job,
        checklists=checklists,
        photos=photos,
        contracts=contracts,
        maps_url=maps_url,
        is_admin=is_admin(),
    )


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)
    users = User.query.all()

    if request.method == "POST":
        job.title = request.form.get("title")
        job.client_name = request.form.get("client_name")
        job.address = request.form.get("address")
        job.service_type = request.form.get("service_type")
        assigned_to_id = request.form.get("assigned_to_id")
        job.assigned_to_id = int(assigned_to_id) if assigned_to_id else None

        db.session.commit()
        flash("Job updated.", "success")
        return redirect(url_for("view_job", job_id=job.id))

    return render_template("edit_job.html", job=job, users=users)


@app.route("/jobs/<int:job_id>/status", methods=["POST"])
@login_required
@admin_required
def update_job_status(job_id):
    job = Job.query.get_or_404(job_id)
    status = request.form.get("status")
    if status in ["open", "in_progress", "closed"]:
        job.status = status
        db.session.commit()
        flash(f"Job status updated to {status}.", "success")
    else:
        flash("Invalid status.", "danger")
    return redirect(url_for("view_job", job_id=job.id))


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted.", "info")
    return redirect(url_for("dashboard"))

# ---------------------------------------------------------------------
# CHECKLIST ITEMS
# ---------------------------------------------------------------------

@app.route("/checklist/item/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_checklist_item(item_id):
    item = JobChecklistItem.query.get_or_404(item_id)
    job = item.checklist.job

    if not (is_admin() or current_user.id in [job.assigned_to_id, job.admin_id]):
        flash("Not allowed.", "danger")
        return redirect(url_for("view_job", job_id=job.id))

    item.completed = not item.completed
    item.completed_at = datetime.utcnow() if item.completed else None
    db.session.commit()
    return redirect(url_for("view_job", job_id=job.id))

# ---------------------------------------------------------------------
# PHOTOS
# ---------------------------------------------------------------------

@app.route("/jobs/<int:job_id>/photos/upload", methods=["POST"])
@login_required
def upload_photo(job_id):
    job = Job.query.get_or_404(job_id)

    if not (is_admin() or current_user.id in [job.assigned_to_id, job.admin_id]):
        flash("Not allowed.", "danger")
        return redirect(url_for("view_job", job_id=job.id))

    file = request.files.get("photo")
    room = request.form.get("room")
    category = request.form.get("category")

    if not file:
        flash("No photo uploaded.", "danger")
        return redirect(url_for("view_job", job_id=job.id))

    filename = secure_filename(file.filename)
    filepath = os.path.join(PHOTO_FOLDER, filename)
    file.save(filepath)

    photo = Photo(
        job_id=job.id,
        room=room,
        category=category,
        filename=filename,
    )
    db.session.add(photo)
    db.session.commit()

    flash("Photo uploaded.", "success")
    return redirect(url_for("view_job", job_id=job.id))


@app.route("/photos/<int:photo_id>")
@login_required
def serve_photo(photo_id):
    photo = Photo.query.get_or_404(photo_id)
    filepath = os.path.join(PHOTO_FOLDER, photo.filename)
    return send_file(filepath)

# ---------------------------------------------------------------------
# CONTRACTS + SIGNATURE
# ---------------------------------------------------------------------

@app.route("/jobs/<int:job_id>/contracts/upload", methods=["POST"])
@login_required
@admin_required
def upload_contract(job_id):
    job = Job.query.get_or_404(job_id)
    file = request.files.get("contract")

    if not file:
        flash("No contract uploaded.", "danger")
        return redirect(url_for("view_job", job_id=job.id))

    filename = secure_filename(file.filename)
    filepath = os.path.join(CONTRACT_FOLDER, filename)
    file.save(filepath)

    contract = Contract(job_id=job.id, filename=filename)
    db.session.add(contract)
    db.session.commit()

    flash("Contract uploaded.", "success")
    return redirect(url_for("view_job", job_id=job.id))


@app.route("/contracts/<int:contract_id>")
@login_required
def serve_contract(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    filepath = os.path.join(CONTRACT_FOLDER, contract.filename)
    return send_file(filepath)


@app.route("/contracts/<int:contract_id>/sign", methods=["GET", "POST"])
@login_required
def sign_contract(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    job = contract.job

    if request.method == "POST":
        signer_name = request.form.get("signer_name")
        signer_email = request.form.get("signer_email")
        signature_data_url = request.form.get("signature_data_url")

        if signature_data_url and signature_data_url.startswith("data:image/png;base64,"):
            import base64
            header, encoded = signature_data_url.split(",", 1)
            signature_bytes = base64.b64decode(encoded)
            sig_filename = f"signature_{contract.id}_{int(datetime.utcnow().timestamp())}.png"
            sig_path = os.path.join(UPLOAD_FOLDER, sig_filename)
            with open(sig_path, "wb") as f:
                f.write(signature_bytes)
            contract.signature_image = sig_filename

        contract.signed = True
        contract.signed_at = datetime.utcnow()
        contract.signer_name
        
# Serve service worker from site root so browsers can register it at /service-worker.js
@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('static', 'service-worker.js')


# --- TEMP SEED START ---
# Temporary seed endpoint. Remove after use.
import os
from datetime import datetime
@app.route('/_seed_site')
def _seed_site():
    token = os.environ.get('SEED_TOKEN', '')
    req = request.args.get('token', '')
    if not token or req != token:
        return ('Forbidden', 403)
    with app.app_context():
        db.create_all()
        admin_email = 'admin@pcrrg.local'
        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(email=admin_email, name='Admin User', role='admin')
            admin.set_password('ChangeMeNow123!')
            db.session.add(admin)
            db.session.commit()
        if Job.query.count() == 0:
            job = Job(job_number='PCRRG-1001', title='Sample Job', client_name='Acme Corp', address='123 Main St', status='open', service_type='Water Mitigation', admin_id=admin.id, assigned_to_id=admin.id, created_at=datetime.utcnow())
            db.session.add(job)
            db.session.commit()
            try:
                p = Photo(job_id=job.id, filename='placeholder.jpg', category='Before', uploaded_at=datetime.utcnow())
                db.session.add(p)
                db.session.commit()
            except Exception:
                pass
    return ('Seeded', 200)
# --- TEMP SEED END ---


