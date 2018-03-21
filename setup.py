#!/usb/bin/python

"""Setup for naaman."""

from setuptools import setup, find_packages
import os

__pkg_name__ = "naaman"
with open(os.path.join(__pkg_name__, "version.py")) as v_file:
    exec(v_file.read())

long_description = ""

setup(
    author="Sean Enck",
    author_email="enckse@gmail.com",
    name=__pkg_name__,
    version=__version__,
    description="N(ot) A(nother) A(UR) Man(ager)",
    long_description="naaman is an AUR manager that provides a pacman-like interface",
    url='https://github.com/enckse/naaman',
    license='MIT',
    python_requires='>=3',
    packages=[__pkg_name__],
    entry_points={
        'console_scripts': [
            'naaman = naaman.naaman:main',
        ],
    },
)
