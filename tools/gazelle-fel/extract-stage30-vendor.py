#!/usr/bin/env python3
"""Stage30 owner archive extractor: SHA-pinned raw ext4 -> TWO vendor ELFs.

Host-only; no mount, ADB, root, kernel writes or binary execution.
Never upload the extracted private .so files to a public repository.
"""
import argparse,hashlib,mmap,shutil,struct,sys,tempfile,zipfile
from pathlib import Path
ARCHIVE_SHA="63c0aacc8647def650751a17b1fdba7ae6a67fed5ce6de7c88ab834d13e41622"
IMAGE_SHA="8021a1ba7956f01fe705b90e0005c377c04570adbec0e2e4399962617ab5553a"
PINS={
 "libOmxVideo.so":"eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77",
 "libomx_framework_alt.so":"fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba",
}
def file_sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for part in iter(lambda:f.read(1<<20),b""):h.update(part)
 return h.hexdigest()

class Image:
 def __init__(self,fp):
  self.m=mmap.mmap(fp.fileno(),0,access=mmap.ACCESS_READ)
  self.sb=1024
  if self.u16(1080)!=0xef53:raise ValueError("not ext filesystem")
  self.block=1024<<self.u32(1048)
  self.ipg=self.u32(1064)
  self.isize=self.u16(1112)
  self.desc=self.u16(1278) or 32
  self.flags=self.u32(1120)
  self.descstart=2 if self.block==1024 else 1
  if (self.block,self.ipg,self.isize)!=(4096,30240,128):
   raise ValueError("unexpected pinned vendor filesystem layout")
 def u16(self,at):return struct.unpack_from("<H",self.m,at)[0]
 def u32(self,at):return struct.unpack_from("<I",self.m,at)[0]
 def inode(self,num):
  group,index=divmod(num-1,self.ipg)
  at=self.descstart*self.block+group*self.desc
  table=self.u32(at+8)
  if self.flags&0x80:table|=self.u32(at+40)<<32
  return table*self.block+index*self.isize
 def extents(self,record):
  if struct.unpack_from("<H",record)[0]!=0xf30a:raise ValueError("bad extents")
  n,limit,depth=struct.unpack_from("<HHH",record,2)
  if not 0<=n<=limit<=340 or not 0<=depth<=4:raise ValueError("bad extent count/depth")
  if not depth:
   return [(i,l&0x7fff,(h<<32)|lo) for i,l,h,lo in
           (struct.unpack_from("<IHHI",record,12+k*12) for k in range(n))]
  result=[]
  for k in range(n):
   logical,lo,hi,_=struct.unpack_from("<IIHH",record,12+k*12)
   physical=(hi<<32)|lo
   result+=self.extents(self.m[physical*self.block:(physical+1)*self.block])
  return result
 def load(self,num):
  base=self.inode(num);mode=self.u16(base);length=self.u32(base+4)
  if length>40_000_000 or not self.u32(base+32)&0x80000:
   raise ValueError("unexpected inode format/size")
  contents=bytearray(length)
  for logical,count,phys in self.extents(self.m[base+40:base+100]):
   at=logical*self.block
   width=min(count*self.block,max(0,length-at))
   if width:contents[at:at+width]=self.m[phys*self.block:phys*self.block+width]
  return mode,bytes(contents)
 def directory(self,num):
  mode,b=self.load(num)
  if mode&0xf000!=0x4000:raise ValueError("not directory")
  result=[]
  for page in range(0,len(b),self.block):
   cursor=page
   while cursor<min(page+self.block,len(b)):
    if cursor+8>len(b):break
    inode,rec,nlen,kind=struct.unpack_from("<IHBB",b,cursor)
    if rec<8 or cursor+rec>page+self.block:break
    if inode:result.append((inode,b[cursor+8:cursor+8+nlen].decode("utf8")))
    cursor+=rec
  return result
 def locate(self,path):
  node=2
  for segment in path.strip("/").split("/"):
   choices=[inode for inode,name in self.directory(node) if name==segment]
   if len(choices)!=1:raise ValueError("missing/ambiguous "+segment)
   node=choices[0]
  return node

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("original_zip",type=Path)
 p.add_argument("output_dir",type=Path)
 a=p.parse_args()
 archive=a.original_zip.expanduser().resolve()
 if file_sha(archive)!=ARCHIVE_SHA:raise ValueError("owner ZIP hash mismatch")
 with zipfile.ZipFile(archive) as z:
  inventory={x.filename:x for x in z.infolist()}
  if set(inventory)!={"vendor.img","odm.img","CONTENTS.json"}:
   raise ValueError("unexpected archive inventory")
  if inventory["vendor.img"].file_size!=251658240:
   raise ValueError("unexpected vendor image size")
  with tempfile.TemporaryDirectory(prefix="gazelle-fel-stage30-") as tmp:
   image=Path(tmp)/"vendor.img"
   with z.open("vendor.img") as source,image.open("wb") as output:
    shutil.copyfileobj(source,output)
   if file_sha(image)!=IMAGE_SHA:raise ValueError("image hash mismatch")
   with image.open("rb") as fp:
    ext=Image(fp)
    binaries={}
    for name,sha in PINS.items():
     mode,b=ext.load(ext.locate("/lib/"+name))
     if mode&0xf000!=0x8000 or hashlib.sha256(b).hexdigest()!=sha:
      raise ValueError("private ELF hash mismatch "+name)
     binaries[name]=b
   out=a.output_dir.expanduser().resolve()
   out.mkdir(parents=True,exist_ok=True)
   for name,blob in binaries.items():
    (out/name).write_bytes(blob)
    print("GAZELLE_STAGE30_EXTRACT_PIN_PASS",name)
 print("GAZELLE_FEL_STAGE30_ORIGINAL_LIBRARIES_READY")

if __name__=="__main__":
 try:main()
 except (OSError,ValueError,zipfile.BadZipFile,struct.error) as err:
  print("GAZELLE_FEL_STAGE30_EXTRACT_FAIL",err,file=sys.stderr)
  sys.exit(1)
