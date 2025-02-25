"""This module defines functions generally useful in scikit-build."""

import contextlib
import os
from collections import namedtuple
from contextlib import ContextDecorator, contextmanager

from distutils.command.build_py import build_py as distutils_build_py
from distutils.errors import DistutilsTemplateError
from distutils.filelist import FileList
from distutils.text_file import TextFile

try:
    import logging

    import setuptools.logging  # noqa: F401

    distutils_log = logging.getLogger("skbuild")
    distutils_log.setLevel(logging.INFO)
    logging_module = True

except ImportError:
    from distutils import log as distutils_log

    logging_module = False


Distribution = namedtuple("Distribution", "script_name")


def _log_warning(msg, *args):
    try:
        if logging_module:
            distutils_log.warning(msg, *args)
        else:
            distutils_log.warn(msg, *args)  # pylint: disable=deprecated-method
    except ValueError:
        # Setuptools might disconnect the logger. That shouldn't be an error for a warning.
        print(msg % args)


def mkdir_p(path):
    """Ensure directory ``path`` exists. If needed, parent directories
    are created.
    """
    return os.makedirs(path, exist_ok=True)


class push_dir(ContextDecorator):
    """Context manager to change current directory."""

    def __init__(self, directory=None, make_directory=False):
        """
        :param directory:
          Path to set as current working directory. If ``None``
          is passed, ``os.getcwd()`` is used instead.

        :param make_directory:
          If True, ``directory`` is created.
        """
        super().__init__()
        self.directory = directory
        self.make_directory = make_directory
        self.old_cwd = None

    def __enter__(self):
        self.old_cwd = os.getcwd()
        if self.directory:
            if self.make_directory:
                os.makedirs(self.directory, exist_ok=True)
            os.chdir(self.directory)
        return self

    def __exit__(self, typ, val, traceback):
        os.chdir(self.old_cwd)


class PythonModuleFinder(distutils_build_py):
    """Convenience class to search for python modules.

    This class is based on ``distutils.command.build_py.build_by`` and
    provides a specialized version of ``find_all_modules()``.
    """

    # pylint: disable-next=super-init-not-called
    def __init__(self, packages, package_dir, py_modules, alternative_build_base=None):
        """
        :param packages: List of packages to search.
        :param package_dir: Dictionary mapping ``package`` with ``directory``.
        :param py_modules: List of python modules.
        :param alternative_build_base: Additional directory to search in.
        """
        self.packages = packages
        self.package_dir = package_dir
        self.py_modules = py_modules
        self.alternative_build_base = alternative_build_base

        self.distribution = Distribution("setup.py")

    def find_all_modules(self, project_dir=None):
        """Compute the list of all modules that would be built by
        project located in current directory, whether they are
        specified one-module-at-a-time ``py_modules`` or by whole
        packages ``packages``.

        By default, the function will search for modules in the current
        directory. Specifying ``project_dir`` parameter allow to change
        this.

        Return a list of tuples ``(package, module, module_file)``.
        """
        with push_dir(project_dir):
            return super().find_all_modules()

    def find_package_modules(self, package, package_dir):
        """Temporally prepend the ``alternative_build_base`` to ``module_file``.
        Doing so will ensure modules can also be found in other location
        (e.g ``skbuild.constants.CMAKE_INSTALL_DIR``).
        """
        if package_dir != "" and not os.path.exists(package_dir) and self.alternative_build_base is not None:
            package_dir = os.path.join(self.alternative_build_base, package_dir)

        modules = super().find_package_modules(package, package_dir)

        # Strip the alternative base from module_file
        def _strip_directory(entry):
            module_file = entry[2]
            if self.alternative_build_base is not None and module_file.startswith(self.alternative_build_base):
                module_file = module_file[len(self.alternative_build_base) + 1 :]
            return entry[0], entry[1], module_file

        return map(_strip_directory, modules)

    def check_module(self, module, module_file):
        """Return True if ``module_file`` belongs to ``module``."""
        if self.alternative_build_base is not None:
            updated_module_file = os.path.join(self.alternative_build_base, module_file)
            if os.path.exists(updated_module_file):
                module_file = updated_module_file
        if not os.path.isfile(module_file):
            _log_warning("file %s (for module %s) not found", module_file, module)
            return False
        return True


def to_platform_path(path):
    """Return a version of ``path`` where all separator are :attr:`os.sep`"""
    return path.replace("/", os.sep).replace("\\", os.sep) if path is not None else None


def to_unix_path(path):
    """Return a version of ``path`` where all separator are ``/``"""
    return path.replace("\\", "/") if path is not None else None


@contextmanager
def distribution_hide_listing(distribution):
    """Given a ``distribution``, this context manager temporarily
    sets distutils threshold to WARN if ``--hide-listing`` argument
    was provided.

    It yields True if ``--hide-listing`` argument was provided.
    """

    hide_listing = hasattr(distribution, "hide_listing") and distribution.hide_listing

    if logging_module:
        # Setuptools 60.2+, will always be on Python 3.6+
        old_level = distutils_log.getEffectiveLevel()
        if hide_listing:
            distutils_log.setLevel(logging.WARNING)
        try:
            if hide_listing:
                # The classic logger doesn't respond to set_threshold anymore,
                # but it does log info and above to stdout, so let's hide that
                with open(os.devnull, "w", encoding="utf-8") as f, contextlib.redirect_stdout(f):
                    yield hide_listing
            else:
                yield hide_listing
        finally:
            distutils_log.setLevel(old_level)

    else:
        old_threshold = distutils_log._global_log.threshold
        if hide_listing:
            distutils_log.set_threshold(distutils_log.WARN)
        try:
            yield hide_listing
        finally:
            distutils_log.set_threshold(old_threshold)


def parse_manifestin(template):
    """This function parses template file (usually MANIFEST.in)"""
    if not os.path.exists(template):
        return []

    template = TextFile(
        template, strip_comments=1, skip_blanks=1, join_lines=1, lstrip_ws=1, rstrip_ws=1, collapse_join=1
    )

    file_list = FileList()
    try:
        while True:
            line = template.readline()
            if line is None:  # end of file
                break

            try:
                file_list.process_template_line(line)
            # the call above can raise a DistutilsTemplateError for
            # malformed lines, or a ValueError from the lower-level
            # convert_path function
            except (DistutilsTemplateError, ValueError) as msg:
                print(f"{template.filename}, line {template.current_line}: {msg}")
        return file_list.files
    finally:
        template.close()
