//
// AD9363SpiTap — a Renode SPI-slave peripheral that taps/decodes the FPGA-bridged SPI the
// DJI Phantom 3 air MCU m0900 (STM32F103) uses to reach the AD9363 transceiver, and returns
// plausible status readbacks so the firmware's runtime radio bring-up proceeds far enough to
// emit its AD9363 register programming.
//
// Protocol (recovered from m0900, scripts/re/m0900_trace.py; awto-au/awto-dji#2):
//   The AD9363 is NOT on the MCU SPI directly — it sits behind a Lightbridge FPGA that
//   exposes a 3-byte SPI command protocol on SPI2 (0x40003800):
//     [0x0E, reg, val]        -> write FPGA register `reg` = `val`     (spi_fpga_raw_write)
//     [0x0F, reg, 0xFF]       -> read  FPGA register `reg` (result on the 3rd/dummy byte)
//   AD9363 register access is tunnelled through the FPGA: the driver first writes FPGA
//   reg 0x01 = 0x01 (passthrough-arm, i.e. a [0x0E,0x01,0x01] unit), then sends a 3-byte
//   payload that is NOT an 0x0E/0x0F unit:
//     [0x80|addrHi, addrLo, val]   -> AD9363 WRITE reg=((b0&0x7F)<<8)|b1, val=b2
//     [addrHi,      addrLo, 0xFF]  -> AD9363 READ  reg=((b0&0x7F)<<8)|b1 (result on dummy)
//   (ad936x_reg_sync_write/read @0x0800cebe/0x0800cf00). Since FPGA command bytes are only
//   ever 0x0E/0x0F and an AD9363 write byte0 is always >=0x80, 3-byte units are classified
//   unambiguously: 0x0E/0x0F => FPGA op; byte0>=0x80 => AD9363 write; else => AD9363 read.
//
// The STM32 SPI controller drives chip-select from a GPIO and never calls
// FinishTransmission(), so there are no transaction delimiters on the wire — we self-frame
// in fixed 3-byte units (every op in this protocol is 3 bytes) and also keep a lossless flat
// MOSI log so framing can be re-checked offline (scripts/re/decode_ad9363.py).
//
// Readbacks: FPGA status registers the bring-up polls (e.g. PLL-lock) must report "ready" or
// the firmware bails before programming the AD9363. Seed them with SetFpgaReadDefault; AD9363
// id/lock/cal regs with SetReadDefault. This is NOT a functional radio model — it records
// traffic and returns just enough status to let the init run. No secret-key material; this is
// structural RF-parameter recovery of an owned device (see CLAUDE.md).
//
// License: MIT (matches the surrounding Renode peripheral sources this is loaded alongside).
//
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals;

namespace Antmicro.Renode.Peripherals.SPI
{
    public class AD9363SpiTap : ISPIPeripheral
    {
        public AD9363SpiTap()
        {
            ad9363 = new byte[Ad9363Space];
            fpga = new byte[FpgaSpace];
            transactions = new List<Transaction>();
            rawMosi = new List<byte>();
            adReadDefaults = new Dictionary<int, byte>();
            fpgaReadDefaults = new Dictionary<int, byte>();
            unit = new byte[3];
            SetResetState();
        }

        public byte Transmit(byte data)
        {
            rawMosi.Add(data);

            // Resync: a unit begins only with an FPGA command byte (0x0E/0x0F) or, right after
            // a passthrough-arm ([0x0E,0x01,0x01]), with an AD9363 payload (any first byte).
            // Anything else at idle (e.g. a stray SPI flush byte seen at stream start) is
            // dropped so 3-byte framing stays aligned.
            if(unitIdx == 0 && !(data == FpgaWriteCmd || data == FpgaReadCmd || expectPayload))
            {
                return 0;
            }

            unit[unitIdx] = data;
            unitIdx++;
            if(unitIdx < 3)
            {
                // On the 3rd byte of a read we must return the modelled value; bytes 1-2 are 0.
                return 0;
            }

            unitIdx = 0;
            return ProcessUnit(unit[0], unit[1], unit[2]);
        }

