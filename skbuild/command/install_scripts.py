"""This module defines custom implementation of ``install_scripts`` setuptools
command."""

from setuptools.command.install_scripts import install_scripts as _install_scripts

from ..utils import distribution_hide_listing, distutils_log
from . import set_build_base_mixin


class install_scripts(set_build_base_mixin, _install_scripts):
    """Custom implementation of ``install_scripts`` setuptools command."""

    def run(self, *args, **kwargs):
        """Handle --hide-listing option."""
        with distribution_hide_listing(self.distribution):
            super().run(*args, **kwargs)
        distutils_log.info("copied %d files", len(self.outfiles))
