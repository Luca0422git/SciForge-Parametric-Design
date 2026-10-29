#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# The one environment the GUI tests run in: the same virtual screen, fonts and Qt settings on
# GitHub's runners (the tests workflow and the build's scenario parts) and in a local or
# Claude sandbox run, so a scenario sees the same window, dialog sizes and pixels everywhere.
#
#   tools/sciforge/gui_env.sh --install   install what it needs (CI; apt-get with sudo)
#   source tools/sciforge/gui_env.sh      set the variables (run_tests.sh does this itself)
#   tools/sciforge/gui_env.sh --print     show them
#
# What it fixes: an Xvfb screen of 1920 x 1200 at 96 DPI, no window manager (none on CI
# either), Qt at scale 1 with 96 DPI fonts, Mesa's software OpenGL, and only the DejaVu fonts
# (fontconfig sees nothing else, so a sandbox with 100 fonts and a runner with others draw
# the same text). Differences from Luca's Windows PC that no setting removes: Windows draws
# with Segoe UI at its own scale, a GPU renders the 3D view and a window manager places
# dialogs. A scenario whose clicks depend on a dialog's size says so in a comment.

_sciforge_gui_env_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_sciforge_gui_env_fonts=/usr/share/fonts/truetype/dejavu

if [ "${1:-}" = "--install" ]; then
    set -e
    # xvfb + xauth: the virtual screen; libgl1-mesa-dri: software OpenGL; fonts-dejavu-core:
    # the one font family; python3-numpy: the simulation results' unit tests
    sudo apt-get update -qq
    sudo apt-get install -y -qq xvfb xauth libgl1-mesa-dri fonts-dejavu-core python3-numpy
    exit 0
fi

export SCIFORGE_XVFB_ARGS="-screen 0 1920x1200x24 -dpi 96 -nolisten tcp"
export QT_QPA_PLATFORM=xcb
export QT_SCALE_FACTOR=1
export QT_ENABLE_HIGHDPI_SCALING=0
export QT_FONT_DPI=96
export LIBGL_ALWAYS_SOFTWARE=1
export LANG=C.UTF-8
export TZ=UTC

if [ -d "${_sciforge_gui_env_fonts}" ]; then
    _sciforge_gui_env_dir="${SCIFORGE_GUI_ENV_DIR:-${_sciforge_gui_env_repo}/.sciforge-cache/gui-env}"
    mkdir -p "${_sciforge_gui_env_dir}/fontcache"
    cat > "${_sciforge_gui_env_dir}/fonts.conf" <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>${_sciforge_gui_env_fonts}</dir>
  <cachedir>${_sciforge_gui_env_dir}/fontcache</cachedir>
  <alias><family>sans-serif</family><prefer><family>DejaVu Sans</family></prefer></alias>
  <alias><family>serif</family><prefer><family>DejaVu Serif</family></prefer></alias>
  <alias><family>monospace</family><prefer><family>DejaVu Sans Mono</family></prefer></alias>
</fontconfig>
EOF
    export FONTCONFIG_FILE="${_sciforge_gui_env_dir}/fonts.conf"
else
    echo "[SciForge] gui_env: ${_sciforge_gui_env_fonts} missing (install fonts-dejavu-core:" \
        "tools/sciforge/gui_env.sh --install); the GUI tests use whatever fonts this machine has" >&2
fi

if [ "${1:-}" = "--print" ]; then
    for var in SCIFORGE_XVFB_ARGS QT_QPA_PLATFORM QT_SCALE_FACTOR QT_ENABLE_HIGHDPI_SCALING \
        QT_FONT_DPI LIBGL_ALWAYS_SOFTWARE LANG TZ FONTCONFIG_FILE; do
        echo "${var}=${!var:-}"
    done
fi
