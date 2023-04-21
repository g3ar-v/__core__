"""Utilities checking for platform features."""
import platform
import os


def get_arch():
    """ Get architecture string of system. """
    return os.uname()[4]


def get_enclosure():
    """Get platform core is running on
    """
    if 'arm' in platform.machine() and 'Darwin' not in os.uname().sysname:
        return "raspberry pi"
    else:
        return "linux"
