import argparse
import sys

from .billing import bill


def main() -> None:
    p = argparse.ArgumentParser(description="ConEd billing utility")
    p.add_argument(
        "load_csv", help="CSV with columns: ts (ISO timestamp with UTC offset), kW (float)"
    )
    p.add_argument("tariff", help="YAML file describing tariff")
    p.add_argument("-o", "--out", help="Output CSV (default: stdout)")
    p.add_argument(
        "--interval", default="1h", help="interval duration: 5min, 15min, 30min or 1h (default 1h)"
    )
    p.add_argument(
        "--label",
        choices=["start", "end"],
        default="start",
        help="timestamps mark interval start (default) or end",
    )
    args = p.parse_args()

    result = bill(args.load_csv, args.tariff, interval=args.interval, label=args.label)
    if args.out:
        result.to_csv(args.out, index=True)
    else:
        result.to_csv(sys.stdout, index=True)


if __name__ == "__main__":  # pragma: no cover
    main()
