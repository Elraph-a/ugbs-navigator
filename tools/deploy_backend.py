"""Deploy the API server to a Hugging Face Docker Space.

    ..\\AI_Lab\\Scripts\\python.exe tools\\deploy_backend.py --dry-run
    ..\\AI_Lab\\Scripts\\python.exe tools\\deploy_backend.py --cors https://your-app.vercel.app

Needs HF_TOKEN (a Hugging Face token with write access) and GROQ_API_KEY in .env.

What it does:
  1. Stages exactly the files the server needs into .tmp/space_bundle -- code,
     the extracted passages, the procedure catalogue -- and nothing else. No raw
     documents, no .env, no enquiry database, no planning material.
  2. Creates the Space if it does not exist (public, Docker SDK).
  3. Stores GROQ_API_KEY as a Space *secret* and the non-sensitive settings as
     Space variables. The key is never uploaded as a file.
  4. Uploads the bundle. The Space then builds the image, which embeds the
     passages and seeds the simulated semester (see deploy/huggingface/Dockerfile).

Never prints the token or the key.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config  # noqa: E402  (also loads .env into the environment)

ROOT = config.PROJECT_ROOT
BUNDLE = ROOT / ".tmp" / "space_bundle"
DEFAULT_SPACE_NAME = "ugbs-navigator-api"

# Relative to the project root. Directories are copied whole, minus caches.
INCLUDE = [
    "backend",
    "core",
    "tools/build_index.py",
    "tools/seed_enquiries.py",
    "data/chunks.json",
    "data/structured",
    "data/synthetic",
    "requirements.txt",
]
FROM_DEPLOY = ["Dockerfile", "README.md"]  # deploy/huggingface/* -> Space root

# Non-secret settings, visible in the Space settings page.
VARIABLES = {
    "LLM_PROVIDER": "groq",
    "GROQ_MODEL": config.settings.groq_model,
    "GROQ_FAST_MODEL": config.settings.groq_fast_model,
}


def stage() -> list[Path]:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for rel in INCLUDE:
        src, dst = ROOT / rel, BUNDLE / rel
        if not src.exists():
            raise SystemExit(f"Missing {rel} - cannot build the bundle.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ignore)
        else:
            shutil.copy2(src, dst)
    for name in FROM_DEPLOY:
        shutil.copy2(ROOT / "deploy" / "huggingface" / name, BUNDLE / name)

    files = sorted(p for p in BUNDLE.rglob("*") if p.is_file())

    # Belt and braces: refuse to upload anything that looks like a secret or
    # material the house rules keep private, even if INCLUDE is edited later.
    forbidden = {".env", "CLAUDE.md", "enquiries.db"}
    leaked = [p for p in files if p.name in forbidden or p.suffix in {".docx", ".pptx", ".pdf"}]
    if leaked:
        raise SystemExit(f"Refusing to upload: {[str(p.relative_to(BUNDLE)) for p in leaked]}")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--space", help=f"owner/name (default: <your username>/{DEFAULT_SPACE_NAME})")
    parser.add_argument("--cors", default="", help="frontend origin(s), comma-separated, e.g. https://x.vercel.app")
    parser.add_argument("--dry-run", action="store_true", help="stage and list files; upload nothing")
    args = parser.parse_args()

    files = stage()
    size = sum(p.stat().st_size for p in files)
    print(f"Staged {len(files)} files ({size / 1024:.0f} KB) in {BUNDLE}")
    for p in files:
        print(f"  {p.relative_to(BUNDLE).as_posix()}")

    if args.dry_run:
        print("\n--dry-run: nothing uploaded.")
        return 0

    token = os.environ.get("HF_TOKEN")
    groq_key = config.settings.groq_api_key
    if not token:
        print("\nHF_TOKEN is not set. Add a write-access token to .env and re-run.")
        return 1
    if not groq_key:
        print("\nGROQ_API_KEY is not set in .env.")
        return 1

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    user = api.whoami()["name"]
    space = args.space or f"{user}/{DEFAULT_SPACE_NAME}"

    api.create_repo(space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    print(f"\nSpace: https://huggingface.co/spaces/{space}")

    api.add_space_secret(space, "GROQ_API_KEY", groq_key)
    variables = dict(VARIABLES)
    if args.cors:
        variables["CORS_ORIGINS"] = args.cors
    for key, value in variables.items():
        api.add_space_variable(space, key, value)
    print(f"Secret set: GROQ_API_KEY.  Variables set: {', '.join(variables)}")

    api.upload_folder(
        folder_path=str(BUNDLE),
        repo_id=space,
        repo_type="space",
        commit_message="Deploy UGBS Service Navigator API",
    )

    host = space.replace("/", "-").replace("_", "-").lower()
    print(f"Uploaded. The Space is now building (first build takes several minutes).")
    print(f"API URL once running: https://{host}.hf.space")
    print(f"Health check:         https://{host}.hf.space/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
