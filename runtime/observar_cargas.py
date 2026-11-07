"""Observador temporal de lecturas DATA; una lectura no se declara activación."""
import ctypes as C
import hashlib
import json
import struct
import time
from pathlib import Path
import carreras as registry

HERE = DLL = TARGET_EXE = None
SAVE_CALL=0x1444e777e
LIFECYCLE_CALLS=(0x143d96efb,0x143d98e94,0x143da2dfb)

class Module(C.Structure):
    _fields_=[('size',C.c_ulong),('id',C.c_ulong),('pid',C.c_ulong),('global_use',C.c_ulong),('process_use',C.c_ulong),('base',C.c_void_p),('bytes',C.c_ulong),('handle',C.c_void_p),('name',C.c_wchar*256),('path',C.c_wchar*260)]
class Record(C.Structure):
    _fields_=[('seq',C.c_uint64),('tick',C.c_uint64),('thread',C.c_uint32),('requested',C.c_uint32),('actual',C.c_uint32),('result',C.c_int32),('overlapped',C.c_uint64),('bank_seq',C.c_uint64),('path_len',C.c_uint32),('stack_len',C.c_uint32),('prefix',C.c_ubyte*160),('path',C.c_uint16*512),('stack',C.c_uint64*32),('file_end',C.c_int64),('handle',C.c_uint64),('order',C.c_uint64)]
class Flow(C.Structure):
    _fields_=[('seq',C.c_uint64),('tick',C.c_uint64),('count',C.c_uint64),('name',C.c_ubyte*64),('arg',C.c_ubyte*32),('order',C.c_uint64)]
assert C.sizeof(Record)==1520 and C.sizeof(Flow)==128

def exports(path):
    b=path.read_bytes();pe=struct.unpack_from('<I',b,60)[0];opt=pe+24
    ns=struct.unpack_from('<H',b,pe+6)[0];sz=struct.unpack_from('<H',b,pe+20)[0]
    sections=[struct.unpack_from('<8sIIII',b,opt+sz+i*40) for i in range(ns)]
    def off(rva):
        for _,_,va,size,raw in sections:
            if va<=rva<va+size:return raw+rva-va
        raise ValueError('RVA is outside the image')
    def name(at):return b[at:b.index(b'\0',at)].decode('ascii')
    rva,_=struct.unpack_from('<II',b,opt+112);e=off(rva)
    n=struct.unpack_from('<I',b,e+24)[0];funcs,names,ords=struct.unpack_from('<III',b,e+28)
    return {name(off(struct.unpack_from('<I',b,off(names)+i*4)[0])):struct.unpack_from('<I',b,off(funcs)+struct.unpack_from('<H',b,off(ords)+i*2)[0]*4)[0] for i in range(n)}

