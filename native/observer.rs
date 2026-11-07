//! ReadFile observer: configured game process only. No filesystem writes; original call/last error preserved.
use std::{ffi::c_void,ptr,sync::atomic::{AtomicBool,AtomicU64,AtomicUsize,Ordering}};
type H=*mut c_void;
type Read=unsafe extern "system" fn(H,*mut c_void,u32,*mut u32,*mut c_void)->i32;
#[link(name="kernel32")]extern "system"{
 fn GetModuleFileNameW(h:H,p:*mut u16,n:u32)->u32;
 fn GetModuleHandleW(p:*const u16)->H;
 fn GetProcAddress(h:H,p:*const u8)->*mut c_void;
 fn VirtualProtect(p:H,n:usize,new:u32,old:*mut u32)->i32;
 fn GetLastError()->u32;fn SetLastError(v:u32);
 fn GetFinalPathNameByHandleW(h:H,p:*mut u16,n:u32,flags:u32)->u32;
 fn GetFileSizeEx(h:H,n:*mut i64)->i32;
 fn GetTickCount64()->u64;fn GetCurrentThreadId()->u32;
 fn GetCurrentThreadStackLimits(low:*mut usize,high:*mut usize);
 fn RtlCaptureStackBackTrace(skip:u32,n:u32,p:*mut H,hash:*mut u32)->u16;
}
#[link(name="ntdll")]extern "system"{fn NtQueryInformationFile(h:H,ios:*mut u64,info:H,length:u32,class:u32)->i32;}
const IAT:usize=0x145f682c8;
const MAX:usize=16*1024*1024;
#[repr(C)]#[derive(Copy,Clone)]pub struct Record{
 pub seq:u64,pub tick:u64,pub thread:u32,pub requested:u32,pub actual:u32,pub result:i32,
 pub overlapped:u64,pub bank_seq:u64,pub path_len:u32,pub stack_len:u32,
 pub prefix:[u8;160],pub path:[u16;512],pub stack:[u64;32],pub file_end:i64,pub handle:u64,pub order:u64,
}
const EMPTY:Record=Record{seq:0,tick:0,thread:0,requested:0,actual:0,result:0,overlapped:0,bank_seq:0,path_len:0,stack_len:0,prefix:[0;160],path:[0;512],stack:[0;32],file_end:-1,handle:0,order:0};
static ORIGINAL:AtomicUsize=AtomicUsize::new(0);
static LOCK:AtomicBool=AtomicBool::new(false);
static ORDER:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static OBS_COUNT:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static OBS_DROPPED:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static OBS_BANK_SEQ:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static OBS_BANK_LEN:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static mut OBS_BANK_RECORD:Record=EMPTY;
#[no_mangle]pub static mut OBS_RECORDS:[Record;64]=[EMPTY;64];
#[no_mangle]pub static mut OBS_BANK:[u8;MAX]=[0;MAX];
#[repr(C)]#[derive(Copy,Clone)]pub struct Flow{pub seq:u64,pub tick:u64,pub count:u64,pub name:[u8;64],pub arg:[u8;32],pub order:u64}
const NOFLOW:Flow=Flow{seq:0,tick:0,count:0,name:[0;64],arg:[0;32],order:0};
#[no_mangle]pub static FLOW_COUNT:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static FLOW_DROPPED:AtomicU64=AtomicU64::new(0);
#[no_mangle]pub static mut FLOWS:[Flow;64]=[NOFLOW;64];
static FLOW_LOCK:AtomicBool=AtomicBool::new(false);
type Send=unsafe extern "system" fn(usize,usize,usize,usize,usize,usize,usize)->u64;
unsafe fn record_flow(mut event:Flow){
 if FLOW_LOCK.compare_exchange(false,true,Ordering::Acquire,Ordering::Relaxed).is_err(){
  FLOW_DROPPED.fetch_add(1,Ordering::Relaxed);return;
 }
 event.tick=GetTickCount64();
 let seq=FLOW_COUNT.load(Ordering::Relaxed)+1;
 event.seq=seq;event.order=ORDER.fetch_add(1,Ordering::SeqCst)+1;
 ptr::write((ptr::addr_of_mut!(FLOWS) as *mut Flow).add(((seq-1)%64) as usize),event);
 FLOW_COUNT.store(seq,Ordering::Release);FLOW_LOCK.store(false,Ordering::Release);
}
#[no_mangle]pub unsafe extern "system" fn Notify(a:usize,b:usize,name:usize,n:usize,args:usize,f:usize,g:usize)->u64{
 let mut event=NOFLOW;event.count=n as u64;
 let lifecycle=matches!(name,0x1421a4e78|0x1421a5ec8);
 if lifecycle || (0x1422322e0..=0x1422324c8).contains(&name){
  for i in 0..63{let x=*((name+i) as *const u8);if x==0{break;}event.name[i]=x;}
  let(mut low,mut high)=(0usize,0usize);GetCurrentThreadStackLimits(&mut low,&mut high);
  if args>=low && args+16<=high{
   for i in 0..16{let x=*((args+i) as *const u8);if x==0{break;}event.arg[i]=x;}
  }
 }
 if lifecycle {record_flow(event);}
 let original:Send=std::mem::transmute(0x144511560usize);
 let result=original(a,b,name,n,args,f,g);
 if !lifecycle && event.name[0]!=0 {record_flow(event);}
 result
}

