from setuptools import setup, find_packages
import os
import os.path

BASEDIR = os.path.abspath(os.path.dirname(__file__))


def get_version() -> str:
    """ Find the version of core"""
    version = None
    version_file = os.path.join(BASEDIR, 'core', 'version', '__init__.py')
    major, minor, build = (None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'CORE_VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'CORE_VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'CORE_VERSION_BUILD' in line:
                build = line.split('=')[1].strip()

            if ((major and minor and build) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = '.'.join([major, minor, build])

    return version


def required(requirements_file):
    """ Read requirements file and remove comments and empty lines. """
    with open(os.path.join(BASEDIR, requirements_file), 'r') as f:
        requirements = f.read().splitlines()
        if 'MYCROFT_LOOSE_REQUIREMENTS' in os.environ:
            print('USING LOOSE REQUIREMENTS!')
            requirements = [r.replace('==', '>=') for r in requirements]
        return [pkg for pkg in requirements
                if pkg.strip() and not pkg.startswith("#")]


setup(
    name='core',
    version=get_version(),
    install_requires=required('requirements/requirements.txt'),
    extras_require={
        'audio-backend': required('requirements/extra-audiobackend.txt'),
        'stt': required('requirements/extra-stt.txt')
    },
    packages=find_packages(include=['core*']),
    include_package_data=True,

    entry_points={
        'console_scripts': [
            'core-speech-client=core.client.speech.__main__:main',  # SPEECH
            'core-messagebus=core.messagebus.service.__main__:main',  # MESSAGEBUS
            'core-skills=core.skills.__main__:main',  # SKILLS
            'core-audio=core.audio.__main__:main',  # VOICE
            'core-echo-observer=core.messagebus.client.ws:echo',
            'core-audio-test=core.util.audio_test:main',
            'core-enclosure-client=core.client.enclosure.__main__:main',  # ENCLOSURE
            'core-cli-client=core.client.text.__main__:main'  # CORE contact with MB
        ]
    }
)
