"""Bounded read-only parsing, no guessed repair of unrecognized formats."""
from dataclasses import dataclass,field
from pathlib import Path
import hashlib,struct
from .checksums import fifa_crc,container_crc
from .schema import load_schema
SIGNATURE=b'DB\x00\x08\x00\x00\x00\x00'
KNOWN={'RrqT':'teamplayerlinks','CZUM':'players','lyxL':'teams'}
class SaveError(ValueError):pass
@dataclass(frozen=True)
class Check:
 name:str
 offset:int
 stored:int
 calculated:int
 @property
 def valid(self):return self.stored==self.calculated
@dataclass(frozen=True)
class Field:
 short:str
 name:str
 type:int
 bit:int
 depth:int
 low:int=0
@dataclass
class Table:
 short:str
 name:str
 header:int
 end:int
 record_start:int
 record_size:int
 written:int
 capacity:int
 cancelled:int
 database:int
 fields:dict
 aliases:dict=field(default_factory=dict)
 def get_field(self,name):
  key=self.aliases.get(name,name)
  if key not in self.fields:raise SaveError(f'Field missing: {self.name}.{name}')
  return self.fields[key]
 def active_rows(self,data):
  for i in range(self.written):
   if not data[self.record_start+(i+1)*self.record_size-1]&128:yield i
 def value(self,data,row,name):
  f=self.get_field(name)
  if not 0<=row<self.written:raise SaveError('Row out of bounds.')
  start=self.record_start+row*self.record_size
  if f.type==0:
   offset=start+f.bit//8
   return bytes(data[offset:offset+f.depth//8]).split(b'\0')[0].decode('utf-8',errors='replace')
  if f.type!=3:raise SaveError(f'Field is not numeric: {self.name}.{name}')
  bit=f.bit%8;offset=start+f.bit//8;n=(bit+f.depth+7)//8
  raw=(int.from_bytes(data[offset:offset+n],'little')>>bit)&((1<<f.depth)-1)
  return raw+f.low

@dataclass
class SaveSnapshot:
 data:bytes
 tables:list
 databases:list
 path:Path|None=None
 is_container:bool=True
 schema:dict=field(default_factory=dict)
 @property
 def sha256(self):return hashlib.sha256(self.data).hexdigest()
 @classmethod
 def read(cls,path,metadata=None):
  path=Path(path)
  if path.is_dir():path=path/'DATA'
  s=cls.from_bytes(path.read_bytes(),metadata);s.path=path.resolve();return s
 @classmethod
 def from_bytes(cls,data,metadata=None,container=True):
  data=bytes(data);schema=load_schema(metadata) if not isinstance(metadata,dict) else metadata
  schema=schema or {};tables=[];dbs=[];cursor=0
  def u32(p):
   if p<0 or p+4>len(data):raise SaveError('Truncated structure.')
   return struct.unpack_from('<I',data,p)[0]
  while True:
   db=data.find(SIGNATURE,cursor)
   if db<0:break
   size=u32(db+8);count=u32(db+16);end=db+size;directory_end=db+24+8*count
   if count<1 or count>1000 or size<28 or end>len(data) or directory_end+4>end:raise SaveError('Unknown or truncated embedded database.')
   entries=[];names=set()
   for i in range(count):
    p=db+24+8*i;short=data[p:p+4].decode('latin1');h=directory_end+4+u32(p+4)
    if short in names:raise SaveError('Duplicate database table.')
    names.add(short);entries.append((h,short))
   entries.sort()
   if len({h for h,_ in entries})!=count:raise SaveError('Overlapping tables.')
   for j,(h,short) in enumerate(entries):
    te=entries[j+1][0] if j+1<count else end
    if h<directory_end+4 or h+40>te:raise SaveError('Invalid table bounds.')
    rs=u32(h+4);capacity,written,cancelled=struct.unpack_from('<HHH',data,h+16);nf=data[h+24]
    rec=h+36+nf*16
    if not rs or not nf or written>capacity or cancelled>written or rec+capacity*rs>te-4:raise SaveError('Invalid table capacity or size.')
    fields={};aliases={};tm=schema.get(short,{});mf=tm.get('fields',{})
    for k in range(nf):
     fp=h+36+16*k
     if fp+16>te-4:raise SaveError('Truncated field descriptor.')
     typ,bit=struct.unpack_from('<II',data,fp);sn=data[fp+8:fp+12].decode('latin1');depth=u32(fp+12);meta=mf.get(sn,{})
     if sn in fields or depth<1:raise SaveError('Invalid or duplicate field.')
     actual_depth=32 if typ in (13,14,4) else depth
     if bit+actual_depth>rs*8:raise SaveError('Field exceeds record bounds.')
     # The Career Stats schema lists only fields used by tracking.
     if meta and (typ==3 or 'career_type' in meta):
      mismatch=int(meta.get('depth',depth))!=depth or typ!=meta.get('career_type',typ)
      if mismatch and meta.get('optional'):meta={}
      elif mismatch:raise SaveError(f'Incompatible save field: {tm["name"]}.{meta["name"]}')
     name=meta.get('name',sn);low=int(meta.get('rangelow',0));fields[sn]=Field(sn,name,typ,bit,depth,low);aliases[name]=sn
    name=tm.get('name',KNOWN.get(short,short));t=Table(short,name,h,te,rec,rs,written,capacity,cancelled,db,fields,aliases)
    if sum(1 for _ in t.active_rows(data))!=written-cancelled:raise SaveError(f'Inconsistent deleted-row count: {name}')
    tables.append(t)
   dbs.append((db,directory_end,end));cursor=end
  if not dbs or (container and (len(data)<160 or dbs[0][0]<160)):raise SaveError('This file does not contain a recognized Career Mode DATA container.')
  return cls(data,tables,dbs,None,container,schema)
 def table(self,name,required=True):
  found=[t for t in self.tables if t.name==name or t.short==name]
  if len(found)>1:raise SaveError(f'Ambiguous table: {name}')
  if not found:
   if required:raise SaveError(f'Table missing: {name}')
   return None
  return found[0]
 def audit(self):
  b=self.data;out=[]
  def check(name,start,end):out.append(Check(name,end,struct.unpack_from('<I',b,end)[0],fifa_crc(memoryview(b)[start:end])))
  for db,de,_ in self.databases:check('DB header',db,db+20);check('DB directory',db+24,de)
  for t in self.tables:check(t.name+' header',t.header,t.header+32);check(t.name+' records',t.header+36,t.end-4)
  if self.is_container:out.append(Check('DATA global',132,struct.unpack_from('<I',b,132)[0],container_crc(b)))
  return out
 def require_valid(self):
  bad=[c.name for c in self.audit() if not c.valid]
  if bad:raise SaveError('Failed CRC checks: '+', '.join(bad))
