# -*- coding: utf-8 -*-

# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Read and write Ogg Theora comments.

This module handles Theora files wrapped in an Ogg bitstream. The
first Theora stream found is used.

Based on the specification at http://theora.org/doc/Theora_I_spec.pdf.
"""

__all__ = ["OggTheora", "Open", "delete"]

import struct

from mutagen import StreamInfo
from mutagen._vorbis import VCommentDict
from mutagen._util import cdata, get_size
from mutagen._tags import PaddingInfo
from mutagen.ogg import OggPage, OggFileType, error as OggError


class error(OggError):
    pass


class OggTheoraHeaderError(error):
    pass


class OggTheoraInfo(StreamInfo):
    """Ogg Theora stream information."""

    length = 0
    """File length in seconds, as a float"""

    fps = 0
    """Video frames per second, as a float"""

    bitrate = 0
    """Bitrate in bps (int)"""

    def __init__(self, fileobj):
        page = OggPage(fileobj)
        while not page.packets[0].startswith(b"\x80theora"):
            page = OggPage(fileobj)
        if not page.first:
            raise OggTheoraHeaderError(
                "page has ID header, but doesn't start a stream")
        data = page.packets[0]
        vmaj, vmin = struct.unpack("2B", data[7:9])
        if (vmaj, vmin) != (3, 2):
            raise OggTheoraHeaderError(
                "found Theora version %d.%d != 3.2" % (vmaj, vmin))
        fps_num, fps_den = struct.unpack(">2I", data[22:30])
        self.fps = fps_num / float(fps_den)
        self.bitrate = cdata.uint_be(b"\x00" + data[37:40])
        self.granule_shift = (cdata.ushort_be(data[40:42]) >> 5) & 0x1F
        self.serial = page.serial

    def _post_tags(self, fileobj):
        page = OggPage.find_last(fileobj, self.serial)
        position = page.position
        mask = (1 << self.granule_shift) - 1
        frames = (position >> self.granule_shift) + (position & mask)
        self.length = frames / float(self.fps)

    def pprint(self):
        return u"Ogg Theora, %.2f seconds, %d bps" % (self.length,
                                                      self.bitrate)


class OggTheoraCommentDict(VCommentDict):
    """Theora comments embedded in an Ogg bitstream."""

    def __init__(self, fileobj, info):
        pages = []
        complete = False
        while not complete:
            page = OggPage(fileobj)
            if page.serial == info.serial:
                pages.append(page)
                complete = page.complete or (len(page.packets) > 1)
        data = OggPage.to_packets(pages)[0][7:]
        super(OggTheoraCommentDict, self).__init__(data, framing=False)
        self._padding = len(data) - self._size

    def _inject(self, fileobj, padding_func):
        """Write tag data into the Theora comment packet/page."""

        fileobj.seek(0)
        page = OggPage(fileobj)
        while not page.packets[0].startswith(b"\x81theora"):
            page = OggPage(fileobj)

        old_pages = [page]
        while not (old_pages[-1].complete or len(old_pages[-1].packets) > 1):
            page = OggPage(fileobj)
            if page.serial == old_pages[0].serial:
                old_pages.append(page)

        packets = OggPage.to_packets(old_pages, strict=False)

        content_size = get_size(fileobj) - len(packets[0])  # approx
        vcomment_data = b"\x81theora" + self.write(framing=False)
        padding_left = len(packets[0]) - len(vcomment_data)

        info = PaddingInfo(padding_left, content_size)
        new_padding = info._get_padding(padding_func)

        packets[0] = vcomment_data + b"\x00" * new_padding

        new_pages = OggPage._from_packets_try_preserve(packets, old_pages)
        OggPage.replace(fileobj, old_pages, new_pages)


class OggTheora(OggFileType):
    """An Ogg Theora file."""

    _Info = OggTheoraInfo
    _Tags = OggTheoraCommentDict
    _Error = OggTheoraHeaderError
    _mimes = ["video/x-theora"]

    info = None
    """A `OggTheoraInfo`"""

    tags = None
    """A `VCommentDict`"""

    @staticmethod
    def score(filename, fileobj, header):
        return (header.startswith(b"OggS") *
                ((b"\x80theora" in header) + (b"\x81theora" in header)) * 2)


Open = OggTheora


def delete(filename):
    """Remove tags from a file."""

    OggTheora(filename).delete()
