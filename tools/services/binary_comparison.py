"""Compare consecutive builds with radiff2 before rerunning a benchmark."""

import os
import shutil
import stat
import struct
import subprocess
import tempfile


def _is_runnable_elf(path):
    with open(path, "rb") as binary:
        header = binary.read(18)
    if len(header) < 18 or header[:4] != b"\x7fELF":
        return False
    byte_order = {1: "<", 2: ">"}.get(header[5])
    if byte_order is None:
        return False
    # ET_EXEC and ET_DYN include executables and shared libraries.
    return struct.unpack_from(byte_order + "H", header, 16)[0] in (2, 3)


def _raise_walk_error(error):
    raise error


def runnable_binaries(build_info, builder):
    """Find every runnable ELF in the build directory by relative path."""
    build_dir = getattr(builder, "build_dir", None)
    if build_dir:
        paths = (
            os.path.join(root, name)
            for root, _, names in os.walk(build_dir, onerror=_raise_walk_error)
            for name in names
        )
        base_dir = build_dir
    elif isinstance(build_info, str):
        paths = (build_info,)
        base_dir = os.path.dirname(build_info)
    else:
        return None

    binaries = {}
    try:
        for path in paths:
            if _is_runnable_elf(path):
                binaries[os.path.relpath(path, base_dir)] = path
    except OSError:
        return None
    return binaries or None


def radiff2_available():
    return shutil.which("radiff2") is not None


class PreviousBuild:
    """One measured build kept outside the build directory for the next diff."""

    def __init__(self, binaries):
        self.snapshot = tempfile.TemporaryDirectory(prefix="autotuner-binaries-")
        self.paths = tuple(sorted(binaries))
        try:
            for relative_path, source in binaries.items():
                destination = os.path.join(self.snapshot.name, relative_path)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(source, destination)
        except OSError:
            self.close()
            raise
        self.runtime = None

    def equivalent_to(self, binaries):
        if tuple(sorted(binaries)) != self.paths:
            return False
        radiff2 = shutil.which("radiff2")
        if radiff2 is None:
            return False
        try:
            for relative_path, current in binaries.items():
                previous = os.path.join(self.snapshot.name, relative_path)
                previous_stat = os.stat(previous)
                current_stat = os.stat(current)
                if previous_stat.st_size != current_stat.st_size:
                    return False
                if stat.S_IMODE(previous_stat.st_mode) != stat.S_IMODE(current_stat.st_mode):
                    return False
                result = subprocess.run(
                    [radiff2, "-c", previous, current],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0 or result.stdout.strip() != "0":
                    return False
        except (OSError, subprocess.SubprocessError):
            return False
        return True

    def close(self):
        self.snapshot.cleanup()