unsafe extern "system" fn observed(h:H,buf:*mut c_void,n:u32,actual:*mut u32,over:*mut c_void)->i32{
 let f:Read=std::mem::transmute(ORIGINAL.load(Ordering::Acquire));
 let result=f(h,buf,n,actual,over);let last=GetLastError();
 let mut r=EMPTY;let len=GetFinalPathNameByHandleW(h,r.path.as_mut_ptr(),512,0);
 if len>=4 && len<512 && r.path[len as usize-4..len as usize].iter().zip([b'D',b'A',b'T',b'A']).all(|(a,b)|(*a as u8).to_ascii_uppercase()==b){
  if LOCK.compare_exchange(false,true,Ordering::Acquire,Ordering::Relaxed).is_ok(){
   r.tick=GetTickCount64();r.thread=GetCurrentThreadId();r.requested=n;r.result=result;r.overlapped=over as u64;r.path_len=len;
   r.actual=if !actual.is_null(){*actual}else{0};r.handle=h as u64;r.order=ORDER.fetch_add(1,Ordering::SeqCst)+1;
   let mut ios=[0u64;2];let mut position=-1i64;
   if over.is_null() && NtQueryInformationFile(h,ios.as_mut_ptr(),&mut position as *mut i64 as H,8,14)>=0{r.file_end=position;}
   r.stack_len=RtlCaptureStackBackTrace(0,32,r.stack.as_mut_ptr() as *mut H,ptr::null_mut()) as u32;
   if result!=0 && r.actual>0 && !buf.is_null(){ptr::copy_nonoverlapping(buf as *const u8,r.prefix.as_mut_ptr(),(r.actual as usize).min(160));}
   let mut size=0i64;
   if result!=0 && over.is_null() && r.actual>=5_000_000 && r.actual as usize<=MAX
      && GetFileSizeEx(h,&mut size)!=0 && r.file_end==size && size>=r.actual as i64 && size-r.actual as i64<=512{
    OBS_BANK_SEQ.fetch_add(1,Ordering::SeqCst);
    ptr::copy_nonoverlapping(buf as *const u8,ptr::addr_of_mut!(OBS_BANK) as *mut u8,r.actual as usize);
    OBS_BANK_LEN.store(r.actual as u64,Ordering::SeqCst);
    r.bank_seq=OBS_BANK_SEQ.load(Ordering::SeqCst)+1;
    ptr::write(ptr::addr_of_mut!(OBS_BANK_RECORD),r);
    OBS_BANK_SEQ.fetch_add(1,Ordering::SeqCst);
   }
   let seq=OBS_COUNT.load(Ordering::Relaxed)+1;r.seq=seq;
   ptr::write((ptr::addr_of_mut!(OBS_RECORDS) as *mut Record).add(((seq-1)%64) as usize),r);
   OBS_COUNT.store(seq,Ordering::Release);LOCK.store(false,Ordering::Release);
  }else{OBS_DROPPED.fetch_add(1,Ordering::Relaxed);}
 }
 SetLastError(last);result
}

#[no_mangle]pub unsafe extern "system" fn Install(expected_path:H)->u32{
 // The launcher supplies a fixed-size UTF-16 buffer after checking the exact
 // disk fingerprint and the path of this process.
 if expected_path.is_null(){return 10;}
 let mut path=vec![0u16;32768];
 let n=GetModuleFileNameW(ptr::null_mut(),path.as_mut_ptr(),path.len() as u32) as usize;
 if n==0 || n>=path.len(){return 10;}
 let Ok(actual)=String::from_utf16(&path[..n]) else {return 10;};
 let expected=std::slice::from_raw_parts(expected_path as *const u16,32768);
 let Some(end)=expected.iter().position(|&unit|unit==0) else {return 10;};
 let Ok(expected)=String::from_utf16(&expected[..end]) else {return 10;};
 if actual.to_lowercase()!=expected.to_lowercase(){return 10;}
 if GetModuleHandleW(ptr::null()) as usize!=0x140000000{return 11;}
 let k:[u16;13]=[107,101,114,110,101,108,51,50,46,100,108,108,0];
 let native=GetProcAddress(GetModuleHandleW(k.as_ptr()),b"ReadFile\0".as_ptr()) as usize;
 let slot=&*(IAT as *const AtomicUsize);let old=slot.load(Ordering::SeqCst);
 if old==observed as *const () as usize{return 1;}if old!=native || old==0{return 12;}
 ORIGINAL.store(old,Ordering::Release);
 let mut protect=0;if VirtualProtect(IAT as H,8,4,&mut protect)==0{return 13;}
 let ok=slot.compare_exchange(old,observed as *const () as usize,Ordering::SeqCst,Ordering::SeqCst).is_ok();
 let mut ignored=0;VirtualProtect(IAT as H,8,protect,&mut ignored);
 if ok{1}else{14}
}
#[no_mangle]pub unsafe extern "system" fn Uninstall(_:H)->u32{
 let slot=&*(IAT as *const AtomicUsize);let old=ORIGINAL.load(Ordering::Acquire);
 if old==0{return 1;}if slot.load(Ordering::SeqCst)==old{return 1;}
 if slot.load(Ordering::SeqCst)!=observed as *const () as usize{return 20;}
 let mut protect=0;if VirtualProtect(IAT as H,8,4,&mut protect)==0{return 21;}
 let ok=slot.compare_exchange(observed as *const () as usize,old,Ordering::SeqCst,Ordering::SeqCst).is_ok();
 let mut ignored=0;VirtualProtect(IAT as H,8,protect,&mut ignored);
 if ok{1}else{22}
}
