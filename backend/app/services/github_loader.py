import os
import re
from git import Repo, GitCommandError

def safe_repo_id(url: str) -> str:
    m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not m:
        return re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")
    owner = m.group(1)
    repo = m.group(2).replace(".git", "")
    return f"{owner}_{repo}"

def clone_or_update(repo_url: str, repos_dir: str, branch: str | None = None) -> tuple[str, str]:
    os.makedirs(repos_dir, exist_ok=True)
    repo_id = safe_repo_id(repo_url)
    dest = os.path.join(repos_dir, repo_id)

    # ---- (1) Prevent concurrent git ops on same repo ----
    ingest_lock = os.path.join(repos_dir, f".lock_{repo_id}")
    lock_fd = None
    try:
        lock_fd = os.open(ingest_lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        # Another ingest is running (or crashed leaving the lock).
        # If you want, you can delete it manually, but safest is to fail fast.
        raise RuntimeError(f"Repo is currently being ingested: {repo_id}. Try again in a moment.")

    try:
        if not os.path.exists(dest):
            repo = Repo.clone_from(repo_url, dest)
        else:
            repo = Repo(dest)

            # ---- (2) Clear stale git index lock if it exists ----
            index_lock = os.path.join(dest, ".git", "index.lock")
            if os.path.exists(index_lock):
                try:
                    os.remove(index_lock)
                except Exception:
                    # If Windows still refuses, another process really is using it.
                    raise RuntimeError(f"Git index is locked for {repo_id}. Close VS Code/Git tools and retry.")

            # Ensure origin is correct
            try:
                origin = repo.remotes.origin
                current_url = list(origin.urls)[0]
                if current_url.rstrip("/") != repo_url.rstrip("/"):
                    origin.set_url(repo_url)
            except Exception:
                if "origin" not in [r.name for r in repo.remotes]:
                    repo.create_remote("origin", repo_url)
                else:
                    repo.remotes.origin.set_url(repo_url)

        # Fetch latest
        repo.remotes.origin.fetch(prune=True)

        # ---- (3) Pick a branch that exists on origin ----
        remote_branches = {ref.remote_head for ref in repo.remotes.origin.refs}  # e.g. {"main","master",...}

        if branch and branch in remote_branches:
            target_branch = branch
        else:
            # Try origin/HEAD, else fall back to main/master/anything available
            target_branch = None
            try:
                head_ref = repo.git.symbolic_ref("refs/remotes/origin/HEAD")  # refs/remotes/origin/main
                guess = head_ref.split("/")[-1]
                if guess in remote_branches:
                    target_branch = guess
            except Exception:
                pass

            if not target_branch:
                if "main" in remote_branches:
                    target_branch = "main"
                elif "master" in remote_branches:
                    target_branch = "master"
                elif len(remote_branches) > 0:
                    target_branch = sorted(remote_branches)[0]
                else:
                    raise RuntimeError("No remote branches found after fetch. Is the repo empty or private?")

        # Checkout + reset hard to remote for deterministic ingestion
        if target_branch in repo.heads:
            repo.git.checkout(target_branch)
        else:
            repo.git.checkout("-b", target_branch, f"origin/{target_branch}")

        repo.git.reset("--hard", f"origin/{target_branch}")

        commit_sha = repo.head.commit.hexsha[:12]
        return dest, commit_sha

    finally:
        # release lock
        try:
            if lock_fd is not None:
                os.close(lock_fd)
            if os.path.exists(ingest_lock):
                os.remove(ingest_lock)
        except Exception:
            pass

def iter_text_files(root: str):
    import os

    skip_dirs = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}
    allowed_ext = {
        ".md",".txt",".py",".js",".ts",".tsx",".jsx",".java",".go",".rs",".c",".cpp",".h",
        ".json",".yaml",".yml",".toml",".ini",".cfg",".sh"
    }

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in allowed_ext:
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                yield path, text
            except Exception:
                continue
