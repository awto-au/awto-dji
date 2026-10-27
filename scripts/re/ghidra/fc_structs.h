// DumlFrame (size 12)
/fc/DumlFrame
pack(disabled)
Structure DumlFrame {
   0   byte   1   sof   "0x55"
   1   byte   1   len_lo   ""
   2   byte   1   ver_len_hi   "ver<<2 | len_hi"
   3   byte   1   hdr_crc8   ""
   4   byte   1   sender   "devtype<<? ; low5=type"
   5   byte   1   receiver   "low5=devtype, high3=index"
   6   ushort   2   seq   ""
   8   byte   1   cmd_type   "ack/enc flags (&0x60,&0x1f)"
   9   byte   1   cmd_set   ""
   10   byte   1   cmd_id   ""
   11   byte   1   payload0   ""
}
Length: 12 Alignment: 1


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
  +0x0b byte       payload0; 
};

// CtrlAgency (size 36)
/fc/CtrlAgency
pack(disabled)
Structure CtrlAgency {
   0   byte   1   active   "1 = a controller holds agency"
   3   byte   1   holder_id   "device type currently holding control"
   32   byte   1   granted   "grant latch"
}
Length: 36 Alignment: 1


struct CtrlAgency {  // 0x24 bytes
  +0x00 byte       active; // 1 = a controller holds agency
  +0x03 byte       holder_id; // device type currently holding control
  +0x20 byte       granted; // grant latch
};

// FlycExportParam[808] (size 48480)
FlycExportParam[808]

// FlycExportParam (size 60)
/fc/FlycExportParam
pack(disabled)
Structure FlycExportParam {
   0   pointer   4   nameptr   ""
   4   pointer   4   valptr   ""
   8   uint   4   valsize   ""
   12   uint   4   type_id   ""
   16   byte[36]   36   limits   ""
   52   uint   4   attribute   ""
   56   pointer   4   callback   ""
}
Length: 60 Alignment: 1


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
/fc/CtrlMode
pack(disabled)
Structure CtrlMode {
   0   byte   1   active_device   "winning control source code; ==2 => API/nav"
   1   byte   1   src_flags   "bit1=src1, bit2=API/nav eligible"
}
Length: 4 Alignment: 1


struct CtrlMode {  // 0x4 bytes
  +0x00 byte       active_device; // winning control source code; ==2 => API/nav
  +0x01 byte       src_flags; // bit1=src1, bit2=API/nav eligible
};

