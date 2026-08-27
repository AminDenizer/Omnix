import sys
import subprocess

if __name__ == "__main__":
    cmd = [sys.executable, "-m", "pytest", "tests", "-v"]
    print("[INFO] Running Omnix PyTest Suite...")
    res = subprocess.run(cmd)
    sys.exit(res.returncode)
