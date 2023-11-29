import os
import os.path

from setuptools import find_packages, setup

BASEDIR = os.path.abspath(os.path.dirname(__file__))


def required(requirements_file):
    """Read requirements file and remove comments and empty lines."""
    with open(os.path.join(BASEDIR, requirements_file), "r") as f:
        requirements = f.read().splitlines()
        return [pkg for pkg in requirements if pkg.strip() and not pkg.startswith("#")]


setup(
    name="core",
    version="4.0.0",
    install_requires=required("requirements/requirements.txt"),
    packages=find_packages(include=["core*"]),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "core-voice-client=core.client.voice.__main__:main",  # VOICE INPUT
            "core-messagebus=core.messagebus.service.__main__:main",  # MESSAGEBUS
            "core-skills=core.skills.__main__:main",  # SKILLS
            "core-audio=core.audio.__main__:main",  # AUDIO OUTPUT
            # TODO audio and echo are broken
            "core-echo-observer=core.messagebus.client.ws:echo",
            "core-audio-test=core.util.audio_test:main",
            "core-enclosure-client=core.client.enclosure.__main__:main",  # ENCLOSURE
            "core-cli-client=core.client.text.__main__:main",  # CORE contact with MB
        ]
    },
)
