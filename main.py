import argparse
from dotenv import load_dotenv
from src.scheduler import run_scheduler
from src.pipeline import run_pipeline_once


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-once", action="store_true", help="Generate and upload a single short now")
    args = parser.parse_args()

    if args.run_once:
        run_pipeline_once()
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
