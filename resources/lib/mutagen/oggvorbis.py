# -*- coding: utf-8 -*-

# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Read and write Ogg Vorbis comments.

This module handles Vorbis files wrapped in an Ogg bitstream. The
first Vorbis stream found is used.

Read more about Ogg Vorbis at http://vorbis.com/. This module is based
on the specification at http://www.xiph.org/vorbis/doc/Vorbis_I_spec.html.
"""

__all__ = ["OggVorbis", "Open", "delete"]

import struct

from mutagen import StreamInfo
from mutagen._vorbis import VCommentDict
from mutagen._util import get_size
from mutagen._tags import PaddingInfo
from mutagen.ogg import OggPage, OggFileType, error as OggError


class error(OggError):
    pass


class OggVorbisHeaderError(error):
    pass


class OggVorbisInfo(StreamInfo):
    """Ogg Vorbis stream information."""

    length = 0
    """File length in seconds, as a float"""

    channels = 0
    """Number of channels"""

    bitrate = 0
    """Nominal ('average') bitrate in bits per second, as an int"""

    sample_rate = 0
    """Sample rate in Hz"""

    def __init__(self, fileobj):
        page = OggPage(fileobj)
        while not page.packets[0].startswith(b"\x01vorbis"):
            page = OggPage(fileobj)
        if not page.first:
            raise OggVorbisHeaderError(
                "page has ID header, but doesn't start a stream")
        (self.channels, self.sample_rate, max_bitrate, nominal_bitrate,
         min_bitrate) = struct.unpack("<B4i", page.packets[0][11:28])
        self.serial = page.serial

        max_bitrate = max(0, max_bitrate)
        min_bitrate = max(0, min_bitrate)
        nominal_bitrate = max(0, nominal_bitrate)

        if nominal_bitrate == 0:
            self.bitrate = (max_bitrate + min_bitrate) // 2
        elif max_bitrate and max_bitrate < nominal_bitrate:
            # If the max bitrate is less than the nominal, we know
            # the nominal is wrong.
            self.bitrate = max_bitrate
        elif min_bitrate > nominal_bitrate:
            self.bitrate = min_bitrate
        else:
            self.bitrate = nominal_bitrate

    def _post_tags(self, fileobj):
        page = OggPage.find_last(fileobj, self.serial)
        self.length = page.position / float(self.sample_rate)

    def pprint(self):
        return u"Ogg Vorbis, %.2f seconds, %d bps" % (
            self.length, self.bitrate)


class OggVCommentDict(VCommentDict):
    """Vorbis comments embedded in an Ogg bitstream."""

    def __init__(self, fileobj, info):
        pages = []
        complete = False
        while not complete:
            page = OggPage(fileobj)
            if page.serial == info.serial:
                pages.append(page)
                complete = page.complete or (len(page.packets) > 1)
        data = OggPage.to_packets(pages)[0][7:]  # Strip off "\x03vorbis".
        super(OggVCommentDict, self).__init__(data)
        self._padding = len(data) - self._size

    def _inject(self, fileobj, padding_func):
        """Write tag data into the Vorbis comment packet/page."""

        # Find the old pages in the file; we'll need to remove them,
        # plus grab any stray setup packet data out of them.
        fileobj.seek(0)
        page = OggPage(fileobj)
        while not page.packets[0].startswith(b"\x03vorbis"):
            page = OggPage(fileobj)

        old_pages = [page]
        while not (old_pages[-1].complete or len(old_pages[-1].packets) > 1):
            page = OggPage(fileobj)
            if page.serial == old_pages[0].serial:
                old_pages.append(page)

        packets = OggPage.to_packets(old_pages, strict=False)

        content_size = get_size(fileobj) - len(packets[0])  # approx
        vcomment_data = b"\x03vorbis" + self.write()
        padding_left = len(packets[0]) - len(vcomment_data)

        info = PaddingInfo(padding_left, content_size)
        new_padding = info._get_padding(padding_func)

        # Set the new comment packet.
        packets[0] = vcomment_data + b"\x00" * new_padding

        new_pages = OggPage._from_packets_try_preserve(packets, old_pages)
        OggPage.replace(fileobj, old_pages, new_pages)


class OggVorbis(OggFileType):
    """An Ogg Vorbis file."""

    _Info = OggVorbisInfo
    _Tags = OggVCommentDict
    _Error = OggVorbisHeaderError
    _mimes = ["audio/vorbis", "audio/x-vorbis"]

    info = None
    """A `OggVorbisInfo`"""

    tags = None
    """A `VCommentDict`"""

    @staticmethod
    def score(filename, fileobj, header):
        return (header.startswith(b"OggS") * (b"\x01vorbis" in header))


Open = OggVorbis


def delete(filename):
    """Remove tags from a file."""

    OggVorbis(filename).delete()
