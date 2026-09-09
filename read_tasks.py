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
from time import strftime, localtime, gmtime
from tabulate import tabulate
from pathlib import Path

from collections.abc import Iterable


class EpochWithTz:
    epoch: int = 0
    offset: float | None = None

    def __init__(self, epoch):
        self.epoch = epoch


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

    def starttime_h(self, offset: float | None) -> str:
        if offset is None:
            return strftime("%Y-%m-%d %H:%M:%S", localtime(self.starttime))

        return strftime("%Y-%m-%d %H:%M:%S", gmtime(self.starttime + offset))

    def rel_path(self) -> Path:
        return Path(self.path.parent.name).joinpath(self.path.name)


class FilterArgs:
    since: None | int = None
    until: None | int = None
    filters: list[str] = []
    exclude_filters: list[str] = []
    grep: list[str] = []


class Args:
    since: None | str = None
    until: None | str = None
    filter: list[str] = []
    exclude_filter: list[str] = []
    grep: list[str] = []
    product: str | None = None
    directories: list[Path] = []

    def since_epoch(self) -> None | EpochWithTz:
        if since := self.since:
            dt = parser.parse(since)
            epoch = EpochWithTz(dt.timestamp())
            if tzinfo := dt.tzinfo:
                epoch.offset = tzinfo._offset.seconds

            return epoch

        return None

    def until_epoch(self) -> None | EpochWithTz:
        if until := self.until:
            dt = parser.parse(until)
            epoch = EpochWithTz(dt.timestamp())
            if tzinfo := dt.tzinfo:
                epoch.offset = tzinfo._offset.seconds

            return epoch

        return None


def parse_args() -> Args:
    parser = argparse.ArgumentParser(
        prog="Task Parser",
        description="Parses task logs",
        epilog="An example parsing multiple directories with a called $hostname-task-logs and a +0100 offset:\n\nread_tasks.py --since '2026-08-10 00:00 +1' --until '2026-08-14 17:00 +1' -e vzdump -e hastart -e hastop -e vncproxy -f 140 -f 162 -f 186 -f 110 $(find . -type d -name '*-task-logs' -printf '--directory %p/var/log/pve/tasks/\\n')",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        action="append",
        dest="directories",
        help="Where the tasks are stored. Defaults to /var/log/pve/tasks. Accepts multiple directories",
        default=Path("/var/log/pve/tasks"),
    )
    parser.add_argument(
        "-f",
        "--filter",
        action="append",
        help="Filters. for example -f '105' for tasks related to the a guest with a VMID of '105' or 'qmsnapshot' for snapshot tasks",
    )
    parser.add_argument(
        "-e",
        "--exclude-filter",
        action="append",
        help="Exclude Filters. Similar to --filter but will exclude matches from the result",
    )
    parser.add_argument(
        "--since",
        nargs="?",
        help="The starting date, for example '2025-11-24 15:24:11 +0100'",
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


def list_active(directories: list[Path], args: FilterArgs) -> Iterable[Upid]:
    upids = [Upid(p) for directory in directories for p in directory.glob("?*/*")]

    def sort_fn(upid):
        return upid.starttime

    def filter_fn(upid):
        if (exclude_filters := args.exclude_filters) and (
            upid.worker_type in exclude_filters or upid.worker_id in exclude_filters
        ):
            return False

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


def print_active(upids: Iterable[Upid], offset: float | None) -> None:
    headers = ["starttime", "type", "path"]
    columns = [
        [u.starttime_h(offset), u.worker_type, f"'{u.rel_path()}'"] for u in upids
    ]
    table = tabulate(columns, headers=headers)
    print(table)


def main():
    args = parse_args()

    filter_args = FilterArgs()
    offset = None

    if since_epoch := args.since_epoch():
        filter_args.since = since_epoch.epoch
        offset = since_epoch.offset

    if until_epoch := args.until_epoch():
        filter_args.until = until_epoch.epoch
        offset = until_epoch.offset

    filter_args.filters = args.filter
    filter_args.exclude_filters = args.exclude_filter
    filter_args.grep = args.grep

    directories = [Path("/var/log/pve/tasks")]
    if args.directories:
        directories = args.directories

    active = list_active(directories, filter_args)
    print_active(active, offset)


if __name__ == "__main__":
    main()
