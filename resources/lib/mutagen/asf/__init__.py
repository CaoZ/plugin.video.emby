# -*- coding: utf-8 -*-
# Copyright (C) 2005-2006  Joe Wreschnig
# Copyright (C) 2006-2007  Lukas Lalinsky
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Read and write ASF (Window Media Audio) files."""

__all__ = ["ASF", "Open"]

from mutagen import FileType, Metadata, StreamInfo
from mutagen._util import resize_bytes, DictMixin
from mutagen._compat import string_types, long_, PY3, izip

from ._util import error, ASFError, ASFHeaderError
from ._objects import HeaderObject, MetadataLibraryObject, MetadataObject, \
    ExtendedContentDescriptionObject, HeaderExtensionObject, \
    ContentDescriptionObject
from ._attrs import ASFGUIDAttribute, ASFWordAttribute, ASFQWordAttribute, \
    ASFDWordAttribute, ASFBoolAttribute, ASFByteArrayAttribute, \
    ASFUnicodeAttribute, ASFBaseAttribute, ASFValue


# pyflakes
error, ASFError, ASFHeaderError, ASFValue


class ASFInfo(StreamInfo):
    """ASF stream information."""

    length = 0.0
    """Length in seconds (`float`)"""

    sample_rate = 0
    """Sample rate in Hz (`int`)"""

    bitrate = 0
    """Bitrate in bps (`int`)"""

    channels = 0
    """Number of channels (`int`)"""

    codec_type = u""
    """Name of the codec type of the first audio stream or
    an empty string if unknown. Example: ``Windows Media Audio 9 Standard``
    (:class:`mutagen.text`)
    """

    codec_name = u""
    """Name and maybe version of the codec used. Example:
    ``Windows Media Audio 9.1`` (:class:`mutagen.text`)
    """

    codec_description = u""
    """Further information on the codec used.
    Example: ``64 kbps, 48 kHz, stereo 2-pass CBR`` (:class:`mutagen.text`)
    """

    def __init__(self):
        self.length = 0.0
        self.sample_rate = 0
        self.bitrate = 0
        self.channels = 0
        self.codec_type = u""
        self.codec_name = u""
        self.codec_description = u""

    def pprint(self):
        """Returns a stream information text summary

        :rtype: text
        """

        s = u"ASF (%s) %d bps, %s Hz, %d channels, %.2f seconds" % (
            self.codec_type or self.codec_name or u"???", self.bitrate,
            self.sample_rate, self.channels, self.length)
        return s


class ASFTags(list, DictMixin, Metadata):
    """Dictionary containing ASF attributes."""

    def __getitem__(self, key):
        """A list of values for the key.

        This is a copy, so comment['title'].append('a title') will not
        work.

        """

        # PY3 only
        if isinstance(key, slice):
            return list.__getitem__(self, key)

        values = [value for (k, value) in self if k == key]
        if not values:
            raise KeyError(key)
        else:
            return values

    def __delitem__(self, key):
        """Delete all values associated with the key."""

        # PY3 only
        if isinstance(key, slice):
            return list.__delitem__(self, key)

        to_delete = [x for x in self if x[0] == key]
        if not to_delete:
            raise KeyError(key)
        else:
            for k in to_delete:
                self.remove(k)

    def __contains__(self, key):
        """Return true if the key has any values."""
        for k, value in self:
            if k == key:
                return True
        else:
            return False

    def __setitem__(self, key, values):
        """Set a key's value or values.

        Setting a value overwrites all old ones. The value may be a
        list of Unicode or UTF-8 strings, or a single Unicode or UTF-8
        string.
        """

        # PY3 only
        if isinstance(key, slice):
            return list.__setitem__(self, key, values)

        if not isinstance(values, list):
            values = [values]

        to_append = []
        for value in values:
            if not isinstance(value, ASFBaseAttribute):
                if isinstance(value, string_types):
                    value = ASFUnicodeAttribute(value)
                elif PY3 and isinstance(value, bytes):
                    value = ASFByteArrayAttribute(value)
                elif isinstance(value, bool):
                    value = ASFBoolAttribute(value)
                elif isinstance(value, int):
                    value = ASFDWordAttribute(value)
                elif isinstance(value, long_):
                    value = ASFQWordAttribute(value)
                else:
                    raise TypeError("Invalid type %r" % type(value))
            to_append.append((key, value))

        try:
            del(self[key])
        except KeyError:
            pass

        self.extend(to_append)

    def keys(self):
        """Return a sequence of all keys in the comment."""

        return self and set(next(izip(*self)))

    def as_dict(self):
        """Return a copy of the comment data in a real dict."""

        d = {}
        for key, value in self:
            d.setdefault(key, []).append(value)
        return d

    def pprint(self):
        """Returns a string containing all key, value pairs.

        :rtype: text
        """

        return "\n".join("%s=%s" % (k, v) for k, v in self)


UNICODE = ASFUnicodeAttribute.TYPE
"""Unicode string type"""

BYTEARRAY = ASFByteArrayAttribute.TYPE
"""Byte array type"""

BOOL = ASFBoolAttribute.TYPE
"""Bool type"""

DWORD = ASFDWordAttribute.TYPE
""""DWord type (uint32)"""

