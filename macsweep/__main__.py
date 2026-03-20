import sys

from .cli import build_parser, normalize_argv


def main():
    raw_argv = normalize_argv(sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    args.func(args)


if __name__ == "__main__":
    main()
