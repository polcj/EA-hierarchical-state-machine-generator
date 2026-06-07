import sys
import os

BACKENDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backends")
sys.path.insert(0, BACKENDS_DIR)

import backend_runner

if __name__ == "__main__":
    backend_runner.main()