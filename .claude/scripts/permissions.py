#!/usr/bin/env python3
"""Manage a run's permissions file, `<git common dir>/claude-permissions/<connector>.json`.

The file lives in the repository's shared `.git` directory so every worktree of
the repo reads the same one. It records the user's questionnaire answers for
one connector, for one run, and is what `.claude/hooks/permission-gate.py`
checks before any live provider call. Only the orchestrating skill runs this,
and only from the user's live answers.

  permissions.py grant  <connector> --mode human-in-the-loop|autonomous --seeding assistant|user|none
  permissions.py stamp  <connector>    # after the credential checkpoint: binds the permission to
                                       # the committed config.yaml (refuses if it is dirty/untracked)
  permissions.py revoke <connector>    # at hand-off
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from typing import cast

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


class Args(argparse.Namespace):
    """The parsed command line; `mode` and `seeding` are set only for `grant`."""

    cmd: str = ""
    connector_slug: str = ""
    mode: str = ""
    seeding: str = ""


def path(connector_slug: str) -> str:
    common = subprocess.run(
        ["git", "-C", ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if common.returncode != 0:
        sys.exit(f"{ROOT} is not inside a git repository: {common.stderr.strip()}")
    return os.path.join(
        common.stdout.strip(), "claude-permissions", connector_slug + ".json"
    )


def load(connector_slug: str) -> dict[str, str]:
    p = path(connector_slug)
    if not os.path.isfile(p):
        sys.exit(f"no permissions file for {connector_slug}; run `grant` first")
    with open(p) as fh:
        return cast(dict[str, str], json.load(fh))


def save(connector_slug: str, data: dict[str, str]) -> None:
    p = path(connector_slug)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        json.dump(data, fh, indent=2)
        _ = fh.write("\n")
    print(f"{p}: {json.dumps(data)}")


def grant(args: Args) -> None:
    save(args.connector_slug, {"mode": args.mode, "seeding": args.seeding})


def stamp(args: Args) -> None:
    data = load(args.connector_slug)
    cdir = os.path.join(ROOT, args.connector_slug)
    cfg = os.path.join(cdir, "config.yaml")
    if not os.path.isfile(cfg):
        sys.exit(f"{args.connector_slug}/config.yaml does not exist")
    ls_files = subprocess.run(
        ["git", "-C", cdir, "ls-files", "--error-unmatch", "config.yaml"],
        capture_output=True,
    )
    tracked = ls_files.returncode == 0
    status = subprocess.run(
        ["git", "-C", cdir, "status", "--porcelain", "--", "config.yaml"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not tracked or status:
        sys.exit(
            (
                f"{args.connector_slug}/config.yaml is {'untracked' if not tracked else 'modified'}; "
                "the user must commit it before permission can be bound to it"
            )
        )
    with open(cfg, "rb") as fh:
        data["config_sha256"] = hashlib.sha256(fh.read()).hexdigest()
    save(args.connector_slug, data)


def revoke(args: Args) -> None:
    p = path(args.connector_slug)
    if os.path.isfile(p):
        os.remove(p)
    print(f"removed {p}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grant")
    _ = g.add_argument("connector_slug", metavar="connector")
    _ = g.add_argument(
        "--mode", required=True, choices=["human-in-the-loop", "autonomous"]
    )
    _ = g.add_argument(
        "--seeding", required=True, choices=["assistant", "user", "none"]
    )

    s = sub.add_parser("stamp")
    _ = s.add_argument("connector_slug", metavar="connector")

    r = sub.add_parser("revoke")
    _ = r.add_argument("connector_slug", metavar="connector")

    args = ap.parse_args(namespace=Args())
    handlers = {"grant": grant, "stamp": stamp, "revoke": revoke}
    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
