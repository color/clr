__version__ = "0.1.0"

def main():
    """This is the main entry point for the tool."""
    import sys
    from . import tool
    tool.main(sys.argv)

def call(cmd, *args, **kwargs):
    """Call the given command with the given args and kwargs."""
    from . import tool
    tool.call(cmd, *args, **kwargs)
