#!/usr/bin/env bash
#
# Print the PEP 440 version for an estuary-cdk wheel built from HEAD.
#
# The base version lives in estuary-cdk/pyproject.toml and the offset comes
# from `git describe`, so cutting a real release means editing the manifest
# and moving the tag together. This script asserts they agree and fails
# otherwise: the alternative is a published wheel whose version silently
# disagrees with the version the repository reads.
#
# `git describe` reports commits since the tag, which PEP 440 spells `.postN`
# -- NOT `.devN`, which sorts *before* the release rather than after it. The
# commit lands in the local segment, so every wheel from `main` is visibly a
# development build and can never be mistaken for, or uploaded as, the
# release it descends from (PyPI rejects local versions outright).
#
#   v0.2.0-19-gb98c5fe504c  ->  0.2.0.post19+gb98c5fe504c
#   v0.2.0                  ->  0.2.0
#
# Requires tags and history, so the calling job needs `fetch-depth: 0` and
# `fetch-tags: true`; the default shallow checkout has neither.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MANIFEST="${REPO_ROOT}/estuary-cdk/pyproject.toml"

BASE=$(python3 -c '
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    print(tomllib.load(f)["project"]["version"])
' "$MANIFEST")

# `--match "v*"` is load-bearing: the rolling release this feeds publishes
# under a `cdk-dev` tag, which sits on the very commit being described. An
# unfiltered `git describe` would anchor on that instead of on the release
# tag and report an offset of zero forever.
if ! DESCRIBED=$(git describe --tags --match 'v*' --dirty 2>/dev/null); then
    echo "error: no v* tag reachable from HEAD; seed one (e.g. 'git tag v${BASE}') before publishing" >&2
    exit 1
fi

# Strip the `-dirty` suffix before parsing, and re-attach it as a local
# segment component later. It never fires in CI, whose checkouts are clean.
DIRTY=""
if [[ "$DESCRIBED" == *-dirty ]]; then
    DIRTY=".dirty"
    DESCRIBED=${DESCRIBED%-dirty}
fi

# Either `vX.Y.Z` exactly, or `vX.Y.Z-<offset>-g<sha>`.
if [[ "$DESCRIBED" =~ ^v(.+)-([0-9]+)-(g[0-9a-f]+)$ ]]; then
    TAG_VERSION=${BASH_REMATCH[1]}
    OFFSET=${BASH_REMATCH[2]}
    COMMIT=${BASH_REMATCH[3]}
elif [[ "$DESCRIBED" =~ ^v(.+)$ ]]; then
    TAG_VERSION=${BASH_REMATCH[1]}
    OFFSET=0
    COMMIT=""
else
    echo "error: could not parse 'git describe' output '${DESCRIBED}'" >&2
    exit 1
fi

if [ "$TAG_VERSION" != "$BASE" ]; then
    echo "error: nearest tag is v${TAG_VERSION} but estuary-cdk/pyproject.toml declares ${BASE}." >&2
    echo "       Cutting a release means moving both: edit the manifest and tag v${BASE}." >&2
    exit 1
fi

# At the tag itself there is no offset and no commit to record, so the wheel
# carries the bare release version. Publishing only happens on pushes that
# change estuary-cdk/, so this is reachable only by tagging such a commit.
if [ "$OFFSET" -eq 0 ] && [ -z "$DIRTY" ]; then
    echo "${BASE}"
else
    echo "${BASE}.post${OFFSET}+${COMMIT:-g$(git rev-parse --short HEAD)}${DIRTY}"
fi
