import subprocess
import os

# 🔧 EDIT THIS LINE ONLY
REPO_URL = "https://github.com/YOURNAME/YOURREPO.git"
BRANCH = "main"

def run(cmd):
    print(f"→ {cmd}")
    subprocess.run(cmd, shell=True, check=False)

def main():
    print("\n🚀 Auto‑Push to GitHub\n")

    # Ensure we are inside a git repo
    if not os.path.exists(".git"):
        print("📁 Initializing new Git repository...")
        run("git init")

    # Add all files
    run("git add .")

    # Commit (ignore error if nothing changed)
    run('git commit -m "Auto‑deploy update"')

    # Set branch
    run(f"git branch -M {BRANCH}")

    # Add remote (ignore error if exists)
    run(f"git remote remove origin")
    run(f"git remote add origin {REPO_URL}")

    # Push to GitHub
    run(f"git push -u origin {BRANCH}")

    print("\n✅ GitHub push complete.")
    print(f"🌐 Repository: {REPO_URL}\n")

if __name__ == "__main__":
    main()