        public void FinishTransmission()
        {
            // No CS delimiting from the STM32 controller; if a partial unit is pending just
            // drop it (keeps framing aligned for the next transfer). Raw log is unaffected.
            unitIdx = 0;
            expectPayload = false;
        }

        public void Reset()
        {
            unitIdx = 0;
            expectPayload = false;
            transactions.Clear();
            rawMosi.Clear();
            SetResetState();
        }

        // --- monitor-facing helpers -------------------------------------------------------

        public void SaveCapture(string path)
        {
            var sb = new StringBuilder();
            sb.AppendLine("# m0900 FPGA-bridged SPI capture - " + transactions.Count
                          + " op(s), " + Ad9363Count + " AD9363 register access(es)");
            sb.AppendLine("# kind         addr   data  ; note");
            foreach(var t in transactions)
            {
                sb.AppendLine(Format(t));
            }
            File.WriteAllText(path, sb.ToString());
            this.Log(LogLevel.Info, "SaveCapture: wrote {0} op(s) ({1} AD9363) to {2}",
                     transactions.Count, Ad9363Count, path);
        }

        public void SaveRaw(string path)
        {
            var sb = new StringBuilder();
            for(var i = 0; i < rawMosi.Count; i++)
            {
                sb.AppendFormat("{0:X2}", rawMosi[i]);
                sb.Append((i % 16 == 15) ? '\n' : ' ');
            }
            File.WriteAllText(path, sb.ToString());
            this.Log(LogLevel.Info, "SaveRaw: wrote {0} MOSI byte(s) to {1}", rawMosi.Count, path);
        }

        // Seed an AD9363 register readback (id/PLL-lock/cal-done), e.g. 0x037 product id.
        public void SetReadDefault(int addr, byte value)
        {
            var a = addr & (Ad9363Space - 1);
            adReadDefaults[a] = value;
            ad9363[a] = value;
        }

        // Seed an FPGA status register readback the bring-up polls (e.g. 0xE9 PLL-lock).
        public void SetFpgaReadDefault(int reg, byte value)
        {
            var r = reg & (FpgaSpace - 1);
            fpgaReadDefaults[r] = value;
            fpga[r] = value;
        }

        // Total decoded ops (FPGA + AD9363) — lets the platform tell which SPI is the bus.
        public int TransactionCount
        {
            get { return transactions.Count; }
        }

        // AD9363 register accesses only — the signal we actually want.
        public int Ad9363Count
        {
            get
            {
                var n = 0;
                foreach(var t in transactions)
                {
                    if(t.Kind == Kind.Ad9363Write || t.Kind == Kind.Ad9363Read)
                    {
                        n++;
                    }
                }
                return n;
            }
        }

        // --- internals --------------------------------------------------------------------

        private byte ProcessUnit(byte b0, byte b1, byte b2)
        {
            byte reply = 0;
            if(b0 == FpgaWriteCmd && !expectPayload)
            {
                fpga[b1] = b2;
                Record(Kind.FpgaWrite, b1, b2);
                // [0x0E,0x01,0x01] arms an AD9363 passthrough: the next unit is its payload.
                expectPayload = (b1 == 0x01 && b2 == 0x01);
            }
            else if(b0 == FpgaReadCmd && !expectPayload)
            {
                reply = FpgaRead(b1);
                Record(Kind.FpgaRead, b1, reply);
            }
            else if((b0 & 0x80) != 0)
            {
                expectPayload = false;
                var addr = ((b0 & 0x7F) << 8) | b1;
                ad9363[addr & (Ad9363Space - 1)] = b2;
                Record(Kind.Ad9363Write, addr, b2);
            }
            else
            {
                expectPayload = false;
                var addr = ((b0 & 0x7F) << 8) | b1;
                reply = Ad9363Read(addr);
                Record(Kind.Ad9363Read, addr, reply);
            }
            return reply;
        }

