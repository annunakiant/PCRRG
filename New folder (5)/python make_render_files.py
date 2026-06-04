import os

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def main():
    print("🔧 Setting up Render deployment structure...\n")

    project = "pcrr_app"
    ensure_dir(project)

    # Move into project folder
    os.chdir(project)

    # Create folders
    ensure_dir("uploads")
    ensure_dir("static")
    ensure_dir("templates")

    # Create requirements.txt
    write_file("requirements.txt", 
"""flask
flask_sqlalchemy
flask_login
reportlab
flask_mail
gunicorn
""")

    # Create Procfile
    write_file("Procfile", 
"web: gunicorn app:app\n")

    # Create runtime.txt
    write_file("runtime.txt", 
"python-3.10.9\n")

    # Create .gitignore
    write_file(".gitignore",
"""__pycache__/
*.pyc
instance/
uploads/
.env
""")

    print("📄 Created: requirements.txt")
    print("📄 Created: Procfile")
    print("📄 Created: runtime.txt")
    print("📄 Created: .gitignore")
    print("📁 Created folders: uploads/, static/, templates/\n")

    # Check for app.py
    if os.path.exists("app.py"):
        print("✅ app.py already exists — you're good to go!")
    else:
        print("⚠️ app.py NOT found — place your full app.py inside:")
        print(f"   {os.getcwd()}")

    print("\n🎉 Render deployment files created successfully!")
    print("Next steps:")
    print("1. Add your app.py into the pcrr_app folder.")
    print("2. Run: git init, git add ., git commit")
    print("3. Push to GitHub")
    print("4. Deploy on Render")

if __name__ == "__main__":
    main()
