"""
ClassFile reader & writer.

The :mod:`lawu.cf` module provides tools for working with JVM ``.class``
ClassFiles.
"""
from typing import BinaryIO, Iterable, Union, Sequence, Optional
from struct import pack, unpack
from collections import namedtuple
from enum import IntFlag

from lawu.constants import ConstantPool, ConstantClass
from lawu.fields import FieldTable
from lawu.methods import MethodTable
from lawu.attribute import AttributeTable, ATTRIBUTE_CLASSES
from lawu.attributes.bootstrap import BootstrapMethod


class ClassVersion(namedtuple('ClassVersion', ['major', 'minor'])):
    """ClassFile file format version."""

    __slots__ = ()

    @property
    def human(self) -> str:
        """
        A human-readable string identifying this version.

        If the version is unknown, `None` is returned instead.
        """
        return {
            0x33: 'J2SE_7',
            0x32: 'J2SE_6',
            0x31: 'J2SE_5',
            0x30: 'JDK1_4',
            0x2F: 'JDK1_3',
            0x2E: 'JDK1_2',
            0x2D: 'JDK1_1',
        }.get(self.major, None)


class ClassFile(object):
    """
    Implements the JVM ClassFile (files typically ending in ``.class``).

    To open an existing ClassFile::

        >>> with open('HelloWorld.class', 'rb') as fin:
        ...    cf = ClassFile(fin)

    To save a newly created or modified ClassFile::

        >>> cf = ClassFile.create('HelloWorld')
        >>> with open('HelloWorld.class', 'wb') as out:
        ...    cf.save(out)

    :meth:`~ClassFile.create` sets up some reasonable defaults equivalent to:

    .. code-block:: java

        public class HelloWorld extends java.lang.Object{
        }

    :param source: any file-like object providing ``.read()``.
    """

    #: The JVM ClassFile magic number.
    MAGIC = 0xCAFEBABE
    
    class AccessFlags(IntFlag):
        PUBLIC = 0x0001
        FINAL = 0x0010
        SUPER = 0x0020
        INTERFACE = 0x0200
        ABSTRACT = 0x0400
        SYNTHETIC = 0x1000
        ANNOTATION = 0x2000
        ENUM = 0x4000
        MODULE = 0x8000
    
    def __init__(self, source: Optional[BinaryIO] = None):
        # Default to J2SE_7
        self._version = ClassVersion(0x32, 0)
        self._constants = ConstantPool()
        self.access_flags = ClassFile.AccessFlags(0)
        self._this = 0
        self._super = 0
        self._interfaces = []
        self.fields = FieldTable(self)
        self.methods = MethodTable(self)
        self.attributes = AttributeTable(self)
        #: The ClassLoader bound to this ClassFile, if any.
        self.classloader = None

        if source:
            self._from_io(source)

    @classmethod
    def create(cls, this: str, super_: str = u'java/lang/Object')\
            -> 'ClassFile':
        """
        A utility which sets up reasonable defaults for a new public class.

        :param this: The name of this class.
        :param super_: The name of this class's superclass.
        """
        cf = ClassFile()

        cf.access_flags.PUBLIC = True
        cf.access_flags.SUPER = True

        cf.this = cf.constants.create_class(this)
        cf.super_ = cf.constants.create_class(super_)

        return cf

    def save(self, source: BinaryIO):
        """
        Saves the class to the file-like object `source`.

        :param source: Any file-like object providing write().
        """
        write = source.write

        write(pack(
            '>IHH',
            ClassFile.MAGIC,
            self.version.minor,
            self.version.major
        ))

        self._constants.pack(source)

        write(pack('>H', int(self.access_flags)))
        write(pack(
            f'>HHH{len(self._interfaces)}H',
            self._this,
            self._super,
            len(self._interfaces),
            *self._interfaces
        ))

        self.fields.pack(source)
        self.methods.pack(source)
        self.attributes.pack(source)

    def _from_io(self, source: BinaryIO):
        """
        Loads an existing JVM ClassFile from any file-like object.
        """
        read = source.read

        if unpack('>I', source.read(4))[0] != ClassFile.MAGIC:
            raise ValueError('invalid magic number')

        # The version is swapped on disk to (minor, major), so swap it back.
        self.version = unpack('>HH', source.read(4))[::-1]

        self._constants.unpack(source)

        # ClassFile access_flags, see section #4.1 of the JVM specs.
        self.access_flags = unpack('>H', read(2))

        # The CONSTANT_Class indexes for "this" class and its superclass.
        # Interfaces are a simple list of CONSTANT_Class indexes.
        self._this, self._super, interfaces_count = unpack('>HHH', read(6))
        self._interfaces = unpack(
            f'>{interfaces_count}H',
            read(2 * interfaces_count)
        )

        self.fields.unpack(source)
        self.methods.unpack(source)
        self.attributes.unpack(source)

    @property
    def version(self) -> ClassVersion:
        """
        The :class:`~lawu.cf.ClassVersion` for this class.

        Example::

            >>> cf = ClassFile.create('HelloWorld')
            >>> cf.version = 51, 0
            >>> print(cf.version)
            ClassVersion(major=51, minor=0)
            >>> print(cf.version.major)
            51
        """
        return self._version

    @version.setter
    def version(self, major_minor: Union[ClassVersion, Sequence]):
        self._version = ClassVersion(*major_minor)

    @property
    def constants(self) -> ConstantPool:
        """
        The :class:`~lawu.cp.ConstantPool` for this class.
        """
        return self._constants

    @property
    def this(self) -> ConstantClass:
        """
        The :class:`~lawu.constants.ConstantClass` which represents this class.
        """
        return self.constants.get(self._this)

    @this.setter
    def this(self, value):
        self._this = value.index

    @property
    def super_(self) -> ConstantClass:
        """
        The :class:`~lawu.constants.ConstantClass` which represents this
        class's superclass.
        """
        return self.constants.get(self._super)

    @super_.setter
    def super_(self, value: ConstantClass):
        self._super = value.index

    @property
    def interfaces(self) -> Iterable[ConstantClass]:
        """
        A list of direct superinterfaces of this class as indexes into
        the constant pool, in left-to-right order.
        """
        return [self._constants[idx] for idx in self._interfaces]

    @property
    def bootstrap_methods(self) -> BootstrapMethod:
        """
        Returns the bootstrap methods' table from the BootstrapMethods
        attribute, if one exists. If it does not, one will be created.

        :returns: Table of `BootstrapMethod` objects.
        """
        bootstrap = self.attributes.find_one(name='BootstrapMethods')

        if bootstrap is None:
            bootstrap = self.attributes.create(
                ATTRIBUTE_CLASSES['BootstrapMethods']
            )

        return bootstrap.table

    def __repr__(self):
        return f'<ClassFile(this={self.this.name.value!r})>'