        private void Record(Kind kind, int addr, int data)
        {
            var t = new Transaction { Kind = kind, Address = addr, Data = (byte)data };
            transactions.Add(t);
            // AD9363 accesses are the interesting ones; log them at Info, FPGA ops at Debug.
            var level = (kind == Kind.Ad9363Write || kind == Kind.Ad9363Read)
                ? LogLevel.Info : LogLevel.Debug;
            this.Log(level, "{0}", Format(t));
        }

        private byte Ad9363Read(int addr)
        {
            byte v;
            var a = addr & (Ad9363Space - 1);
            if(adReadDefaults.TryGetValue(a, out v))
            {
                return v;
            }
            return ad9363[a];
        }

        private byte FpgaRead(int reg)
        {
            byte v;
            var r = reg & (FpgaSpace - 1);
            if(fpgaReadDefaults.TryGetValue(r, out v))
            {
                return v;
            }
            return fpga[r];
        }

        private void SetResetState()
        {
            Array.Clear(ad9363, 0, ad9363.Length);
            Array.Clear(fpga, 0, fpga.Length);
            // AD9361/3 product-id (UG-570 reg 0x037). AD9361 reports 0x0A; AD9363 differs —
            // confirm/tune at run time. Seeded so a presence check does not stall.
            ad9363[0x037] = 0x0A;
            // FPGA PLL-lock bit the per-channel tune (tcx_config_update1 @0x0800f0bc) polls on
            // FPGA reg 0xE9: it requires bit1 set or it skips the AD9363 re-tune.
            fpga[0xE9] = 0x02;
            foreach(var kv in adReadDefaults)
            {
                ad9363[kv.Key] = kv.Value;
            }
            foreach(var kv in fpgaReadDefaults)
            {
                fpga[kv.Key] = kv.Value;
            }
        }

        private string Format(Transaction t)
        {
            var sb = new StringBuilder();
            switch(t.Kind)
            {
            case Kind.FpgaWrite:   sb.Append("Wfpga  "); break;
            case Kind.FpgaRead:    sb.Append("Rfpga  "); break;
            case Kind.Ad9363Write: sb.Append("W ad9363 "); break;
            case Kind.Ad9363Read:  sb.Append("R ad9363 "); break;
            }
            sb.AppendFormat("0x{0:X3} ", t.Address);
            sb.AppendFormat("0x{0:X2}", t.Data);
            if(t.Kind == Kind.Ad9363Write || t.Kind == Kind.Ad9363Read)
            {
                var note = RegisterNote(t.Address);
                if(note != null)
                {
                    sb.Append("  ; ");
                    sb.Append(note);
                }
            }
            return sb.ToString();
        }

        // Only registers we are confident about from UG-570 are annotated; the full numeric
        // decode (BBPLL->sample rate, RFPLL->centre freq, Rx/Tx BW, gains) is done offline
        // against UG-570 in scripts/re/decode_ad9363.py / docs/phy-params.md.
        private static string RegisterNote(int a)
        {
            switch(a)
            {
            case 0x000: return "SPI config / soft reset";
            case 0x017: return "ENSM / state";
            case 0x037: return "product id";
            default: return null;
            }
        }

        private enum Kind { FpgaWrite, FpgaRead, Ad9363Write, Ad9363Read }

        private struct Transaction
        {
            public Kind Kind;
            public int Address;
            public byte Data;
        }

        private int unitIdx;
        private bool expectPayload;
        private readonly byte[] unit;
        private readonly byte[] ad9363;
        private readonly byte[] fpga;
        private readonly List<Transaction> transactions;
        private readonly List<byte> rawMosi;
        private readonly Dictionary<int, byte> adReadDefaults;
        private readonly Dictionary<int, byte> fpgaReadDefaults;

        private const byte FpgaWriteCmd = 0x0E;
        private const byte FpgaReadCmd = 0x0F;
        private const int Ad9363Space = 0x400;
        private const int FpgaSpace = 0x100;
    }
}
