"""This module defines custom implementation of ``test`` setuptools command."""

from setuptools.command.test import test as _test

from . import set_build_base_mixin


class test(set_build_base_mixin, _test):
    """Custom implementation of ``test`` setuptools command."""

    def run(self, *args, **kwargs):
        """Force ``develop`` command to run."""
        self.run_command("develop")
        super().run(*args, **kwargs)
