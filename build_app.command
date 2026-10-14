#!/bin/bash
# Builds "Transducer Toolkit.app" (with icon) and copies it to your Desktop.
# Needs Python 3 with tkinter (python.org installer, or: brew install python-tk).
cd "$(dirname "$0")" || exit 1

fail() {
  echo
  echo "Build failed: $1"
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
}

PY="$(command -v python3)"
[ -z "$PY" ] && fail "python3 not found. Install Python 3 from python.org."

echo "[1/5] Checking tkinter..."
"$PY" -c "import tkinter" 2>/dev/null || fail "this Python has no tkinter. Install Python from python.org (or: brew install python-tk)."

echo "[2/5] Creating build environment..."
"$PY" -m venv .buildenv || fail "could not create the environment."
source .buildenv/bin/activate || fail "could not activate the environment."

echo "[3/5] Installing packages (numpy, matplotlib, pyinstaller)..."
python -m pip install --upgrade pip || fail "pip upgrade failed."
pip install numpy matplotlib pyinstaller || fail "package installation failed."

echo "[4/5] Building the app (takes a few minutes)..."
pyinstaller --windowed --noconfirm --clean \
  --name "Transducer Toolkit" \
  --icon icon.icns \
  --add-data "icon.png:." \
  --hidden-import matplotlib.backends.backend_tkagg \
  transducer_toolkit.py || fail "PyInstaller failed."

echo "[5/5] Copying to Desktop..."
rm -rf "$HOME/Desktop/Transducer Toolkit.app"
cp -R "dist/Transducer Toolkit.app" "$HOME/Desktop/" || fail "could not copy to the Desktop."

echo
echo "Done. 'Transducer Toolkit.app' is on your Desktop."
read -n 1 -s -r -p "Press any key to close..."