QWORD = ASFQWordAttribute.TYPE
"""QWord type (uint64)"""

WORD = ASFWordAttribute.TYPE
"""Word type (uint16)"""

GUID = ASFGUIDAttribute.TYPE
"""GUID type"""


class ASF(FileType):
    """An ASF file, probably containing WMA or WMV.

    :param filename: a filename to load
    :raises mutagen.asf.error: In case loading fails
    """

    _mimes = ["audio/x-ms-wma", "audio/x-ms-wmv", "video/x-ms-asf",
              "audio/x-wma", "video/x-wmv"]

    info = None
    """A `ASFInfo` instance"""

    tags = None
    """A `ASFTags` instance"""

    def load(self, filename):
        self.filename = filename
        self.info = ASFInfo()
        self.tags = ASFTags()

        with open(filename, "rb") as fileobj:
            self._tags = {}

            self._header = HeaderObject.parse_full(self, fileobj)

            for guid in [ContentDescriptionObject.GUID,
                    ExtendedContentDescriptionObject.GUID, MetadataObject.GUID,
                    MetadataLibraryObject.GUID]:
                self.tags.extend(self._tags.pop(guid, []))

            assert not self._tags

    def save(self, filename=None, padding=None):
        """Save tag changes back to the loaded file.

        :param padding: A callback which returns the amount of padding to use.
            See :class:`mutagen.PaddingInfo`

        :raises mutagen.asf.error: In case saving fails
        """

        if filename is not None and filename != self.filename:
            raise ValueError("saving to another file not supported atm")

        # Move attributes to the right objects
        self.to_content_description = {}
        self.to_extended_content_description = {}
        self.to_metadata = {}
        self.to_metadata_library = []
        for name, value in self.tags:
            library_only = (value.data_size() > 0xFFFF or value.TYPE == GUID)
            can_cont_desc = value.TYPE == UNICODE

            if library_only or value.language is not None:
                self.to_metadata_library.append((name, value))
            elif value.stream is not None:
                if name not in self.to_metadata:
                    self.to_metadata[name] = value
                else:
                    self.to_metadata_library.append((name, value))
            elif name in ContentDescriptionObject.NAMES:
                if name not in self.to_content_description and can_cont_desc:
                    self.to_content_description[name] = value
                else:
                    self.to_metadata_library.append((name, value))
            else:
                if name not in self.to_extended_content_description:
                    self.to_extended_content_description[name] = value
                else:
                    self.to_metadata_library.append((name, value))

        # Add missing objects
        header = self._header
        if header.get_child(ContentDescriptionObject.GUID) is None:
            header.objects.append(ContentDescriptionObject())
        if header.get_child(ExtendedContentDescriptionObject.GUID) is None:
            header.objects.append(ExtendedContentDescriptionObject())
        header_ext = header.get_child(HeaderExtensionObject.GUID)
        if header_ext is None:
            header_ext = HeaderExtensionObject()
            header.objects.append(header_ext)
        if header_ext.get_child(MetadataObject.GUID) is None:
            header_ext.objects.append(MetadataObject())
        if header_ext.get_child(MetadataLibraryObject.GUID) is None:
            header_ext.objects.append(MetadataLibraryObject())

        # Render to file
        with open(self.filename, "rb+") as fileobj:
            old_size = header.parse_size(fileobj)[0]
            data = header.render_full(self, fileobj, old_size, padding)
            size = len(data)
            resize_bytes(fileobj, old_size, size, 0)
            fileobj.seek(0)
            fileobj.write(data)

    def add_tags(self):
        raise ASFError

    def delete(self, filename=None):

        if filename is not None and filename != self.filename:
            raise ValueError("saving to another file not supported atm")

        self.tags.clear()
        self.save(padding=lambda x: 0)

    @staticmethod
    def score(filename, fileobj, header):
        return header.startswith(HeaderObject.GUID) * 2

Open = ASF
