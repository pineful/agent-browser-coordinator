"""Installed command-line entry point."""
import sys
from .coordinator import VERSION, main as coordinator_main
def main():
    if sys.argv[1:] == ["--version"]:
        print(VERSION)
        return
    coordinator_main()
