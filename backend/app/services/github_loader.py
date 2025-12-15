import os
import re
from git import Repo, GitCommandError


def safe_repo_id(url: str) -> str:
    """
    Turns https://github.com/user/repo(.git) into user_repo
    Falls back to a sanitized string if it doesn't match.
    """
    m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not m:
        return re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")

    owner = m.group(1)
    repo = m.group(2).replace(".git", "")
    return f"{owner}_{repo}"

def clone_or_update(repo_url: str, repos_dir: str, branch: str | None = None) -> tuple[str, str]:
    """
    Option A:
      - If repo not present locally: clone it.
      - If repo exists: fetch + checkout target branch + pull.
    Returns: (local_repo_path, commit_sha_short)
    """
    os.makedirs(repos_dir, exist_ok=True)
    repo_id = safe_repo_id(repo_url)
    dest = os.path.join(repos_dir, repo_id)

    if not os.path.exists(dest):
        repo = Repo.clone_from(repo_url, dest)
    else:
        repo = Repo(dest)

        # Ensure origin points to the URL we were asked to ingest
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

    # Always fetch latest refs
    try:
        repo.remotes.origin.fetch(prune=True)
    except GitCommandError:
        # If origin remote missing/misconfigured, re-add it
        if "origin" not in [r.name for r in repo.remotes]:
            repo.create_remote("origin", repo_url)
        repo.remotes.origin.fetch(prune=True)

    # Determine which branch to use
    target_branch = branch
    if not target_branch:
        # Try to infer default branch from origin/HEAD
        try:
            head_ref = repo.git.symbolic_ref("refs/remotes/origin/HEAD")  # e.g. refs/remotes/origin/main
            target_branch = head_ref.split("/")[-1]
        except Exception:
            # fallback
            target_branch = "main"

    # Checkout branch locally (create it if needed), then pull
    try:
        if target_branch in repo.heads:
            repo.git.checkout(target_branch)
        else:
            repo.git.checkout("-b", target_branch, f"origin/{target_branch}")

        # Make ingestion deterministic: match remote exactly
        repo.git.reset("--hard", f"origin/{target_branch}")
    except GitCommandError:
        # common fallback: branch might be "master"
        if target_branch != "master":
            target_branch = "master"
            if target_branch in repo.heads:
                repo.git.checkout(target_branch)
            else:
                repo.git.checkout("-b", target_branch, f"origin/{target_branch}")
            repo.git.reset("--hard", f"origin/{target_branch}")
        else:
            raise

    commit_sha = repo.head.commit.hexsha[:12]
    return dest, commit_sha
