import os
import shutil
import subprocess
from datetime import datetime
import requests

# ============================================================
# CONFIG — EDIT THESE TWO VALUES
# ============================================================

RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "rnd_2TQwCloA98FnUqjEDQjdztmyaRaj")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "srv-d8jjmbk2m8qs7395kf00")

PROJECT_NAME = "pcrr_app"
BUILD_DIR = "build_output"
VERSION_FILE = "VERSION.txt"
BACKUP_DIR = "backups"
REPO_URL = "https://github.com/annunakiant/PCRRG.git"
BRANCH = "main"

# ============================================================
# HELPERS
# ============================================================

def run(cmd):
    print(f"→ {cmd}")
    subprocess.run(cmd, shell=True, check=False)

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def ensure(path):
    if not os.path.exists(path):
        os.makedirs(path)

# ============================================================
# 1. BUILD PROJECT (NO DELETE, NO CHDIR)
# ============================================================
def build_project():
    print("\n🔥 BUILD: Rebuilding project folder\n")

    # SAFE: Do NOT delete build_output on Windows
    ensure(BUILD_DIR)

    project_path = os.path.join(BUILD_DIR, PROJECT_NAME)
    ensure(project_path)

    ensure(os.path.join(project_path, "uploads/contracts"))
    ensure(os.path.join(project_path, "uploads/photos"))
    ensure(os.path.join(project_path, "static"))
    ensure(os.path.join(project_path, "templates"))

    # requirements
    write(os.path.join(project_path, "requirements.txt"),
"""flask
flask_sqlalchemy
flask_login
flask_mail
reportlab
gunicorn
""")

    write(os.path.join(project_path, "Procfile"), "web: gunicorn app:app\n")
    write(os.path.join(project_path, "runtime.txt"), "python-3.10.9\n")
    write(os.path.join(project_path, ".gitignore"),
"""__pycache__/
*.pyc
instance/
uploads/
.env
VERSION.txt
""")

    # Copy app.py from root
    root_app = os.path.join(os.getcwd(), "app.py")
    if os.path.exists(root_app):
        shutil.copy(root_app, os.path.join(project_path, "app.py"))
        print("✅ app.py copied")
    else:
        print("⚠️ app.py NOT found in root folder.")

    # PWA files
    write(os.path.join(project_path, "static/manifest.json"),
"""{
  "name": "PCRRG Field Ops",
  "short_name": "PCRRG",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#111111",
  "theme_color": "#4fc3f7",
  "icons": []
}
""")

    write(os.path.join(project_path, "static/service-worker.js"),
"""const CACHE_NAME = 'pcrrg-cache-v1';
const URLS_TO_CACHE = ['/', '/login', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(URLS_TO_CACHE)));
});

self.addEventListener('fetch', e => {
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
""")

    print("✅ Build complete.\n")

# ============================================================
# 2. BUMP VERSION
# ============================================================

def bump_version():
    print("🔢 VERSION: Bumping version")
    if not os.path.exists(VERSION_FILE):
        current = "0.0.0"
    else:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            current = f.read().strip() or "0.0.0"

    major, minor, patch = map(int, current.split("."))
    patch += 1
    new = f"{major}.{minor}.{patch}"

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(new)

    print(f"   Current: {current}")
    print(f"   New:     {new}\n")

# ============================================================
# 3. BACKUP ZIP
# ============================================================

def backup_project():
    print("💾 BACKUP: Creating backup zip")
    ensure(BACKUP_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = os.path.join(BACKUP_DIR, f"{PROJECT_NAME}_{ts}")
    shutil.make_archive(zip_name, "zip", BUILD_DIR)
    print(f"✅ Backup created: {zip_name}.zip\n")

# ============================================================
# 4. PUSH TO GITHUB
# ============================================================

def push_github():
    print("🚀 GIT: Auto‑push to GitHub\n")

    if not os.path.exists(".git"):
        run("git init")

    run("git add .")
    run('git commit -m "Auto‑deploy update"')
    run(f"git branch -M {BRANCH}")
    run("git remote remove origin")
    run(f"git remote add origin {REPO_URL}")
    run(f"git push -u origin {BRANCH}")

    print(f"\n✅ Pushed to GitHub: {REPO_URL}\n")

# ============================================================
# 5. TRIGGER RENDER DEPLOY
# ============================================================

def trigger_render():
    print("🌐 RENDER: Triggering deploy via API\n")
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys"
    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json={})
    if resp.status_code == 201:
        print("✅ Render deploy triggered.")
    else:
        print(f"⚠️ Failed to trigger deploy: {resp.status_code} {resp.text}")
    print()

# ============================================================
# MAIN
# ============================================================

def main():
    print("\n🧵 MASTER PIPELINE START\n")
    build_project()
    bump_version()
    backup_project()
    push_github()
    trigger_render()
    print("🎉 PIPELINE COMPLETE — app is rebuilt, backed up, pushed, and redeploying.\n")

if __name__ == "__main__":
    main()
