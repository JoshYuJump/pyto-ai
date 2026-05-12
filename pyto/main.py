"""PyTo Code - CLI."""

import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="pyto",
        description="PyTo Code - A lightweight, extensible Python-first Code Agent framework",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add commit subcommand
    commit_parser = subparsers.add_parser(
        "commit", help="Submit code and create merge request (MR) workflow"
    )
    commit_parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip code review confirmation (not recommended)",
    )

    # Parse arguments
    args = parser.parse_args()

    # Handle commands
    if args.command == "commit":
        try:
            from pyto.commands import commit

            commit(args)
        except ImportError:
            print("❌ Error: pyto package not found. Please install the package first.")
            print("Run: pip install -e .")
            sys.exit(1)
    elif args.command is None:
        print("PyTo Code - A lightweight, extensible Python-first Code Agent framework")
        print("Use 'pyto --help' for available commands")
        print("Available commands:")
        print("  commit    Submit code and create merge request (MR) workflow")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
