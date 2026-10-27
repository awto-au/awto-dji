#!/usr/bin/env python3
"""Inspect original Intel WiMAX SBCF boot-signature data, without modifying image.
Extracts header fields, records, RSA verification candidates and hash candidates.
Only emits metadata and short hex prefixes, not proprietary firmware bytes.
"""
import collections,hashlib,json,struct,sys
from pathlib import Path
DIGESTS={"md5":(hashlib.md5,"3020300c06082a864886f70d020505000410"),"sha1":(hashlib.sha1,"3021300906052b0e03021a05000414"),"sha224":(hashlib.sha224,"302d300d06096086480165030402040500041c"),"sha256":(hashlib.sha256,"3031300d060960864801650304020105000420"),"sha384":(hashlib.sha384,"3041300d060960864801650304020205000430"),"sha512":(hashlib.sha512,"3051300d060960864801650304020305000440")}
def sha(x):return hashlib.sha256(x).hexdigest()
def analyze(path):
 b=path.read_bytes()
 h=struct.unpack_from("<10I",b)
 typ,hlen,version,mid,vendor,date,total,ks,ms,es=h
 assert typ==6 and vendor==0x8086 and hlen*4>=128 and total*4<=len(b)
 base=128; kb=b[base:base+ks*4]; xb=b[base+ks*4:base+(ks+es)*4]; sb=b[base+(ks+es)*4:base+(ks+es+ms)*4]
 assert base+len(kb)+len(xb)+len(sb)<=hlen*4
 secs=[]; pos=hlen*4; jump=None
 while pos+16<=total*4:
  opw,addr,n,ck=struct.unpack_from("<4I",b,pos)
  if (opw & 0xffff0000)!=0xcbbc0000:raise ValueError(f"boot header @ {pos:x} unknown {opw:x}")
  if (opw & 15) in (3,8):
   jump={"offset":hex(pos),"opcode":opw&15,"address":hex(addr),"size":n,"checksum":hex(ck),"last_header_hex":b[pos:pos+16].hex(),"trailing_bytes_in_primary":total*4-(pos+16)}
   break
  end=pos+16+n
  assert end<=total*4
  secs.append((pos,addr,n,b[pos+16:end],b[pos:(end+3)&~3]))
  pos=(end+3)&~3
 # verify unsigned raw RSA public keys using both byte orders
 results=[]
 for endian in ["big","little"]:
  modulus=int.from_bytes(kb,endian); keybits=modulus.bit_length()
  for expend in ["big","little"]:
   exponent=int.from_bytes(xb,expend)
   if exponent<3 or exponent>2**24 or exponent%2==0:continue
   for signend in ["big","little"]:
    signature=int.from_bytes(sb,signend)
    if signature>=modulus:continue
    dec=pow(signature,exponent,modulus).to_bytes(len(kb),"big")
    idx=dec.find(b"\x00",2)
    parsed={"modulus_endian":endian,"exponent_endian":expend,"signature_endian":signend,"exponent":exponent,"modulus_bits":keybits,"rsa_recovered_header_48":dec[:48].hex(),"pkcs1_padding":dec.startswith(b"\x00\x01") and idx>=10,"rsa_trailer_80":dec[-80:].hex()}
    if dec.startswith(b"\x00\x01") and idx>0:
      tail=dec[idx+1:]
      parsed["digestinfo_hex"]=tail.hex()
      matches=[]
      buffers={"whole_file":b,"primary_image":b[:total*4],"write_data_concat":b"".join(s[3] for s in secs),
               "write_commands_concat":b"".join(s[4] for s in secs),"primary_after_header":b[hlen*4:total*4],
               "primary_after_header_no_jump":b[hlen*4:pos],
               "first_header":b[:128],"header_excl_signature":b[:base+(ks+es)*4]}
      for label,raw in buffers.items():
       for dig,(fn,prefix) in DIGESTS.items():
        if bytes.fromhex(prefix)+fn(raw).digest()==tail:
         matches.append({"message":label,"hash":dig})
      parsed["digest_matches"]=matches
    results.append(parsed)
 trailing=[]
 off=total*4
 while off+128<=len(b):
  hh=struct.unpack_from("<10I",b,off)
  if hh[0]!=6 or hh[4]!=0x8086 or hh[1]<32:break
  trailing.append({"offset":hex(off),"module_id":hex(hh[3]),"header_bytes":hh[1]*4,"date":hex(hh[5]),"key_size":hh[7]*4,"modulus_size":hh[8]*4,"exponent_size":hh[9]*4,"key_sha256":sha(b[off+128:off+128+hh[7]*4])})
  off+=hh[1]*4
 return {"name":path.name,"image_len":len(b),"sha256":sha(b),"first_header":{
 "module_type":typ,"header_len":hlen*4,"header_version":hex(version),"module_id":hex(mid),"date":hex(date),
 "module_vendor":hex(vendor),"declared_primary_bytes":total*4,"key_bytes":len(kb),"exp_bytes":len(xb),
 "modulus_or_signature_bytes":len(sb),"key_first_24_hex":kb[:24].hex(),"exponent_hex":xb.hex(),
 "signature_first_24_hex":sb[:24].hex(),"pubkey_sha256":sha(kb),
 "signature_sha256":sha(sb),"header_extra_after_fields":hlen*4-(base+len(kb)+len(xb)+len(sb))},
 "jump":jump,"written_sections":len(secs),"trailing_headers":trailing,"rsa_candidates":results[:16],
 "warning":"RSA padding validity, not filename or lengths, is required to establish signed integrity. RSA alone does not establish device policy."}
if __name__=="__main__":
 print(json.dumps(analyze(Path(sys.argv[1])),indent=2))
