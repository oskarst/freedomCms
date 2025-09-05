#!/usr/bin/env python3
"""
Run script for Devall CMS
"""

import subprocess
import sys
import os

def main():
    print("Starting Devall CMS...")
    print("Default login: admin / admin123")
    print("Access at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("-" * 50)

    # Change to the directory containing cms.py
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run the CMS
    try:
        subprocess.run([sys.executable, "cms.py"], check=True)
    except KeyboardInterrupt:
        print("\nCMS stopped.")
    except subprocess.CalledProcessError as e:
        print(f"Error running CMS: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
