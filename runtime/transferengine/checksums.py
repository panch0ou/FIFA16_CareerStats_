"""FIFA MPEG-2 CRC and container IEEE CRC are deliberately separate."""
import zlib

def _table():
 result=[]
 for i in range(256):
  c=i<<24
  for _ in range(8): c=((c<<1)^0x04C11DB7 if c&0x80000000 else c<<1)&0xffffffff
  result.append(c)
 return tuple(result)
_TABLE=_table()
def fifa_crc(data):
 c=0xffffffff
 for byte in data:c=((c<<8)&0xffffffff)^_TABLE[(c>>24)^byte]
 return c

def container_crc(data):return zlib.crc32(data[160:])&0xffffffff
