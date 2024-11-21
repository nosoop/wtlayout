#!/usr/bin/python3

import dataclasses
import enum
import itertools
from typing import Iterator, TypeVar

T = TypeVar("T")


def iterjoin(sep: T, iterables: Iterator[T]) -> Iterator[T]:
    """
    Yields iterable items, yielding a separator between each iterable after the first.

    [ a, b, c ] -> iter(a, sep, b, sep, c)
    """
    yield next(iterables)
    for iter in iterables:
        yield sep
        yield iter


def subcmd_join(*cmds: list[str]) -> list[str]:
    """
    Given a list of subcmds (which itself a list of args), returns a flattened arg list with
    semicolons in between each subcmd.

    [ [ a, b, c ], [ d, e, f ] ] -> iter(a, b, c, ';', d, e, f)
    """
    return list(itertools.chain.from_iterable(iterjoin([";"], iter(cmds))))


def pairwise_longest(iterable: Iterator[T]) -> Iterator[tuple[T, T]]:
    "s -> (s0,s1), (s1,s2), (s2, s3), ..., (sN-1,sN), (sN,None)"
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.zip_longest(a, b, fillvalue=None)


class Action:
    def command(self) -> list[str]:
        raise NotImplementedError


@dataclasses.dataclass
class Window(Action):
    subcmds: list[Action]

    def __init__(self, *subcmds: Action):
        self.subcmds = list(subcmds)

    def command(self) -> list[str]:
        # pop the first subcommand so the delimiter isn't inserted until after the first command
        # otherwise WT will open a tab up front
        return subcmd_join(
            ["wt", "-w", "0"] + self.subcmds[0].command(),
            *(s.command() for s in self.subcmds[1:]),
        )


@dataclasses.dataclass
class Pane(Action):
    """
    Holds options available to both new-tab and split-pane commands.
    """

    title: str | None = None
    starting_directory: str | None = None
    profile: str | None = None
    process: list[str] | None = None
    tab_color: int | None = None

    @property
    def num_subpanes(self) -> int:
        return 1

    @property
    def root(self) -> "Pane":
        return self

    def options(self) -> list[str]:
        # this needs to be executed last since it includes the process string
        result = []
        if self.title:
            result.extend(["--title", self.title])
        if self.starting_directory:
            result.extend(["-d", self.starting_directory])
        if self.profile:
            result.extend(["-p", self.profile])
        if self.tab_color:
            result.extend(["--tabColor", "#{:0>6x}".format(self.tab_color)])
        if self.process:
            result.extend(self.process)
        return result


@dataclasses.dataclass
class Tab(Pane):
    def command(self) -> list[str]:
        return ["nt"] + self.options()


class SplitDirection(enum.Enum):
    HORIZONTAL = enum.auto()
    VERTICAL = enum.auto()


@dataclasses.dataclass
class LayoutTab(Action):
    # can have a regular Pane or a PaneGroup
    pane: Pane = dataclasses.field(default_factory=Pane)

    def command(self) -> list[str]:
        return ["nt"] + self.pane.options()


class LayoutDirection(enum.Enum):
    ROW = enum.auto()  # items are inserted from left to right
    COLUMN = enum.auto()  # items are inserted from top to bottom


@dataclasses.dataclass
class PaneGroup:
    """
    A group of panes or nested pane groups.  Panes are created in order from left to right, top
    to bottom; this is so we don't have to backtrack and keep track of pane layout.
    """

    layout: LayoutDirection  # we need to know the orientation to move-focus in the correct direction
    panes: list[Pane]

    # how much of the space in the group should be occupied by the given pane, in proportion to the total
    # len(weights) == len(panes)
    weights: list[float] | None = None

    @property
    def num_subpanes(self) -> int:
        return len(self.panes)

    @property
    def root(self) -> Action:
        # get the deepest panel in the first position
        # (this is the top-left panel, which is the first one before panes are split out)
        return self.panes[0].root

    def sibling_options(self) -> list[str]:
        commands = []

        orientation, focus_prev, focus_next = "-V", "left", "right"
        if self.layout == LayoutDirection.COLUMN:
            orientation, focus_prev, focus_next = "-H", "up", "down"

        # compute the split amount required on each split
        if not self.weights:
            # split evenly; previous pane takes 1/n, 1/(n-1), 1/(n-2), ..., 1/2 of the remaining space
            split_weights: list[float] = [
                n / (n + 1) for n in range(self.num_subpanes - 1, 0, -1)
            ]
        else:
            # split so current pane takes P% of the space (and next pane is 100-P%)
            # P is (fraction of current / remaining weights)
            split_weights = [
                1 - (self.weights[n] / sum(self.weights[n:]))
                for n in range(self.num_subpanes - 1)
            ]

        for w, (pane_prev, pane) in itertools.zip_longest(
            split_weights, pairwise_longest(self.panes), fillvalue=None
        ):
            if pane:
                # create the next pane before working on our previous one to finalize positioning
                commands.append(
                    ["sp", orientation, "-s", str(round(w, 4))] + pane.root.options()
                )

            # perform nested split operations if necessary
            if pane_prev.num_subpanes > 1:
                # split-pane focuses the new pane, so we have to focus the previous pane before
                # any nested splitting occurs; if we are at the end, we don't have a pane, so we
                # just operate on the the currently focused one
                if pane:
                    commands.append(["mf", focus_prev])

                commands.append(pane_prev.sibling_options())

                if pane:
                    commands.append(["mf", focus_next])

        return subcmd_join(*commands)

    def options(self) -> list[str]:
        # the first pane needs to have its options passed directly, since it's for a previous command
        # (either new-tab or split-pane)
        commands = [self.panes[0].root.options()] + [self.sibling_options()]
        return subcmd_join(*commands)
