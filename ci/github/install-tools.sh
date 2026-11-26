#!/bin/sh
# Install what PackagingOnLinux needs to build the requested formats: Python 3 and the
# packaging tools (ci/github/plan.py lists them per package manager). Used by
# .github/workflows/package.yml on the runner, and in the layer it adds on top of the
# project's build image.
#
#   install-tools.sh "<apt packages>" "<dnf packages>"
#
# With CHECK_PYTHON=1, fails when python3 is older than 3.11 (on the runner, Python comes
# from actions/setup-python instead).
set -eu

apt_packages="${1:-}"
dnf_packages="${2:-}"

sudo=""
if [ "$(id -u)" != 0 ]; then
  sudo=sudo
fi

# Word splitting of the package lists is wanted below.
# shellcheck disable=SC2086
if command -v apt-get >/dev/null 2>&1; then
  $sudo apt-get update
  DEBIAN_FRONTEND=noninteractive $sudo apt-get install -y --no-install-recommends \
    python3 ca-certificates $apt_packages
elif command -v dnf >/dev/null 2>&1; then
  $sudo dnf install -y python3 findutils tar gzip $dnf_packages
else
  echo "error: the build image needs apt-get (Debian, Ubuntu) or dnf (Fedora, RHEL) to install the packaging tools" >&2
  exit 1
fi

if [ "${CHECK_PYTHON:-}" = 1 ] && ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "error: PackagingOnLinux needs Python >= 3.11, the build image has $(python3 --version 2>&1)" >&2
  exit 1
fi
