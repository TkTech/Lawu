# -*- coding: utf8 -*-
"""
The :mod:`jawa.jf` module provides tools for working with JVM ``.jar``
archives, which are simply ZIP_ archives with some mandatory structure.

.. note::
    If `czipfile <http://pypi.python.org/pypi/czipfile>`_ is available,
    decompression will be noticably faster.

.. _ZIP: http://en.wikipedia.org/wiki/Zip_(file_format)
"""
__all__ = ('JarFile',)

try:
    from cStringIO import StringIO
except ImportError:
    try:
        from StringIO import StringIO
    except ImportError:
        from io import BytesIO
        StringIO = BytesIO

from jawa.util.ezip import EditableZipFile
from jawa.cf import ClassFile


class JarFile(EditableZipFile):
    """
    Implements Jawa-specific extensions over
    :class:`~jawa.util.ezip.EditableZipFile`.
    """
    def all_classes(self):
        """
        An iterator that yields a :class:`~jawa.cf.ClassFile` for each
        path ending in ``.class`` in this JarFile::

            with JarFile(sys.argv[1]) as jf:
                for path, cf in jf.all_classes():
                    ...
        """
        # About 10ms faster for 1028 files than using self.regex()
        for path in (p for p in self.namelist if p.endswith('.class')):
            yield path, ClassFile(StringIO(self.read(path)))

    def open_class(self, path):
        """
        Returns a :class:`~jawa.cf.ClassFile` for the file at `path`.

        :param path: Path to the file to load.
        """
        return ClassFile(StringIO(self.read(path)))

    @property
    def class_count(self):
        """
        The number of classes within this JarFile (any file ending in .class
        is considered to be a ClassFile).
        """
        return sum(1 for p in self.namelist if p.endswith('.class'))
