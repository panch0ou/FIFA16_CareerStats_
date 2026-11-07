use apt::{actions::{opcode as o,ActionStream,DictRefKind as D,Instruction as I,PushStringKind as S},AptFile,Character,CharacterSlot,Control,Value};
use std::{env,fs};
fn op(x:u8)->I{I::Simple(x)}
fn lit(x:&str)->I{I::PushString{kind:S::Push,value:x.into()}}
fn mem(x:u16)->I{I::DictRef{kind:D::ByteGetMember,index:x}}
fn p(x:&str)->Vec<I>{vec![I::PushRegister(1),lit(x),op(o::GET_MEMBER)]}
fn set(v:&mut Vec<I>,x:&str,w:Vec<I>){v.extend([I::PushRegister(1),lit(x)]);v.extend(w);v.push(op(o::SET_MEMBER));}
fn call(obj:Vec<I>,name:&str,args:Vec<Vec<I>>)->Vec<I>{let mut v=vec![];let n=args.len();for a in args.into_iter().rev(){v.extend(a);}v.push(I::PushByte(n as u8));v.extend(obj);v.extend([lit(name),op(o::CALL_METHOD)]);v}
fn test(v:&mut Vec<I>)->usize{let n=v.len();v.push(I::BranchIfFalse{target:0});n}
fn end(v:&mut Vec<I>,n:usize){v[n]=I::BranchIfFalse{target:v.len()};}
fn add(mut a:Vec<I>,b:Vec<I>)->Vec<I>{a.extend(b);a.push(op(o::ADD2));a}
fn text(v:&mut Vec<I>,path:Vec<I>,value:Vec<I>){v.extend(path);v.push(lit("text"));v.extend(value);v.push(op(o::SET_MEMBER));}
fn row(v:&mut Vec<I>,field:u16,value:Vec<I>){text(v,vec![I::PushRegister(3),mem(field)],value)}
fn visible(v:&mut Vec<I>,yes:bool){v.extend([I::PushRegister(3),lit("_visible"),op(if yes{o::EA_PUSH_TRUE}else{o::EA_PUSH_FALSE}),op(o::SET_MEMBER)]);}
fn at(name:&str,index:u8)->Vec<I>{let mut v=p(name);v.extend([I::PushByte(index),op(o::GET_MEMBER)]);v}
fn live_totals(v:&mut Vec<I>){
 for field in [178,180,182]{
  v.extend([I::PushRegister(1),mem(44),mem(173),mem(field),
   I::DictRef{kind:D::PushByte,index:62},
   I::DictRef{kind:D::ByteGetVar,index:1},mem(12),mem(63),mem(64),op(o::SET_MEMBER)]);
 }
 for (path,index) in [
  (vec![I::PushRegister(1),mem(44),mem(80),mem(125)],1),
  (vec![I::PushRegister(1),mem(44),mem(80),mem(129)],2),
  (vec![I::PushRegister(1),mem(44),mem(173),mem(180)],3),
  (vec![I::PushRegister(1),mem(44),mem(173),mem(182)],4)]{
  let fallback=if index==4{"CS -"}else if index==2{"-"}else{"-       -       -"};
  text(v,path.clone(),vec![lit(fallback)]);
  v.extend(p("_extCount"));v.extend([I::PushByte(0),op(o::GREATER)]);let absent=test(v);
  text(v,path,at("_dParts",index));end(v,absent);
 }
}
fn patch_render(body:&mut ActionStream,capacity:usize,buckets:u32,fulham:&[u32],live:bool){
 let v=&mut body.instructions;
 // Keep captured Fulham records/totals as a distinct, unchanged source.
 v.extend([I::PushRegister(1),mem(35),mem(68),op(o::TO_NUMBER),I::PushDWord(144),op(o::EQUALS2)]);
 let mut any=false;
 for id in fulham {v.extend(p("_historyPlayerId"));v.extend([I::PushDWord(*id),op(o::EQUALS2)]);if any{v.push(op(o::OR));}any=true;}
 if !any{v.push(op(o::EA_PUSH_FALSE));}
 v.extend([op(o::AND),op(o::NOT)]);let preserve=test(v);
 // One lookup per player/instance. Pending cache is retried by the existing row refresh.
 v.extend([I::PushRegister(7),I::PushByte(0),op(o::EQUALS2)]);let first=test(v);
 v.extend(p("_extId"));v.extend(p("_historyPlayerId"));v.extend([op(o::EQUALS2),op(o::NOT)]);
 v.extend(p("_extLoaded"));v.extend([op(o::NOT),op(o::OR)]);let unchanged=test(v);
 set(v,"_extId",p("_historyPlayerId"));set(v,"_extCount",vec![I::PushByte(0)]);
 set(v,"_extStatus",vec![lit("LOADING EXTERNAL HISTORY")]);
 for bucket in 0..buckets {
  v.extend(p("_historyPlayerId"));v.extend([I::PushDWord(buckets),op(o::MODULO),I::PushDWord(bucket),op(o::EQUALS2)]);let other=test(v);
  let family=if live{"12D"}else{"12B8"};
  let prefix=format!("{family}_BUCKET_{bucket:03}_WAIT\n");let guard=format!("END_BUCKET_{bucket:03}");
  set(v,"_extPool",vec![lit(&format!("{}{}{}",prefix," ".repeat(capacity-prefix.len()-guard.len()),guard))]);end(v,other);
 }
 let mut ready=call(p("_extPool"),"indexOf",vec![vec![lit("_READY\n")]]);ready.extend([I::PushByte(0),op(o::GREATER)]);
 set(v,"_extLoaded",ready);v.extend(p("_extLoaded"));let waiting=test(v);
 set(v,"_extStatus",vec![lit("NO HISTORY AVAILABLE")]);
 set(v,"_extKey",add(add(vec![lit("\n")],p("_historyPlayerId")),vec![lit("|")]));
 set(v,"_extStart",call(p("_extPool"),"indexOf",vec![p("_extKey")]));
 v.extend(p("_extStart"));v.extend([I::PushByte(0),op(o::LESS_THAN2),op(o::NOT)]);let missing=test(v);
 let mut start=p("_extStart");start.extend(p("_extKey"));start.extend([lit("length"),op(o::GET_MEMBER),op(o::ADD2)]);set(v,"_extStart",start);
 set(v,"_extEnd",call(p("_extPool"),"indexOf",vec![vec![lit("\n")],p("_extStart")]));
 let line=call(p("_extPool"),"substring",vec![p("_extStart"),p("_extEnd")]);
 if live{
  set(v,"_dParts",call(line,"split",vec![vec![lit("|")]]));
  set(v,"_extRows",call(at("_dParts",0),"split",vec![vec![lit("^")]]));
 }else{set(v,"_extRows",call(line,"split",vec![vec![lit("^")]]));}
 let mut count=p("_extRows");count.extend([lit("length"),op(o::GET_MEMBER)]);set(v,"_extCount",count);
 v.extend(p("_extCount"));v.extend([I::PushDWord(512),op(o::GREATER)]);let within=test(v);
 set(v,"_extCount",vec![I::PushByte(0)]);set(v,"_extStatus",vec![lit("HISTORY LIMIT 512")]);end(v,within);
 v.extend(p("_extCount"));v.extend([I::PushByte(0),op(o::GREATER)]);let empty=test(v);
 set(v,"_extStatus",if live{at("_dParts",5)}else{vec![lit("PRE-2015 EXTERNAL HISTORY")]});end(v,empty);
 end(v,missing);end(v,waiting);end(v,unchanged);
 let mut pages=p("_extCount");pages.extend([I::PushByte(15),op(o::ADD2),I::PushByte(16),op(o::DIVIDE),op(o::TO_INTEGER)]);set(v,"_historyPages",pages);
 v.extend(p("_historyPages"));v.extend([I::PushByte(1),op(o::LESS_THAN2)]);let positive=test(v);set(v,"_historyPages",vec![I::PushByte(1)]);end(v,positive);
 if live{
  v.extend(p("_historyPage"));v.extend(p("_historyPages"));v.extend([op(o::LESS_THAN2),op(o::NOT)]);
  let clamp=test(v);set(v,"_historyPage",vec![I::PushByte(0)]);end(v,clamp);
  live_totals(v);
 }
 let val=add(add(add(vec![lit("PAGE ")],add(p("_historyPage"),vec![I::PushByte(1)])),vec![lit(" / ")]),p("_historyPages"));
 text(v,vec![I::PushRegister(1),mem(48),mem(60)],val);
 text(v,p("_ph12b6_1"),p("_extStatus"));
 end(v,first);
 // Clear every visible slot before rendering the selected ID's external records.
 for field in [230,232,234,236,238,240]{row(v,field,vec![lit("")]);}visible(v,false);
 let mut ix=p("_historyPage");ix.extend([I::PushByte(16),op(o::MULTIPLY),I::PushRegister(7),op(o::ADD2)]);set(v,"_extRow",ix);
 v.extend(p("_extRow"));v.extend(p("_extCount"));v.push(op(o::LESS_THAN2));let absent=test(v);
 let mut record=p("_extRows");record.extend(p("_extRow"));record.push(op(o::GET_MEMBER));
 set(v,"_extFields",call(record,"split",vec![vec![lit("~")]]));visible(v,true);
 for (i,field) in [232,230,234,236,238,240].into_iter().enumerate(){let mut value=p("_extFields");value.extend([I::PushByte(i as u8),op(o::GET_MEMBER)]);row(v,field,value);}
 end(v,absent);
 v.extend(p("_extCount"));v.extend([I::PushByte(0),op(o::EQUALS2),I::PushRegister(7),I::PushByte(0),op(o::EQUALS2),op(o::AND)]);let has_data=test(v);visible(v,true);row(v,240,p("_extStatus"));end(v,has_data);
 end(v,preserve);
}
fn init(body:&mut ActionStream,live:bool){
 let v=&mut body.instructions;set(v,"_extLoaded",vec![op(o::EA_PUSH_TRUE)]);set(v,"_extTicks",vec![I::PushByte(0)]);
 let mut tick=vec![];set(&mut tick,"_extTicks",add(p("_extTicks"),vec![I::PushByte(1)]));
 tick.extend(p("_extTicks"));tick.extend([I::PushByte(30),op(o::LESS_THAN2),op(o::NOT)]);let slow=test(&mut tick);set(&mut tick,"_extTicks",vec![I::PushByte(0)]);
 if live{
  let marker="12D_EPOCH_WAIT";let guard="END_12D_EPOCH";
  set(&mut tick,"_dSeenEpoch",vec![lit(&format!("{marker}{}{guard}"," ".repeat(128-marker.len()-guard.len())))]);
  tick.extend(p("_dSeenEpoch"));tick.extend(p("_dEpoch"));tick.extend([op(o::EQUALS2),op(o::NOT)]);
  let changed=test(&mut tick);
  set(&mut tick,"_dEpoch",p("_dSeenEpoch"));
  set(&mut tick,"_extLoaded",vec![op(o::EA_PUSH_FALSE)]);
  set(&mut tick,"_historyPage",vec![I::PushByte(0)]);
  end(&mut tick,changed);
 }
 tick.extend(p("_extLoaded"));tick.push(op(o::NOT));let loaded=test(&mut tick);
 tick.extend([I::PushByte(0),I::PushRegister(1),I::DictRef{kind:D::CallMethodPop,index:33}]);end(&mut tick,loaded);end(&mut tick,slow);
 set(v,"_extTick",vec![I::DefineFunction2{name:String::new(),params:vec![],register_count:2,flags:1,body:ActionStream{instructions:tick}}]);
}
fn main()->Result<(),Box<dyn std::error::Error>>{
 let args:Vec<_>=env::args().collect();let base=&args[1];let output=&args[2];let capacity:usize=args[3].parse()?;
 let buckets:u32=args.get(5).map_or(Ok(128),|value|value.parse())?;
 if !(1..=999).contains(&buckets) || capacity<64{return Err("invalid bucket dimensions".into());}
 let lib:serde_json::Value=serde_json::from_slice(&fs::read(&args[4])?)?;
 let live=lib["runtime_only"]==true;
 let ids:Vec<u32>=lib["players"].as_object().ok_or("players")?.values().filter(|p|p["context_team_id"]==144 && p["records"].as_array().is_some_and(|a|!a.is_empty())).map(|p|p["player_id"].as_u64().unwrap() as u32).collect();
 let mut m=AptFile::read(&fs::read(format!("{base}.apt"))?,&fs::read(format!("{base}.const"))?)?;let mut hits=0;
 for control in &mut m.movie.frames[0].controls{let Control::InitAction{actions,..}=control else{continue};let Some(I::DefineDictionary(d))=actions.instructions.first() else{continue};if d.get(34)!=Some(&Value::String("SquadRanking::InitData()".into())){continue;}
 for i in 1..actions.instructions.len(){let method=match &actions.instructions[i-1]{I::DictRef{kind:D::PushByte|D::PushWord,index}=>*index,_=>continue};let I::DefineFunction2{body,..}=&mut actions.instructions[i] else{continue};
 if method==211{if body.instructions.first()!=Some(&I::PushRegister(3)){return Err("B6 renderer".into());}patch_render(body,capacity,buckets,&ids,live);hits+=1;}
 if method==16{if body.instructions.len()!=230{return Err("B6 init".into());}init(body,live);hits+=1;}
 }}if hits!=2{return Err("methods not unique".into());}
 // Native EnterFrame event on a dedicated empty child; no menu automation.
 let poll_id=m.movie.characters.len() as i32;m.movie.characters.push(CharacterSlot::Character(Character::Sprite(apt::Sprite{frames:vec![apt::Frame::default()]})));
 let actions=ActionStream{instructions:vec![I::PushByte(0),lit("this"),op(o::GET_VARIABLE),lit("_parent"),op(o::GET_MEMBER),lit("_extTick"),op(o::CALL_METHOD),op(o::POP),I::End]};
 let CharacterSlot::Character(Character::Sprite(s))=&mut m.movie.characters[56] else{return Err("screen".into());};
 s.frames[0].controls.push(Control::PlaceObject(apt::PlaceObject{depth:95,character_id:Some(poll_id),name:Some("_extClock".into()),clip_actions:Some(vec![apt::EventAction{triggers:2,key_code:0,actions}]),..Default::default()}));
 let (apt,constants)=m.write(&apt::write::WriteOptions::from_header(&m.header))?;let check=AptFile::read(&apt,&constants)?;if check!=m{
 eprintln!("header={} frames={} chars={}/{}",check.header==m.header,check.movie.frames==m.movie.frames,check.movie.characters.len(),m.movie.characters.len());
 for (i,(a,b)) in check.movie.characters.iter().zip(m.movie.characters.iter()).enumerate(){if a!=b{eprintln!("different char {}",i);if let (CharacterSlot::Character(Character::Sprite(a)),CharacterSlot::Character(Character::Sprite(b)))=(a,b){eprintln!("READ {:?} WRITE {:?}",a.frames[0].controls.last(),b.frames[0].controls.last());}}}
 for (i,(a,b)) in check.movie.frames[0].controls.iter().zip(m.movie.frames[0].controls.iter()).enumerate(){if a!=b{eprintln!("different root control {}",i);}}
 return Err("semantic roundtrip".into());}
 fs::write(format!("{output}.apt"),apt)?;fs::write(format!("{output}.const"),constants)?;println!("External cache renderer preserved {} embedded player histories",ids.len());Ok(())
}
