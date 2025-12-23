import os
import re
import shutil
from urllib.parse import urlparse
from git import Repo, GitCommandError

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
ALLOWED_EXT = {
    ".md", ".txt",
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sh", ".ps1",
}

def normalize_github_repo_url(url: str) -> str:
    """
    Accepts:
      - https://github.com/OWNER/REPO
      - https://github.com/OWNER/REPO.git
    Rejects folder URLs like:
      - https://github.com/OWNER/REPO/tree/main/src/...
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Empty repo_url")

    # Basic parse
    u = urlparse(url)
    if u.netloc.lower() not in {"github.com", "www.github.com"}:
        # allow non-github too, but keep it strict for your project
        raise ValueError("Only github.com URLs are supported in this MVP")

    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Repo URL must look like https://github.com/OWNER/REPO")

    owner, repo = parts[0], parts[1]
    repo = repo.replace(".git", "")

    # If user pasted a file/folder URL (tree/blob), reject clearly
    if len(parts) > 2 and parts[2] in {"tree", "blob"}:
        raise ValueError(
            "You pasted a folder/file URL. Use the repo root URL like: https://github.com/OWNER/REPO"
        )

    return f"https://github.com/{owner}/{repo}.git"

def safe_repo_id(url: str) -> str:
    # deterministic folder name
    m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not m:
        return re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")
    owner = m.group(1)
    repo = m.group(2).replace(".git", "")
    return f"{owner}_{repo}"

def _remove_stale_index_lock(repo_path: str) -> None:
    lock_path = os.path.join(repo_path, ".git", "index.lock")
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except Exception:
            pass

def _default_branch(repo: Repo) -> str:
    """
    Determine default branch from origin/HEAD if possible, else try main/master.
    """
    try:
        head_ref = repo.git.symbolic_ref("refs/remotes/origin/HEAD")  # refs/remotes/origin/main
        return head_ref.split("/")[-1]
    except Exception:
        # fallbacks
        for b in ("main", "master"):
            try:
                repo.git.rev_parse(f"origin/{b}")
                return b
            except Exception:
                continue
        return "main"

def clone_or_update(repo_url: str, repos_dir: str, branch: str | None = None) -> tuple[str, str]:
    os.makedirs(repos_dir, exist_ok=True)

    repo_url = normalize_github_repo_url(repo_url)
    repo_id = safe_repo_id(repo_url)
    dest = os.path.join(repos_dir, repo_id)

    if not os.path.exists(dest):
        repo = Repo.clone_from(repo_url, dest)
    else:
        repo = Repo(dest)

        # ensure origin exists & matches
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

    _remove_stale_index_lock(dest)

    # fetch latest
    try:
        repo.remotes.origin.fetch(prune=True)
    except GitCommandError as e:
        _remove_stale_index_lock(dest)
        raise

    # branch selection
    target_branch = (branch or "").strip() or _default_branch(repo)

    # checkout local branch tracking remote + hard reset to origin for deterministic ingestion
    _remove_stale_index_lock(dest)
    try:
        if target_branch in repo.heads:
            repo.git.checkout(target_branch)
        else:
            # create local branch from origin/<branch>
            repo.git.checkout("-b", target_branch, f"origin/{target_branch}")

        repo.git.reset("--hard", f"origin/{target_branch}")
    except GitCommandError:
        # final fallback: try main/master
        for fallback in ("main", "master"):
            if fallback == target_branch:
                continue
            try:
                if fallback in repo.heads:
                    repo.git.checkout(fallback)
                else:
                    repo.git.checkout("-b", fallback, f"origin/{fallback}")
                repo.git.reset("--hard", f"origin/{fallback}")
                target_branch = fallback
                break
            except GitCommandError:
                continue
        else:
            raise

    commit_sha = repo.head.commit.hexsha[:12]
    return dest, commit_sha

def iter_text_files(root: str):
    import os

    root = os.path.abspath(root)

    skip_dirs = {
        ".git",
        ".repos",              # critical: avoid indexing clones folder if nested
        "node_modules",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        ".tox",
        "site-packages",
    }

    allowed_ext = {
        ".md", ".rst", ".txt",
        ".py", ".pyi",
        ".js", ".ts", ".tsx", ".jsx",
        ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp",
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
        ".sh", ".bash", ".ps1",
        ".dockerfile", "dockerfile",
    }

    for dirpath, dirnames, filenames in os.walk(root):
        # prune directories in-place
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for fn in filenames:
            full_path = os.path.join(dirpath, fn)

            # extension check (special-case Dockerfile)
            lower = fn.lower()
            ext = os.path.splitext(lower)[1]
            if lower == "dockerfile":
                pass
            elif ext not in allowed_ext:
                continue

            # return repo-relative path for stable metadata + UI
            rel_path = os.path.relpath(full_path, root).replace("\\", "/")

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    text = f.read()
                if text.strip():
                    yield rel_path, text
            except Exception:
                continue