class Process:
    def __init__(self,pid,readonly=False):
        self.pid=pid;self.k=C.WinDLL('kernel32',use_last_error=True);k=self.k
        k.OpenProcess.argtypes=[C.c_ulong,C.c_int,C.c_ulong];k.OpenProcess.restype=C.c_void_p
        k.CloseHandle.argtypes=[C.c_void_p]
        k.QueryFullProcessImageNameW.argtypes=[C.c_void_p,C.c_ulong,C.c_wchar_p,C.POINTER(C.c_ulong)]
        k.GetProcessTimes.argtypes=[C.c_void_p]+[C.c_void_p]*4
        k.ReadProcessMemory.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
        k.WriteProcessMemory.argtypes=k.ReadProcessMemory.argtypes
        k.VirtualAllocEx.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_ulong,C.c_ulong];k.VirtualAllocEx.restype=C.c_void_p
        k.VirtualFreeEx.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_ulong]
        k.VirtualProtectEx.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_ulong,C.POINTER(C.c_ulong)]
        k.FlushInstructionCache.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]
        k.CreateRemoteThread.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_ulong,C.c_void_p];k.CreateRemoteThread.restype=C.c_void_p
        k.WaitForSingleObject.argtypes=[C.c_void_p,C.c_ulong]
        k.GetExitCodeThread.argtypes=[C.c_void_p,C.POINTER(C.c_ulong)]
        k.GetExitCodeProcess.argtypes=[C.c_void_p,C.POINTER(C.c_ulong)]
        k.CreateToolhelp32Snapshot.argtypes=[C.c_ulong,C.c_ulong];k.CreateToolhelp32Snapshot.restype=C.c_void_p
        k.Module32FirstW.argtypes=[C.c_void_p,C.POINTER(Module)];k.Module32NextW.argtypes=k.Module32FirstW.argtypes
        k.GetModuleHandleW.argtypes=[C.c_wchar_p];k.GetModuleHandleW.restype=C.c_void_p
        k.GetProcAddress.argtypes=[C.c_void_p,C.c_char_p];k.GetProcAddress.restype=C.c_void_p
        k.GetModuleHandleExW.argtypes=[C.c_ulong,C.c_void_p,C.POINTER(C.c_void_p)]
        k.GetModuleFileNameW.argtypes=[C.c_void_p,C.c_wchar_p,C.c_ulong]
        self.h=k.OpenProcess(0x1010 if readonly else 0x1fffff,False,pid)
        if not self.h:raise C.WinError(C.get_last_error())
        try:
            name=C.create_unicode_buffer(32768);n=C.c_ulong(len(name))
            if not k.QueryFullProcessImageNameW(self.h,0,name,C.byref(n)):raise C.WinError(C.get_last_error())
            if Path(name.value).resolve()!=TARGET_EXE.resolve():raise ValueError('The process does not match the validated game path')
            times=[C.c_uint64() for _ in range(4)]
            if not k.GetProcessTimes(self.h,*[C.byref(t) for t in times]):raise C.WinError(C.get_last_error())
            self.creation=times[0].value
            registry.safe_source(registry.ACTIVE/'0/FIFA16')
        except Exception:
            self.close()
            raise
    def alive(self):
        code=C.c_ulong()
        if not self.k.GetExitCodeProcess(self.h,C.byref(code)):
            raise C.WinError(C.get_last_error())
        return code.value==259

    def patch_call(self,j,enable):
        sites=(SAVE_CALL,*LIFECYCLE_CALLS) if DLL.stem=='observer_v5' else (SAVE_CALL,)
        original={at:b'\xe8'+struct.pack('<i',0x144511560-at-5) for at in sites}
        if enable:
            if any(self.read(at,5)!=old for at,old in original.items()):raise ValueError('Unexpected native call site')
            relay=None
            for addr in range(0x146000000,0x150000000,0x10000):
                relay=self.k.VirtualAllocEx(self.h,addr,16,0x3000,4)
                if relay:break
            if not relay:raise ValueError('No nearby memory page is available')
            code=b'\xff\x25\0\0\0\0'+struct.pack('<Q',j['base']+exports(DLL)['Notify'])
            n=C.c_size_t();old=C.c_ulong()
            if not self.k.WriteProcessMemory(self.h,relay,C.c_char_p(code),len(code),C.byref(n)) or n.value!=len(code):raise C.WinError(C.get_last_error())
            if not self.k.VirtualProtectEx(self.h,relay,16,0x20,C.byref(old)):raise C.WinError(C.get_last_error())
            self.k.FlushInstructionCache(self.h,relay,16)
            j.update({'relay':relay,'call_old':original[SAVE_CALL].hex(),
                      'call_new':(b'\xe8'+struct.pack('<i',relay-SAVE_CALL-5)).hex()})
        if 'relay' not in j:return
        (HERE/f'{DLL.stem}_{self.pid}.json').write_text(json.dumps(j,indent=2))
        patched={at:b'\xe8'+struct.pack('<i',j['relay']-at-5) for at in sites}
        expected,want=(original,patched) if enable else (patched,original)
        if all(self.read(at,5)==new for at,new in want.items()):return
        nt=C.WinDLL('ntdll')
        for fn in (nt.NtSuspendProcess,nt.NtResumeProcess):fn.argtypes=[C.c_void_p];fn.restype=C.c_long
        if nt.NtSuspendProcess(self.h)<0:raise ValueError('Could not suspend FIFA')
        def write(at,value):
            old=C.c_ulong();n=C.c_size_t()
            if not self.k.VirtualProtectEx(self.h,at,5,0x40,C.byref(old)):raise C.WinError(C.get_last_error())
            try:
                if not self.k.WriteProcessMemory(self.h,at,C.c_char_p(value),5,C.byref(n)) or n.value!=5 or self.read(at,5)!=value:
                    raise ValueError('Incomplete write at a call site')
                self.k.FlushInstructionCache(self.h,at,5)
            finally:
                ignored=C.c_ulong();self.k.VirtualProtectEx(self.h,at,5,old.value,C.byref(ignored))
        changed=[]
        try:
            if any(self.read(at,5)!=old for at,old in expected.items()):raise ValueError('The call site changed')
            for at,new in want.items():
                changed.append(at)
                write(at,new)
        except Exception:
            for at in reversed(changed):
                write(at,expected[at])
            raise
        finally:
            nt.NtResumeProcess(self.h)
    def close(self):self.k.CloseHandle(self.h)
    def read(self,at,n):
        b=C.create_string_buffer(n);got=C.c_size_t()
        if not self.k.ReadProcessMemory(self.h,at,b,n,C.byref(got)) or got.value!=n:raise C.WinError(C.get_last_error())
        return b.raw
    def modules(self):
        h=self.k.CreateToolhelp32Snapshot(0x18,self.pid);m=Module();m.size=C.sizeof(m);out=[]
        try:
            ok=self.k.Module32FirstW(h,C.byref(m))
            while ok:out.append((m.name,m.base,m.bytes,m.path));ok=self.k.Module32NextW(h,C.byref(m))
        finally:self.k.CloseHandle(h)
        return out
    def remote(self,fn,arg=0):
        h=self.k.CreateRemoteThread(self.h,None,0,fn,arg,0,None)
        if not h:raise C.WinError(C.get_last_error())
        try:
            if self.k.WaitForSingleObject(h,15000)!=0:raise ValueError('The remote call did not finish. Close FIFA before retrying')
            result=C.c_ulong()
            if not self.k.GetExitCodeThread(h,C.byref(result)):raise C.WinError(C.get_last_error())
            return result.value
        finally:self.k.CloseHandle(h)
    def load(self):
        found=[m for m in self.modules() if Path(m[3]).resolve()==DLL.resolve()]
        if found:return found[0][1]
        k=self.k;local=k.GetProcAddress(k.GetModuleHandleW('kernel32.dll'),b'LoadLibraryW')
        owner=C.c_void_p()
        if not k.GetModuleHandleExW(6,local,C.byref(owner)):raise C.WinError(C.get_last_error())
        name=C.create_unicode_buffer(1024);k.GetModuleFileNameW(owner,name,1024)
        mod=next(m for m in self.modules() if m[0].lower()==Path(name.value).name.lower())
        remote=mod[1]+local-owner.value
        if self.read(remote,32)!=C.string_at(local,32):raise ValueError('The remote system function does not match')
        self.remote_buffer(remote, (str(DLL.resolve())+'\0').encode('utf-16le'))
        return next(m[1] for m in self.modules() if Path(m[3]).resolve()==DLL.resolve())

    def remote_buffer(self, function, data):
        k = self.k
        mem = k.VirtualAllocEx(self.h, None, len(data), 0x3000, 4)
        if not mem:
            raise C.WinError(C.get_last_error())
        started = False
        complete = False
        try:
            size = C.c_size_t()
            if not k.WriteProcessMemory(self.h, mem, C.c_char_p(data), len(data), C.byref(size)) or size.value != len(data):
                raise C.WinError(C.get_last_error())
            started = True
            result = self.remote(function, mem)
            complete = True
            return result
        finally:
            if complete or not started:
                k.VirtualFreeEx(self.h, mem, 0, 0x8000)

