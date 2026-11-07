"""Windows process memory and PE helpers."""
import ctypes as c
import ctypes
import struct

class MBI(c.Structure):
    _fields_ = [('base',c.c_void_p),('allocation',c.c_void_p),('allocation_protect',c.c_ulong),
                ('partition',c.c_ushort),('size',c.c_size_t),('state',c.c_ulong),
                ('protect',c.c_ulong),('type',c.c_ulong)]


def pe_bytes(path, rva, length):
    with path.open("rb") as f:
        f.seek(0x3C)
        pe_offset = struct.unpack("<I", f.read(4))[0]
        f.seek(pe_offset)
        if f.read(4) != b"PE\0\0":
            raise ValueError(f"Expected a PE file: {path}")
        header = f.read(20)
        sections = struct.unpack_from("<H", header, 2)[0]
        optional_size = struct.unpack_from("<H", header, 16)[0]
        f.seek(pe_offset + 24 + optional_size)
        for _ in range(sections):
            item = f.read(40)
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", item, 8)
            if virtual_address <= rva and rva + length <= virtual_address + raw_size:
                f.seek(raw_pointer + rva - virtual_address)
                return f.read(length)
    raise ValueError(f"RVA 0x{rva:X} is outside the PE section data: {path}")


def read_process(pid, address, length):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_size_t,
                                         ctypes.POINTER(ctypes.c_size_t)]
    kernel.ReadProcessMemory.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x0410, 0, pid)  # QUERY_INFORMATION | VM_READ
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess")
    try:
        buffer = ctypes.create_string_buffer(length)
        n = ctypes.c_size_t()
        ok = kernel.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer,
                                      length, ctypes.byref(n))
        if not ok or n.value != length:
            raise OSError(ctypes.get_last_error(), f"ReadProcessMemory 0x{address:X}")
        return buffer.raw
    finally:
        kernel.CloseHandle(handle)


