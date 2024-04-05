"""Utilities checking for platform features."""
import platform
import os
import shutil
from pathlib import Path


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

def is_installed(lib_name: str) -> bool:
    lib = shutil.which(lib_name)
    if lib is None:
        return False
    global_path = Path(lib)
    # else check if path is valid and has the correct access rights
    return global_path.exists() and os.access(global_path, os.X_OK)
