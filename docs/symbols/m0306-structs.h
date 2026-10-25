/* m0306 (P3 flight controller) struct layouts - reverse-engineered, Ghidra /fc category.
   Applied at: CtrlAgency@0x20023664, CtrlMode@0x200001d5, FlycExportParam[808]@0x080ab66c.
   DumlFrame = DUML wire header (payload at +0x0b). */

struct DumlFrame {  // 0xc bytes
  +0x00 byte       sof; // 0x55
  +0x01 byte       len_lo; 
  +0x02 byte       ver_len_hi; // ver<<2 | len_hi
  +0x03 byte       hdr_crc8; 
  +0x04 byte       sender; // devtype<<? ; low5=type
  +0x05 byte       receiver; // low5=devtype, high3=index
  +0x06 ushort     seq; 
  +0x08 byte       cmd_type; // ack/enc flags (&0x60,&0x1f)
  +0x09 byte       cmd_set; 
  +0x0a byte       cmd_id; 
--
struct CtrlAgency {  // 0x24 bytes
  +0x00 byte       active; // 1 = a controller holds agency
  +0x03 byte       holder_id; // device type currently holding control
  +0x20 byte       granted; // grant latch
};

// FlycExportParam[808] (size 48480)
FlycExportParam[808]

// FlycExportParam (size 60)
/fc/FlycExportParam
--
struct FlycExportParam {  // 0x3c bytes
  +0x00 pointer    nameptr; 
  +0x04 pointer    valptr; 
  +0x08 uint       valsize; 
  +0x0c uint       type_id; 
  +0x10 byte[36]   limits; 
  +0x34 uint       attribute; 
  +0x38 pointer    callback; 
};

// CtrlMode (size 4)
--
struct CtrlMode {  // 0x4 bytes
  +0x00 byte       active_device; // winning control source code; ==2 => API/nav
  +0x01 byte       src_flags; // bit1=src1, bit2=API/nav eligible
};