def event_record(record):
    raw=C.string_at(C.addressof(record)+Record.path.offset,record.path_len*2)
    return {'seq':record.seq,'tick':record.tick,'thread':record.thread,'requested':record.requested,'actual':record.actual,'result':record.result,
        'overlapped':record.overlapped,'bank_seq':record.bank_seq,'path':raw.decode('utf-16le'),
        'prefix':bytes(record.prefix).hex(),'file_end':record.file_end,'handle':record.handle,'order':record.order,'stack':[hex(v) for v in record.stack[:record.stack_len]]}

def run(pid,action,quiet=False):
    p=Process(pid);symbols=exports(DLL);journal=HERE/f'{DLL.stem}_{pid}.json'
    installed=False
    try:
        if action=='uninstall':
            j=json.loads(journal.read_text());assert j['creation']==p.creation
            p.patch_call(j,False)
            if p.remote(j['base']+symbols['Uninstall'])!=1:raise ValueError('Could not remove the observer hook')
            assert struct.unpack('<Q',p.read(0x145f682c8,8))[0]==j['original_iat']
            j['state']='uninstalled_dll_passive_until_process_exit';journal.write_text(json.dumps(j,indent=2));return
        if journal.exists():raise ValueError('An observer journal already exists for this process')
        from estado_activo import career_inventory
        registry.safe_source(registry.ACTIVE/'0/FIFA16')
        career_baseline=career_inventory(registry.ACTIVE)
        base=p.load();old=struct.unpack('<Q',p.read(0x145f682c8,8))[0]
        j={'pid':pid,'creation':p.creation,'base':base,'original_iat':old,'dll_sha256':hashlib.sha256(DLL.read_bytes()).hexdigest(),
           'career_inventory_before':career_baseline,'state':'installing'}
        journal.write_text(json.dumps(j,indent=2))
        expected = (str(TARGET_EXE)+'\0').encode('utf-16le')
        if len(expected) > 65_536:
            raise ValueError('The configured game path is too long')
        result=p.remote_buffer(base+symbols['Install'], expected.ljust(65_536, b'\0'))
        if result!=1:raise ValueError(f'Observer installation rejected: {result}')
        installed=True
        p.patch_call(j,True)
        j['state']='observing';journal.write_text(json.dumps(j,indent=2));print('Observer installed. Waiting for DATA reads and a verified Career Mode load.',flush=True)
        last=0;bank=0;segments={};last_flow=0;last_heartbeat=0
        def read_symbol(name,n=8):return p.read(base+symbols[name],n)
        def emit(value):
            with (HERE/f'cargas_{DLL.stem}_{pid}.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
            if not quiet and value['kind']!='watcher_heartbeat':
                print(json.dumps({k:v for k,v in value.items() if k!='event'},ensure_ascii=False),flush=True)
        def permitted(record):
            if record.path_len>511 or record.stack_len>32:return False
            name=event_record(record)['path']
            if name.startswith('\\\\?\\'):name=name[4:]
            try:return registry.safe_source(name).is_relative_to(registry.ACTIVE/'0/FIFA16')
            except (ValueError,FileNotFoundError):return False
        while p.alive():
            count=struct.unpack('<Q',read_symbol('OBS_COUNT'))[0]
            if count-last>64:
                first=count-63
                r=Record.from_buffer_copy(p.read(base+symbols['OBS_RECORDS']+((first-1)%64)*C.sizeof(Record),C.sizeof(Record)))
                emit({'kind':'overrun','lost_at_least':count-last-64,
                      'through_order':r.order-1 if r.seq==first else None})
            for seq in range(max(last+1,count-63),count+1):
                r=Record.from_buffer_copy(p.read(base+symbols['OBS_RECORDS']+((seq-1)%64)*C.sizeof(Record),C.sizeof(Record)))
                if r.seq==seq and permitted(r):
                    e=event_record(r);emit({'kind':'data_read','event':e})
                    start=r.file_end-r.actual
                    key=(r.handle,e['path'])
                    if start==80 and r.actual==16:segments[key]=[]
                    if start>=0 and r.actual<=160:segments.setdefault(key,[]).append((start,bytes(r.prefix)[:r.actual]))
            last=count
            current=struct.unpack('<Q',read_symbol('OBS_BANK_SEQ'))[0]
            if current and current%2==0 and current!=bank:
                size=struct.unpack('<Q',read_symbol('OBS_BANK_LEN'))[0]
                r=Record.from_buffer_copy(read_symbol('OBS_BANK_RECORD',C.sizeof(Record)))
                if size<=16*1024*1024:
                    data=read_symbol('OBS_BANK',size)
                    if struct.unpack('<Q',read_symbol('OBS_BANK_SEQ'))[0]==current and r.bank_seq==current and permitted(r):
                        start=r.file_end-r.actual
                        header=bytearray(max(0,start));filled=bytearray(len(header))
                        for at,chunk in segments.get((r.handle,event_record(r)['path']),[]):
                            if 0<=at and at+len(chunk)<=len(header):header[at:at+len(chunk)]=chunk;filled[at:at+len(chunk)]=b'1'*len(chunk)
                        if start<0 or start>512 or (len(header) and not all(filled)):
                            bank=current;emit({'kind':'incomplete_native_header','bank_seq':current,'offset':start});continue
                        bank=current;data=bytes(header)+data
                        if data[116:132]==b'SaveType_Career\0':
                            try:
                                s=registry.SaveSnapshot.from_bytes(data,registry.SCHEMA)
                                integrity=registry.validate_snapshot(s)
                            except ValueError as exc:
                                emit({'kind':'invalid_career_data','error':str(exc),'event':event_record(r)})
                            else:
                                emit({'kind':f'complete_DATA_{integrity}','sha256':s.sha256,'event':event_record(r),
                                      'activation_status':'read_completed_only_not_yet_proven_activation'})
            flow_count=struct.unpack('<Q',read_symbol('FLOW_COUNT'))[0]
            if flow_count-last_flow>64:
                first=flow_count-63
                f=Flow.from_buffer_copy(p.read(base+symbols['FLOWS']+((first-1)%64)*C.sizeof(Flow),C.sizeof(Flow)))
                emit({'kind':'overrun','lost_flows_at_least':flow_count-last_flow-64,
                      'through_order':f.order-1 if f.seq==first else None})
            for seq in range(max(last_flow+1,flow_count-63),flow_count+1):
                f=Flow.from_buffer_copy(p.read(base+symbols['FLOWS']+((seq-1)%64)*C.sizeof(Flow),C.sizeof(Flow)))
                if f.seq==seq:emit({'kind':'native_flow_complete','flow':bytes(f.name).split(b'\0')[0].decode('ascii',errors='replace'),'status_ptr':f.count,'native_status':p.read(f.count,32).split(b'\0')[0].decode('ascii',errors='replace') if 0x140000000<=f.count<0x146000000 else 'UNKNOWN','arg0':bytes(f.arg).split(b'\0')[0].decode('ascii',errors='replace'),'order':f.order,'tick':f.tick,'seq':f.seq})
            last_flow=flow_count
            if time.time()-last_heartbeat>=1:
                last_heartbeat=time.time();emit({'kind':'watcher_heartbeat','time':last_heartbeat})
            time.sleep(.05)
        j['state']='process_ended';journal.write_text(json.dumps(j,indent=2))
    except OSError:
        if not installed or p.alive():
            raise
        j['state']='process_ended';journal.write_text(json.dumps(j,indent=2))
    finally:
        try:
            if installed and p.alive():
                p.patch_call(j,False)
                result=p.remote(base+symbols['Uninstall'])
                if result!=1:print('Could not remove the observer hook. Close FIFA before retrying.',flush=True)
                else:
                    j['state']='uninstalled_dll_passive_until_process_exit';journal.write_text(json.dumps(j,indent=2))
        finally:
            p.close()
