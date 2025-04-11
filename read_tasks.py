#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "python-dateutil",
#     "tabulate",
# ]
# ///

import argparse

from dateutil import parser
from time import strftime, localtime
from tabulate import tabulate
from pathlib import Path

from collections.abc import Iterable


class Upid:
    inner = None

    def __init__(self, inner):
        self.path = inner
        self.upid = inner.name

        comps = self.upid.split(":")
        self.node = comps[1]
        self.pid = int(comps[2], 16)
        self.pstart = int(comps[3], 16)
        self.task_id = int(comps[4], 16)
        self.starttime = int(comps[5], 16)
        self.wtype = comps[6]
        self.authid = comps[7]

        self.rel_path = f"{comps[3][-2:]}/{self.upid}"

    def starttime_h(self):
        return strftime("%Y-%m-%d %H:%M:%S", localtime(self.starttime))

class FilterArgs:
    since: None | int
    until: None | int
    filters: list[str]

class Args:
    since: None | str = None
    until: None | str = None
    wtype_filter: list[str] = []

    def since_epoch(self) -> None | int:
        if since := self.since:
            epoch = parser.parse(since).timestamp()
            return epoch

        return None

    def until_epoch(self) -> None | int:
        if until := self.until:
            epoch = parser.parse(until).timestamp()
            return epoch

        return None


def parse_args() -> Args:
    parser = argparse.ArgumentParser(prog="Task Parser", description="Parses task logs")

    parser.add_argument("-d", "--directory", type=Path)
    parser.add_argument("-f", "--wtype-filter", action="append")
    parser.add_argument("--since", nargs="?")
    parser.add_argument("--until", nargs="?")
    parser.add_argument("-g", "--grep", nargs="?", help="Only lists files containing this argument")

    args = Args()
    parser.parse_args(namespace=args)

    return args


def list_active(directory: str, args: FilterArgs) -> Iterable[Upid]:
    upids = [Upid(p) for p in directory.glob("?*/*")]

    def sort_fn(upid):
        return upid.starttime

    def filter_fn(upid):
        if args.filters and upid.wtype not in args.filters:
            return False

        if args.since and upid.starttime < args.since:
            return False

        if args.until and upid.starttime < args.until:
            return False

        if args.grep and not contains(upid.path, args.grep):
            return False

        return True

    upids = filter(filter_fn, upids)
    upids = sorted(upids, key=sort_fn)

    return upids


def contains(file: Path, query: str) -> bool:
    with open(file, 'r') as fp:
        # read all lines using readline()
        lines = fp.readlines()
        for row in lines:
            # check if string present on a current line
            if row.find(query) != -1:
                return True

    return False

def print_active(upids: Iterable[Upid]) -> None:
    headers = ["starttime", "type", "path"]
    columns = [[u.starttime_h(), u.wtype, f"'{u.rel_path}'"] for u in upids]
    table = tabulate(columns, headers=headers)
    print(table)


def main():
    args = parse_args()

    filter_args = FilterArgs()
    filter_args.since = args.since_epoch()
    filter_args.until = args.until_epoch()
    filter_args.filters = args.wtype_filter
    filter_args.grep = args.grep

    active = list_active(args.directory, filter_args)
    print_active(active)


if __name__ == "__main__":
    main()
