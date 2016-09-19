#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""test_setup
----------------------------------

Tests for `skbuild.setup` function.
"""

import textwrap
import os
import pprint
import pytest

from distutils.core import Distribution as distutils_Distribution
from setuptools import Distribution as setuptool_Distribution

from skbuild import setup as skbuild_setup
from skbuild.cmaker import CMAKE_INSTALL_DIR
from skbuild.exceptions import SKBuildError
from skbuild.setuptools_wrap import strip_package
from skbuild.utils import (push_dir, to_platform_path)

from . import (_tmpdir, execute_setup_py, push_argv)


@pytest.mark.parametrize("distribution_type",
                         ['unknown',
                          'py_modules',
                          'packages',
                          'skbuild'
                          ])
def test_distribution_is_pure(distribution_type, tmpdir):

    skbuild_setup_kwargs = {}

    if distribution_type == 'unknown':
        is_pure = False

    elif distribution_type == 'py_modules':
        is_pure = True
        hello_py = tmpdir.join("hello.py")
        hello_py.write("")
        skbuild_setup_kwargs["py_modules"] = ["hello"]

    elif distribution_type == 'packages':
        is_pure = True
        init_py = tmpdir.mkdir("hello").join("__init__.py")
        init_py.write("")
        skbuild_setup_kwargs["packages"] = ["hello"]

    elif distribution_type == 'skbuild':
        is_pure = False
        cmakelists_txt = tmpdir.join("CMakeLists.txt")
        cmakelists_txt.write(
            """
            cmake_minimum_required(VERSION 3.5.0)
            project(test NONE)
            install(CODE "execute_process(
              COMMAND \${CMAKE_COMMAND} -E sleep 0)")
            """
        )
    else:
        raise Exception(
            "Unknown distribution_type: {}".format(distribution_type))

    with push_dir(str(tmpdir)), push_argv(["setup.py", "build"]):
        distribution = skbuild_setup(
            name="test",
            version="0.0.1",
            description="test object returned by setup function",
            author="The scikit-build team",
            license="MIT",
            **skbuild_setup_kwargs
        )
        assert issubclass(distribution.__class__,
                          (distutils_Distribution, setuptool_Distribution))
        assert is_pure == distribution.is_pure()


@pytest.mark.parametrize("cmake_args", [
    [],
    ['--', '-DVAR:STRING=43', '-DVAR_WITH_SPACE:STRING=Ciao Mondo']
])
def test_cmake_args_keyword(cmake_args, capfd):
    tmp_dir = _tmpdir('cmake_args_keyword')

    tmp_dir.join('setup.py').write(textwrap.dedent(
        """
        from skbuild import setup
        setup(
            name="hello",
            version="1.2.3",
            description="a minimal example package",
            author='The scikit-build team',
            license="MIT",
            cmake_args=[
                "-DVAR:STRING=42",
                "-DVAR_WITH_SPACE:STRING=Hello World"
            ]

        )
        """
    ))
    tmp_dir.join('CMakeLists.txt').write(textwrap.dedent(
        """
        cmake_minimum_required(VERSION 3.5.0)
        project(test NONE)
        message(STATUS "VAR[${VAR}]")
        message(STATUS "VAR_WITH_SPACE[${VAR_WITH_SPACE}]")
        install(CODE "execute_process(
          COMMAND \${CMAKE_COMMAND} -E sleep 0)")
        """
    ))

    with execute_setup_py(tmp_dir, ['build'] + cmake_args):
        pass

    out, _ = capfd.readouterr()

    if not cmake_args:
        assert "VAR[42]" in out
        assert "VAR_WITH_SPACE[Hello World]" in out
    else:
        assert "VAR[43]" in out
        assert "VAR_WITH_SPACE[Ciao Mondo]" in out


@pytest.mark.parametrize(
    "cmake_install_dir, expected_failed, error_code_type", (
        (None, True, str),
        ('', True, str),
        (os.getcwd(), True, SKBuildError),
        ('banana', False, str)
    )
)
def test_cmake_install_dir_keyword(
        cmake_install_dir, expected_failed, error_code_type, capsys):

    # -------------------------------------------------------------------------
    # "SOURCE" tree layout:
    #
    # ROOT/
    #
    #     CMakeLists.txt
    #     setup.py
    #
    #     apple/
    #         __init__.py
    #
    # -------------------------------------------------------------------------
    # "BINARY" distribution layout
    #
    # ROOT/
    #
    #     apple/
    #         __init__.py
    #

    tmp_dir = _tmpdir('cmake_install_dir_keyword')

    setup_kwarg = ''
    if cmake_install_dir is not None:
        setup_kwarg = 'cmake_install_dir=\'{}\''.format(cmake_install_dir)

    tmp_dir.join('setup.py').write(textwrap.dedent(
        """
        from skbuild import setup
        setup(
            name="test_cmake_install_dir",
            version="1.2.3",
            description="a package testing use of cmake_install_dir",
            author='The scikit-build team',
            license="MIT",
            packages=['apple', 'banana'],
            {setup_kwarg}
        )
        """.format(setup_kwarg=setup_kwarg)
    ))

    # Install location purposely set to "." so that we can test
    # usage of "cmake_install_dir" skbuild.setup keyword.
    tmp_dir.join('CMakeLists.txt').write(textwrap.dedent(
        """
        cmake_minimum_required(VERSION 3.5.0)
        project(banana)
        file(WRITE "${CMAKE_BINARY_DIR}/__init__.py" "")
        install(FILES "${CMAKE_BINARY_DIR}/__init__.py" DESTINATION ".")
        """
    ))

    tmp_dir.ensure('apple', '__init__.py')

    failed = False
    message = ""
    try:
        with execute_setup_py(tmp_dir, ['build']):
            pass
    except SystemExit as e:
        # Error is not of type SKBuildError, it is expected to be
        # raised by distutils.core.setup
        failed = isinstance(e.code, error_code_type)
        message = str(e)

    out, _ = capsys.readouterr()

    assert failed == expected_failed
    if failed:
        if error_code_type == str:
            assert message == "error: package directory " \
                              "'{}' does not exist".format(
                                    os.path.join(CMAKE_INSTALL_DIR, 'banana'))
        else:
            assert message.strip().startswith(
                "setup parameter 'cmake_install_dir' "
                "is set to an absolute path.")
    else:
        assert "copying {}".format(os.path.join(
            *"_skbuild/cmake-install/banana/__init__.py".split("/"))) in out


@pytest.mark.parametrize("distribution_type", ('pure', 'skbuild'))
def test_script_keyword(distribution_type, capsys):

    # -------------------------------------------------------------------------
    #
    # "SOURCE" tree layout for "pure" distribution:
    #
    # ROOT/
    #     setup.py
    #     foo.py
    #     bar.py
    #
    # "SOURCE" tree layout for "pure" distribution:
    #
    # ROOT/
    #     setup.py
    #     CMakeLists.txt
    #
    # -------------------------------------------------------------------------
    # "BINARY" distribution layout is identical for both
    #
    # ROOT/
    #     foo.py
    #     bar.py
    #

    tmp_dir = _tmpdir('script_keyword')

    tmp_dir.join('setup.py').write(textwrap.dedent(
        """
        from skbuild import setup
        setup(
            name="test_script_keyword",
            version="1.2.3",
            description="a package testing use of script keyword",
            author='The scikit-build team',
            license="MIT",
            scripts=['foo.py', 'bar.py']
        )
        """
    ))

    if distribution_type == 'skbuild':
        tmp_dir.join('CMakeLists.txt').write(textwrap.dedent(
            """
            cmake_minimum_required(VERSION 3.5.0)
            project(foo)
            file(WRITE "${CMAKE_BINARY_DIR}/foo.py" "# foo.py")
            file(WRITE "${CMAKE_BINARY_DIR}/bar.py" "# bar.py")
            install(
                FILES
                    "${CMAKE_BINARY_DIR}/foo.py"
                    "${CMAKE_BINARY_DIR}/bar.py"
                DESTINATION "."
                )
            """
        ))

        messages = [
            "copying _skbuild/cmake-install/{}.py -> "
            "_skbuild/setuptools/scripts-".format(module)
            for module in ['foo', 'bar']]

    elif distribution_type == 'pure':
        tmp_dir.join('foo.py').write("# foo.py")
        tmp_dir.join('bar.py').write("# bar.py")

        messages = [
            "copying {}.py -> "
            "_skbuild/setuptools/scripts-".format(module)
            for module in ['foo', 'bar']]

    with execute_setup_py(tmp_dir, ['build']):
        pass

    out, _ = capsys.readouterr()
    for message in messages:
        assert to_platform_path(message) in out


@pytest.mark.parametrize("distribution_type", ('pure', 'skbuild'))
def test_py_modules_keyword(distribution_type, capsys):

    # -------------------------------------------------------------------------
    #
    # "SOURCE" tree layout for "pure" distribution:
    #
    # ROOT/
    #     setup.py
    #     foo.py
    #     bar.py
    #
    # "SOURCE" tree layout for "pure" distribution:
    #
    # ROOT/
    #     setup.py
    #     CMakeLists.txt
    #
    # -------------------------------------------------------------------------
    # "BINARY" distribution layout is identical for both
    #
    # ROOT/
    #     foo.py
    #     bar.py
    #

    tmp_dir = _tmpdir('py_modules_keyword')

    tmp_dir.join('setup.py').write(textwrap.dedent(
        """
        from skbuild import setup
        setup(
            name="test_py_modules_keyword",
            version="1.2.3",
            description="a package testing use of py_modules keyword",
            author='The scikit-build team',
            license="MIT",
            py_modules=['foo', 'bar']
        )
        """
    ))

    if distribution_type == 'skbuild':
        tmp_dir.join('CMakeLists.txt').write(textwrap.dedent(
            """
            cmake_minimum_required(VERSION 3.5.0)
            project(foobar)
            file(WRITE "${CMAKE_BINARY_DIR}/foo.py" "# foo.py")
            file(WRITE "${CMAKE_BINARY_DIR}/bar.py" "# bar.py")
            install(
                FILES
                    "${CMAKE_BINARY_DIR}/foo.py"
                    "${CMAKE_BINARY_DIR}/bar.py"
                DESTINATION "."
                )
            """
        ))

        messages = [
            "copying _skbuild/cmake-install/{}.py -> "
            "_skbuild/setuptools/lib".format(module)
            for module in ['foo', 'bar']]

    elif distribution_type == 'pure':
        tmp_dir.join('foo.py').write("# foo.py")
        tmp_dir.join('bar.py').write("# bar.py")

        messages = [
            "copying {}.py -> "
            "_skbuild/setuptools/lib".format(module)
            for module in ['foo', 'bar']]

    with execute_setup_py(tmp_dir, ['build']):
        pass

    out, _ = capsys.readouterr()
    for message in messages:
        assert to_platform_path(message) in out


@pytest.mark.parametrize("package_parts, module_file, expected", [
    ([], "", ""),
    ([], "foo/file.py", "foo/file.py"),
    (["foo"], "", ""),
    (["foo"], "", ""),
    (["foo"], "foo/file.py", "file.py"),
    (["foo"], "foo\\file.py", "file.py"),
    (["foo", "bar"], "foo/file.py", "foo/file.py"),
    (["foo", "bar"], "foo/bar/file.py", "file.py"),
    (["foo", "bar"], "foo/bar/baz/file.py", "baz/file.py"),
    (["foo"], "/foo/file.py", "/foo/file.py"),
])
def test_strip_package(package_parts, module_file, expected):
    assert strip_package(package_parts, module_file) == expected


@pytest.mark.parametrize("has_cmake_package", [0, 1])
@pytest.mark.parametrize("has_hybrid_package", [0, 1])
@pytest.mark.parametrize("has_pure_package", [0, 1])
@pytest.mark.parametrize("with_package_base", [0, 1])
def test_setup_inputs(
        has_cmake_package, has_hybrid_package, has_pure_package,
        with_package_base,
        mocker):
    """This test that a project can have a package with some modules
    installed using setup.py and some other modules installed using CMake.
    """

    tmp_dir = _tmpdir('test_setup_inputs')

    package_base = 'base' if with_package_base else ''
    cmake_source_dir = package_base

    if cmake_source_dir and has_cmake_package:
        pytest.skip("unsupported configuration: "
                    "python package fully generated by CMake does *NOT* work. "
                    "At least __init__.py should be in the project source tree")

    # -------------------------------------------------------------------------
    # Here is the "SOURCE" tree layout:
    #
    # ROOT/
    #
    #     setup.py
    #
    #     [<base>/]
    #
    #         pure/
    #             __init__.py
    #             pure.py
    #
    #             data/
    #                 pure.dat                   *NO TEST*
    #
    #     [<cmake_src_dir>/]
    #
    #         hybrid/
    #             CMakeLists.txt
    #             __init__.py
    #             hybrid_pure.dat                *NO TEST*
    #             hybrid_pure.py
    #
    #             data/
    #                 hybrid_data_pure.dat       *NO TEST*
    #
    #             hybrid_2/
    #                 __init__.py
    #                 hybrid_2_pure.py
    #
    #             hybrid_2_pure/
    #                 __init__.py
    #                 hybrid_2_pure_1.py
    #                 hybrid_2_pure_2.py
    #
    #
    # -------------------------------------------------------------------------
    # and here is the "BINARY" distribution layout:
    #
    # The comment "CMake" or "Setuptools" indicates which tool is responsible
    # for placing the file in the tree used to create the binary distribution.
    #
    # ROOT/
    #
    #     cmake/
    #         __init__.py                # CMake
    #         cmake.py                   # CMake
    #
    #     hybrid/
    #         hybrid_cmake.dat           # CMake                  *NO TEST*
    #         hybrid_cmake.py            # CMake
    #
    #         data/
    #             hybrid_data_pure.dat   # CMake or Setuptools    *NO TEST*
    #             hybrid_data_cmake.dat  # CMake                  *NO TEST*
    #
    #         hybrid_2/
    #             __init__.py            # CMake or Setuptools
    #             hybrid_2_pure.py       # CMake or Setuptools
    #             hybrid_2_cmake.py      # CMake
    #
    #         hybrid_2_pure/
    #             __init__.py            # CMake or Setuptools
    #             hybrid_2_pure_1.py     # CMake or Setuptools
    #             hybrid_2_pure_2.py     # CMake or Setuptools
    #
    #     pure/
    #         __init__.py                # Setuptools
    #         pure.py                    # Setuptools
    #
    #         data/
    #             pure.dat               # Setuptools    *NO TEST*

    tmp_dir.join('setup.py').write(textwrap.dedent(
        """
        from skbuild import setup
        #from setuptools import setup
        setup(
            name="test_hybrid_project",
            version="1.2.3",
            description=("an hybrid package mixing files installed by both "
                        "CMake and setuptools"),
            author='The scikit-build team',
            license="MIT",
            cmake_source_dir='{cmake_source_dir}',
            # Arbitrary order of packages
            packages=[
        {p_off}    'pure',
        {h_off}    'hybrid.hybrid_2',
        {h_off}    'hybrid',
        {c_off}    'cmake',
        {p_off}    'hybrid.hybrid_2_pure',
            ],
            #package_data=[
            #    '': ['*.dat']
            #]
            # Arbitrary order of package_dir
            package_dir = {{
        {p_off}    'hybrid.hybrid_2_pure': '{package_base}hybrid/hybrid_2_pure',
        {p_off}    'pure': '{package_base}pure',
        {h_off}    'hybrid': '{package_base}hybrid',
        {h_off}    'hybrid.hybrid_2': '{package_base}hybrid/hybrid_2',
        {c_off}    'cmake': '{package_base}cmake',
            }}
        )
        """.format(
            cmake_source_dir=cmake_source_dir,
            package_base=package_base + '/' if package_base else '',
            c_off='' if has_cmake_package else '#',
            h_off='' if has_hybrid_package else '#',
            p_off='' if has_pure_package else '#'
        )
    ))

    src_dir = tmp_dir.ensure(package_base, dir=1)

    src_dir.join('CMakeLists.txt').write(textwrap.dedent(
        """
        cmake_minimum_required(VERSION 3.5.0)
        project(hybrid)
        set(build_dir ${{CMAKE_BINARY_DIR}})

        {c_off} file(WRITE ${{build_dir}}/__init__.py "")
        {c_off} file(WRITE ${{build_dir}}/cmake.py "")
        {c_off} install(
        {c_off}     FILES
        {c_off}         ${{build_dir}}/__init__.py
        {c_off}         ${{build_dir}}/cmake.py
        {c_off}     DESTINATION cmake
        {c_off}     )

        {h_off} file(WRITE ${{build_dir}}/hybrid_cmake.py "")
        {h_off} install(
        {h_off}     FILES ${{build_dir}}/hybrid_cmake.py
        {h_off}     DESTINATION hybrid)

        {h_off} file(WRITE ${{build_dir}}/hybrid_2_cmake.py "")
        {h_off} install(
        {h_off}     FILES ${{build_dir}}/hybrid_2_cmake.py
        {h_off}     DESTINATION hybrid/hybrid_2)

        install(CODE "message(STATUS \\\"Installation complete\\\")")
        """.format(
            c_off='' if has_cmake_package else '#',
            h_off='' if has_hybrid_package else '#',
            p_off='' if has_pure_package else '#'
        )
    ))

    # List path types: 'c', 'h' or 'p'
    try:
        path_types = list(zip(*filter(
            lambda i: i[1],
            [('c', has_cmake_package),
             ('h', has_hybrid_package),
             ('p', has_pure_package)])))[0]
    except IndexError:
        path_types = []

    def select_paths(annotated_paths):
        """Return a filtered list paths considering ``path_types``.

        `annotated_paths`` is list of tuple ``(type, path)`` where type
        is either `c`, `h` or `p`.

        """
        return filter(lambda i: i[0] in path_types, annotated_paths)

    # Commented paths are the one expected to be installed by CMake. For
    # this reason, corresponding files should NOT be created in the source
    # tree.
    for (type, path) in select_paths([
        # ('c', 'cmake/__init__.py'),
        # ('c', 'cmake/cmake.py'),

        ('h', 'hybrid/__init__.py'),
        # ('h', 'hybrid/hybrid_cmake.dat'),
        # ('h', 'hybrid/hybrid_cmake.py'),
        ('h', 'hybrid/hybrid_pure.dat'),
        ('h', 'hybrid/hybrid_pure.py'),

        # ('h', 'hybrid/data/hybrid_data_cmake.dat'),
        ('h', 'hybrid/data/hybrid_data_pure.dat'),

        ('h', 'hybrid/hybrid_2/__init__.py'),
        # ('h', 'hybrid/hybrid_2/hybrid_2_cmake.py'),
        ('h', 'hybrid/hybrid_2/hybrid_2_pure.py'),

        ('p', 'hybrid/hybrid_2_pure/__init__.py'),
        ('p', 'hybrid/hybrid_2_pure/hybrid_2_pure_1.py'),
        ('p', 'hybrid/hybrid_2_pure/hybrid_2_pure_2.py'),

        ('p', 'pure/__init__.py'),
        ('p', 'pure/pure.py'),

        ('p', 'pure/data/pure.dat'),
    ]):
        assert type in ['p', 'h']
        root = package_base if type == 'p' else cmake_source_dir
        tmp_dir.ensure(os.path.join(root, path))

    # Do not call the real setup function. Instead, replace it with
    # a MagicMock allowing to
    mock_setup = mocker.patch('skbuild.setuptools_wrap.upstream_setup')

    # Convenience print function
    def _pprint(desc, value=None):
        print(
            "-----------------\n"
            "{}:\n"
            "\n"
            "{}\n".format(desc, pprint.pformat(
                setup_kw.get(desc, {}) if value is None else value, indent=2)))

    with execute_setup_py(tmp_dir, ['build']):

        assert mock_setup.call_count == 1
        setup_kw = mock_setup.call_args[1]

        # packages
        expected_packages = []
        if has_cmake_package:
            expected_packages += ['cmake']
        if has_hybrid_package:
            expected_packages += ['hybrid', 'hybrid.hybrid_2']
        if has_pure_package:
            expected_packages += ['hybrid.hybrid_2_pure', 'pure']

        _pprint('expected_packages', expected_packages)
        _pprint('packages')

        # package dir
        expected_package_dir = {
            package: (os.path.join(CMAKE_INSTALL_DIR,
                      package_base,
                      package.replace('.', '/')))
            for package in expected_packages
            }
        _pprint('expected_package_dir', expected_package_dir)
        _pprint('package_dir')

        def prepend_package_base(module_files):
            # return [package_base + module_file
            #         for module_file in module_files]
            return module_files

        # package data
        expected_package_data = {}

        if has_cmake_package:
            expected_package_data['cmake'] = prepend_package_base([
                '__init__.py',
                'cmake.py'
            ])

        if has_hybrid_package:
            expected_package_data['hybrid'] = prepend_package_base([
                '__init__.py',
                # 'hybrid_cmake.dat',
                'hybrid_cmake.py',
                # 'hybrid_pure.dat'
                'hybrid_pure.py',
                # 'data/hybrid_data_cmake.dat',
                # 'data/hybrid_data_pure.dat',
            ])
            expected_package_data['hybrid.hybrid_2'] = prepend_package_base([
                '__init__.py',
                'hybrid_2_cmake.py',
                'hybrid_2_pure.py'
            ])

        if has_pure_package:
            expected_package_data['hybrid.hybrid_2_pure'] = \
                prepend_package_base([
                    '__init__.py',
                    'hybrid_2_pure_1.py',
                    'hybrid_2_pure_2.py'
                ])
            expected_package_data['pure'] = prepend_package_base([
                '__init__.py',
                'pure.py',
                # 'data/pure.dat',
            ])

        _pprint('expected_package_data', expected_package_data)
        package_data = {p: sorted(files)
                        for p, files in setup_kw['package_data'].items()}

        _pprint('package_data', package_data)

        # py_modules
        expected_py_modules = []
        _pprint('expected_py_modules', expected_py_modules)
        _pprint('py_modules')

        # scripts
        expected_scripts = []
        _pprint('expected_scripts', expected_scripts)
        _pprint('scripts')

        # data_files
        expected_data_files = []
        _pprint('expected_data_files', expected_data_files)
        _pprint('data_files')

        assert sorted(setup_kw['packages']) == sorted(expected_packages)
        assert sorted(setup_kw['package_dir']) == sorted(expected_package_dir)
        assert package_data == {p: sorted(files)
                                for p, files in expected_package_data.items()}
        assert sorted(setup_kw['py_modules']) == sorted(expected_py_modules)
        assert sorted(setup_kw['scripts']) == sorted([])
        assert sorted(setup_kw['data_files']) == sorted([])


@pytest.mark.parametrize("with_cmake_source_dir", [0, 1])
def test_cmake_install_into_pure_package(with_cmake_source_dir, capsys):

    # -------------------------------------------------------------------------
    # "SOURCE" tree layout:
    #
    # (1) with_cmake_source_dir == 0
    #
    # ROOT/
    #
    #     CMakeLists.txt
    #     setup.py
    #
    #     fruits/
    #         __init__.py
    #
    #
    # (2) with_cmake_source_dir == 1
    #
    # ROOT/
    #
    #     setup.py
    #
    #     fruits/
    #         __init__.py
    #
    #     src/
    #
    #         CMakeLists.txt
    #
    # -------------------------------------------------------------------------
    # "BINARY" distribution layout:
    #
    # ROOT/
    #
    #     fruits/
    #
    #         __init__.py
    #         apple.py
    #         banana.py
    #
    #             data/
    #
    #                 apple.dat
    #                 banana.dat
    #

    tmp_dir = _tmpdir('cmake_install_into_pure_package')

    cmake_source_dir = 'src' if with_cmake_source_dir else ''

    tmp_dir.join('setup.py').write(textwrap.dedent(
        """
        from skbuild import setup
        setup(
            name="test_py_modules_keyword",
            version="1.2.3",
            description="a package testing use of py_modules keyword",
            author='The scikit-build team',
            license="MIT",
            packages=['fruits'],
            cmake_install_dir='fruits',
            cmake_source_dir='{cmake_source_dir}',
        )
        """.format(cmake_source_dir=cmake_source_dir)
    ))

    cmake_src_dir = tmp_dir.ensure(cmake_source_dir, dir=1)
    cmake_src_dir.join('CMakeLists.txt').write(textwrap.dedent(
        """
        cmake_minimum_required(VERSION 3.5.0)
        project(test)
        file(WRITE "${CMAKE_BINARY_DIR}/apple.py" "# apple.py")
        file(WRITE "${CMAKE_BINARY_DIR}/banana.py" "# banana.py")
        install(
            FILES
                "${CMAKE_BINARY_DIR}/apple.py"
                "${CMAKE_BINARY_DIR}/banana.py"
            DESTINATION "."
            )
        file(WRITE "${CMAKE_BINARY_DIR}/apple.dat" "# apple.dat")
        file(WRITE "${CMAKE_BINARY_DIR}/banana.dat" "# banana.dat")
        install(
            FILES
                "${CMAKE_BINARY_DIR}/apple.dat"
                "${CMAKE_BINARY_DIR}/banana.dat"
            DESTINATION "data"
            )
        """
    ))

    tmp_dir.ensure('fruits/__init__.py')

    with execute_setup_py(tmp_dir, ['build']):
        pass

    messages = [
        "copying _skbuild/cmake-install/{} -> "
        "_skbuild/setuptools/lib".format(module)
        for module in [
            'fruits/__init__.py',
            'fruits/apple.py',
            'fruits/banana.py',
            'fruits/data/apple.dat',
            'fruits/data/banana.dat',
        ]]

    out, _ = capsys.readouterr()
    for message in messages:
        assert to_platform_path(message) in out