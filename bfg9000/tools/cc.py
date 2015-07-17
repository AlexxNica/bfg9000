import os.path
import re

from .. import path
from .. import safe_str
from .. import shell
from ..iterutils import iterate, uniques
from ..file_types import *

class CcCompilerBase(object):
    def __init__(self, env, command, name):
        self.platform = env.platform
        self.command_name = command
        self.name = name
        self.command_var = name

    def command(self, cmd, input, output, deps=None, args=None):
        result = [cmd]
        result.extend(iterate(args))
        result.extend(['-c', input])
        if deps:
            result.extend(['-MMD', '-MF', deps])
        result.extend(['-o', output])
        return result

    def output_file(self, name, lang):
        return ObjectFile(name + '.o', Path.builddir, lang)

    @property
    def deps_flavor(self):
        return 'gcc'

    @property
    def library_args(self):
        return ['-fPIC']

    def include_dir(self, directory):
        return ['-I' + directory.path]

class CcLinkerBase(object):
    def __init__(self, env, mode, command, name):
        self.platform = env.platform
        self.mode = mode
        self.command_name = command
        self.name = 'link_' + name
        self.command_var = name
        self.link_var = 'ld'

        # Create a regular expression to extract the library name for linking
        # with -l. TODO: Support .lib as an extension on Windows/Cygwin?
        exts = [r'\.a']
        if not self.platform.has_import_library:
            exts.append(re.escape(self.platform.shared_library_ext))
        self._lib_re = re.compile('lib(.*)(?:' + '|'.join(exts) + ')$')

    def command(self, cmd, input, output, libs=None, args=None):
        result = [cmd]
        result.extend(iterate(args))
        result.extend(iterate(input))
        result.extend(iterate(libs))
        result.extend(['-o', output])
        return result

    def post_install_command(self, target):
        if self.platform.has_rpath:
            paths = uniques(
                path.install_path(i.path, i.install_root).parent()
                for i in target.creator.libs if isinstance(i, SharedLibrary)
            )
            if paths:
                # TODO: Improve the configurability of this (e.g. provide a
                # PatchElf class that installers can work with).
                return ['patchelf', '--set-rpath', safe_str.join(paths, ':'),
                        path.install_path(target.path, target.install_root)]
        return None

    def output_file(self, name):
        if self.mode == 'executable':
            return Executable(
                name + self.platform.executable_ext, Path.builddir
            )
        elif self.mode == 'shared_library':
            head, tail = os.path.split(name)
            def libpath(prefix='lib'):
                return os.path.join(
                    head, 'lib' + tail + self.platform.shared_library_ext
                )

            if self.platform.has_import_library:
                dllprefix = 'cyg' if self.platform.name == 'cygwin' else 'lib'
                dll = DllLibrary(libpath(dllprefix), Path.builddir)
                return SharedLibrary(libpath() + '.a', Path.builddir, dll)
            else:
                return SharedLibrary(libpath(), Path.builddir)
        else:
            raise ValueError("unknown mode '{}'".format(self.mode))

    @property
    def mode_args(self):
        return ['-shared', '-fPIC'] if self.mode == 'shared_library' else []

    def lib_dirs(self, libraries):
        dirs = uniques(i.path.parent() for i in libraries)
        return ['-L' + i for i in dirs]

    def link_lib(self, library):
        lib_name = library.path.basename()
        m = self._lib_re.match(lib_name)
        if not m:
            raise ValueError("'{}' is not a valid library".format(lib_name))
        return ['-l' + m.group(1)]

    def import_lib(self, library):
        if self.platform.has_import_library and self.mode == 'shared_library':
            return ['-Wl,--out-implib=' + library.path]
        return []

    def rpath(self, libraries, start):
        if self.platform.has_rpath:
            paths = uniques(i.path.parent().relpath(start) for i in libraries
                            if isinstance(i, SharedLibrary))
            if paths:
                rpaths = ('$ORIGIN' if i == '.' else os.path.join('$ORIGIN', i)
                          for i in paths)
                return ['-Wl,-rpath={}'.format(':'.join(rpaths))]
        return []

class CcCompiler(CcCompilerBase):
    def __init__(self, env):
        CcCompilerBase.__init__(self, env, env.getvar('CC', 'cc'), 'cc')
        self.global_args = (
            shell.split(env.getvar('CFLAGS', '')) +
            shell.split(env.getvar('CPPFLAGS', ''))
        )

class CxxCompiler(CcCompilerBase):
    def __init__(self, env):
        CcCompilerBase.__init__(self, env, env.getvar('CXX', 'c++'), 'cxx')
        self.global_args = (
            shell.split(env.getvar('CXXFLAGS', '')) +
            shell.split(env.getvar('CPPFLAGS', ''))
        )

class CcLinker(CcLinkerBase):
    def __init__(self, env, mode):
        CcLinkerBase.__init__(self, env, mode, env.getvar('CC', 'cc'), 'cc')
        self.global_args = shell.split(env.getvar('LDFLAGS', ''))
        self.global_libs = shell.split(env.getvar('LDLIBS', ''))

class CxxLinker(CcLinkerBase):
    def __init__(self, env, mode):
        CcLinkerBase.__init__(self, env, mode, env.getvar('CXX', 'c++'), 'cxx')
        self.global_args = shell.split(env.getvar('LDFLAGS', ''))
        self.global_libs = shell.split(env.getvar('LDLIBS', ''))