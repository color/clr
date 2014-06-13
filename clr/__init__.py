"""``clr'' command line tool. see ``tool.py'' for more details."""

from __future__ import absolute_import

import sys

from . import tool


def main():
    """This is the main entry point for the tool."""
    tool.main(sys.argv)

def call(cmd, *args, **kwargs):
    """Call the given command with the given args and kwargs."""
    tool.call(cmd, *args, **kwargs)
