import os
import posixpath
import tarfile

from .integration import *
pjoin = os.path.join


class TestSubdirs(IntegrationTest):
    def __init__(self, *args, **kwargs):
        IntegrationTest.__init__(
            self, pjoin(examples_dir, '05_subdirs'), dist=True, *args, **kwargs
        )

    def setUp(self):
        IntegrationTest.setUp(self)
        cleandir(self.distdir)

    def test_build(self):
        self.build()
        self.assertOutput([executable('sub/program')], 'hello, library!\n')

    @skip_if_backend('msbuild')
    def test_dist(self):
        dist = output_file('05_subdirs.tar.gz')
        self.build('dist')
        self.assertExists(dist)
        with tarfile.open(self.target_path(dist)) as t:
            self.assertEqual(set(t.getnames()), {
                posixpath.join('05_subdirs', 'build.bfg'),
                posixpath.join('05_subdirs', 'include', 'library.hpp'),
                posixpath.join('05_subdirs', 'include', 'detail',
                               'export.hpp'),
                posixpath.join('05_subdirs', 'src', 'library.cpp'),
                posixpath.join('05_subdirs', 'src', 'program.cpp'),
            })

    @only_if_backend('make')
    def test_dir_sentinels(self):
        self.build()
        self.assertTrue(os.path.isfile('sub/.dir'))

    @skip_if_backend('msbuild')
    def test_install(self):
        self.build('install')

        extra = []
        if platform_info().has_import_library:
            extra = [pjoin(self.libdir, import_library('sub/library').path)]

        self.assertDirectory(self.distdir, [
            pjoin(self.includedir, 'library.hpp'),
            pjoin(self.includedir, 'detail', 'export.hpp'),
            pjoin(self.bindir, executable('sub/program').path),
            pjoin(self.libdir, shared_library('sub/library').path),
        ] + extra)

        os.chdir(self.srcdir)
        cleandir(self.builddir)
        self.assertOutput([pjoin(self.bindir, executable('sub/program').path)],
                          'hello, library!\n')

    @skip_if_backend('msbuild')
    def test_install_existing_paths(self):
        makedirs(self.includedir, exist_ok=True)
        makedirs(self.bindir, exist_ok=True)
        makedirs(self.libdir, exist_ok=True)
        self.build('install')

        extra = []
        if platform_info().has_import_library:
            extra = [pjoin(self.libdir, import_library('sub/library').path)]

        self.assertDirectory(self.distdir, [
            pjoin(self.includedir, 'library.hpp'),
            pjoin(self.includedir, 'detail', 'export.hpp'),
            pjoin(self.bindir, executable('sub/program').path),
            pjoin(self.libdir, shared_library('sub/library').path),
        ] + extra)

        os.chdir(self.srcdir)
        cleandir(self.builddir)
        self.assertOutput([pjoin(self.bindir, executable('sub/program').path)],
                          'hello, library!\n')
