import sys
import os

MOTOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parser")

sys.path.insert(0, MOTOR_DIR)

import state_machine_generator

if __name__ == "__main__":
    state_machine_generator.main()