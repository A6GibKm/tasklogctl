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
    node: str
    pid: int
    # The Unix process start time from `/proc/pid/stat`
    pstart: int
    startime: None | int  # epoch
    task_id: int | None
    worker_type: str
    worker_id: None | str
    authid: str
    rel_path: str

    def __init__(self, inner):
        self.path = inner
        self.upid = inner.name

        comps = self.upid.split(":")

        self.node = comps[1]
        self.pid = int(comps[2], 16)
        self.pstart = int(comps[3], 16)

        is_pve = len(comps) == 9

        if is_pve:
            self.task_id = None
            self.starttime = int(comps[4], 16)
            self.worker_type = comps[5]
            self.worker_id = comps[6]
            self.authid = comps[7]
        else:  # is a PBS
            self.task_id = int(comps[4], 16)
            self.starttime = int(comps[5], 16)
            self.worker_type = comps[6]
            self.worker_id = comps[7]
            self.authid = comps[8]

    def starttime_h(self):
        return strftime("%Y-%m-%d %H:%M:%S", localtime(self.starttime))

    def rel_path(self) -> Path:
        return Path(self.path.parent.name).joinpath(self.path.name)


class FilterArgs:
    since: None | int = None
    until: None | int = None
    filters: list[str] = []
    grep: list[str] = []


class Args:
    since: None | str = None
    until: None | str = None
    filter: list[str] = []
    grep: list[str] = []
    product: str | None = None
    directory: Path = Path("/var/log/pve/tasks")

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

    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        help="Where the tasks are stored. Defaults to /var/log/pve/tasks",
        default=Path("/var/log/pve/tasks"),
    )
    parser.add_argument(
        "-f",
        "--filter",
        action="append",
        help="Filters. for example -f '105' for tasks related to the a guest with a VMID of '105' or 'qmsnapshot' for snapshot tasks",
    )
    parser.add_argument(
        "--since",
        nargs="?",
        help="The starting date, for example '2025-11-24 15:24:11'",
    )
    parser.add_argument("--until", nargs="?", help="See --since")
    parser.add_argument(
        "-g",
        "--grep",
        nargs="?",
        help="Only lists files containing this expression",
        action="append",
    )

    args = Args()
    parser.parse_args(namespace=args)

    return args


def list_active(directory: Path, args: FilterArgs) -> Iterable[Upid]:
    upids = [Upid(p) for p in directory.glob("?*/*")]

    def sort_fn(upid):
        return upid.starttime

    def filter_fn(upid):
        if (
            (filters := args.filters)
            and upid.worker_type not in filters
            and upid.worker_id not in filters
        ):
            return False

        if (since := args.since) and upid.starttime < since:
            return False

        if (until := args.until) and upid.starttime > until:
            return False

        for g in args.grep:
            if not contains(upid.path, g):
                return False

        return True

    upids = filter(filter_fn, upids)
    upids = sorted(upids, key=sort_fn)

    return upids


def contains(file: Path, query: str) -> bool:
    with open(file, "r") as fp:
        # read all lines using readline()
        lines = fp.readlines()
        for row in lines:
            # check if string present on a current line
            if row.find(query) != -1:
                return True

    return False


def print_active(upids: Iterable[Upid]) -> None:
    headers = ["starttime", "type", "path"]
    columns = [[u.starttime_h(), u.worker_type, f"'{u.rel_path()}'"] for u in upids]
    table = tabulate(columns, headers=headers)
    print(table)


def main():
    args = parse_args()

    filter_args = FilterArgs()
    filter_args.since = args.since_epoch()
    filter_args.until = args.until_epoch()
    filter_args.filters = args.filter
    filter_args.grep = args.grep

    active = list_active(args.directory, filter_args)
    print_active(active)


if __name__ == "__main__":
    main()
