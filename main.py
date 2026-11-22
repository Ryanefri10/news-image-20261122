#!/usr/bin/env python3
"""Courier for the news-image-20261122 make.fun bounty entry.

The picture itself is pre-rendered and shipped beside this script as
entry.png. This program's only job is to prove that the shipped file
is exactly the approved artwork, then carry a byte-for-byte copy of
it into the directory make.fun provides ($MAKEFUN_OUTPUT_DIR).

Verification walks the whole PNG chunk by chunk: the signature, the
IHDR geometry, the CRC of every chunk, the closing IEND, and the
pinned SHA-256 of the file. Anything off, and the program stops
before it writes a single byte.

Standard library only. No arguments, no network, deterministic.
"""

import hashlib
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTWORK = HERE / "entry.png"

MAX_BYTES = 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WANT_WIDTH = 1024
WANT_HEIGHT = 1024

# sha256 of entry.png exactly as committed in this repository.
ARTWORK_SHA256 = (
    "94e374f29ab02561acdec73b8ab81986682046e23d23263a29074678180a8f72"
)


class ArtworkError(Exception):
    """The shipped image failed one of its integrity checks."""


def read_artwork() -> bytes:
    """Load the vendored picture and enforce the size ceiling."""
    if not ARTWORK.is_file():
        raise ArtworkError(f"no vendored image beside main.py: {ARTWORK}")
    data = ARTWORK.read_bytes()
    if len(data) > MAX_BYTES:
        raise ArtworkError(
            f"image is {len(data)} bytes, above the {MAX_BYTES} limit")
    if len(data) < 8 or data[:8] != PNG_MAGIC:
        raise ArtworkError("file does not open with the PNG signature")
    return data


def walk_chunks(data: bytes) -> tuple:
    """Walk every PNG chunk, checking lengths, CRCs and the trailer.

    Returns the (width, height) declared by IHDR. Raises ArtworkError
    on a bad length, a CRC mismatch, a missing IEND, or trailing bytes
    after IEND.
    """
    pos = 8
    width = height = None
    seen_iend = False
    while pos < len(data):
        if pos + 8 > len(data):
            raise ArtworkError("truncated chunk header")
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if end > len(data):
            raise ArtworkError(f"chunk {tag!r} runs past end of file")
        payload = data[pos + 8:pos + 8 + length]
        stored = struct.unpack(">I", data[pos + 8 + length:end])[0]
        if zlib.crc32(tag + payload) & 0xFFFFFFFF != stored:
            raise ArtworkError(f"chunk {tag!r} fails its CRC-32")
        if tag == b"IHDR":
            if length != 13:
                raise ArtworkError("IHDR payload is not 13 bytes")
            width, height = struct.unpack(">II", payload[:8])
            bit_depth, colour_type = payload[8], payload[9]
            if bit_depth != 8 or colour_type not in (2, 6):
                raise ArtworkError(
                    f"unexpected IHDR depth {bit_depth} / colour "
                    f"type {colour_type}; expected 8-bit RGB(A)")
        if tag == b"IEND":
            if length != 0:
                raise ArtworkError("IEND carries a payload")
            if end != len(data):
                raise ArtworkError("bytes follow the IEND chunk")
            seen_iend = True
        pos = end
    if width is None:
        raise ArtworkError("no IHDR chunk found")
    if not seen_iend:
        raise ArtworkError("no closing IEND chunk found")
    return width, height


def confirm_digest(data: bytes) -> None:
    """The file must be exactly the artwork this commit approves."""
    actual = hashlib.sha256(data).hexdigest()
    if actual != ARTWORK_SHA256:
        raise ArtworkError(
            f"SHA-256 {actual} is not the approved {ARTWORK_SHA256}")


def deliver_copy(data: bytes) -> Path:
    """Place the verified bytes at $MAKEFUN_OUTPUT_DIR/entry.png."""
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not out_dir:
        raise ArtworkError("MAKEFUN_OUTPUT_DIR is not set")
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    dest = target / "entry.png"
    dest.write_bytes(data)
    if dest.read_bytes() != data:
        raise ArtworkError("the written copy differs from the artwork")
    return dest


def entrypoint() -> int:
    try:
        data = read_artwork()
        width, height = walk_chunks(data)
        if (width, height) != (WANT_WIDTH, WANT_HEIGHT):
            raise ArtworkError(
                f"image is {width}x{height}, expected "
                f"{WANT_WIDTH}x{WANT_HEIGHT}")
        confirm_digest(data)
        dest = deliver_copy(data)
    except ArtworkError as problem:
        print(f"main.py: {problem}", file=sys.stderr)
        return 1
    print(f"delivered {dest} ({len(data)} bytes, "
          f"sha256 {ARTWORK_SHA256[:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(entrypoint())
