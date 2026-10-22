//
// AD9363SpiTap — a Renode SPI-slave peripheral that taps and logs every AD9361/AD9363
// SPI transaction issued by the emulated DJI Phantom 3 air MCU m0900 (STM32F103).
//
// Purpose (interoperability, see CLAUDE.md): the AD9363 RF config in m0900 is
// *runtime-computed*, not a static table, so the only way to read the exact OFDM channel
// parameters (centre frequency, channel bandwidth, sample rate, gains) is to run the
// firmware's bring-up and capture the SPI register writes it makes to the transceiver,
// then decode them against the public ADI UG-570 register map. This peripheral is that tap.
//
// It is NOT a functional AD9363 model. It records traffic and returns plausible readback
// values so the init sequence can proceed (ID/lock/cal-done registers are tunable from the
// monitor via SetReadDefault). No secret-key material is involved; this is structural RF
// parameter recovery of an owned device.
//
// License: MIT (matches the surrounding Renode peripheral sources this is loaded alongside).
//
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals;
using Antmicro.Renode.Peripherals.SPI;

namespace Antmicro.Renode.Peripherals.SPI
{
    // AD9361 and AD9363 share the SPI map and framing (ADI UG-570, "SPI Interface").
    // A transaction is: a 16-bit instruction word (MSB first), then N data bytes.
    //
    //   instruction word bits:
    //     D15      R/!W   (1 = read, 0 = write)  -- ADI: first byte 0x80 bit = read
    //     D14..D13 W1:W0  number of DATA bytes minus 1 (burst length, 1..4)
    //     D12..D0  A12..A0 start register address (the UG-570 map is < 0x400)
    //
    // The STM32 SPI controller drives CS from a software GPIO and never calls
    // FinishTransmission() on the slave, so we cannot rely on it to delimit transactions.
    // Instead we self-frame from the byte count encoded in the header (W1:W0). We also keep
    // a lossless flat log of every MOSI byte so the capture can be re-framed by hand in the
    // (rare) event a multi-byte burst uses a count encoding we did not expect.
    public class AD9363SpiTap : ISPIPeripheral
    {
        public AD9363SpiTap()
        {
            registers = new byte[AddressSpace];
            transactions = new List<Transaction>();
            rawMosi = new List<byte>();
            readDefaults = new Dictionary<int, byte>();
            currentData = new List<byte>();
            SetResetState();
        }

        public byte Transmit(byte data)
        {
            rawMosi.Add(data);
            byte reply = 0;

            if(byteIndex == 0)
            {
                headerHi = data;
                byteIndex = 1;
                return 0;
            }
            if(byteIndex == 1)
            {
                command = (headerHi << 8) | data;
                isWrite = (command & 0x8000) == 0;
                dataLen = ((command >> 13) & 0x3) + 1;
                address = command & 0x1FFF;        // keep the full 13-bit field; UG-570 uses < 0x400
                currentData.Clear();
                byteIndex = 2;
                return 0;
            }

            // Data phase. ADI bursts auto-decrement the address from the start address.
            var di = byteIndex - 2;
            var a = (address - di) & (AddressSpace - 1);
            if(isWrite)
            {
                registers[a] = data;
                currentData.Add(data);
            }
            else
            {
                reply = ReadRegister(a);
                currentData.Add(reply);
            }
            byteIndex++;

            if(byteIndex >= 2 + dataLen)
            {
                EmitTransaction();
                byteIndex = 0;
            }
            return reply;
        }

        public void FinishTransmission()
        {
            // Honoured if a controller ever asserts a transaction boundary (STM32SPI does
            // not). If we are mid-frame, flush what we have so nothing is silently dropped.
            if(byteIndex >= 2)
            {
                EmitTransaction();
            }
            byteIndex = 0;
        }

        public void Reset()
        {
            byteIndex = 0;
            transactions.Clear();
            rawMosi.Clear();
            SetResetState();
        }

        // --- monitor-facing helpers -------------------------------------------------------

        // Persist the decoded transaction list, e.g.:  ad9363_spi1 SaveCapture @spi1.txt
        public void SaveCapture(string path)
        {
            var sb = new StringBuilder();
            sb.AppendLine("# AD9363/AD9361 SPI capture - " + transactions.Count + " transaction(s)");
            sb.AppendLine("# dir  addr   data...            ; UG-570 note");
            foreach(var t in transactions)
            {
                sb.AppendLine(Format(t));
            }
            File.WriteAllText(path, sb.ToString());
            this.Log(LogLevel.Info, "SaveCapture: wrote {0} transaction(s) to {1}", transactions.Count, path);
        }

        // Persist the lossless flat MOSI byte stream (hex), as a re-framing fallback.
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

        // Preload a readback value for an ID/status register the firmware polls before it
        // will proceed (product id, PLL lock, calibration-done bits). Tune during the live
        // run if the bring-up spins, e.g.:  ad9363_spi1 SetReadDefault 0x037 0x0A
        public void SetReadDefault(int addr, byte value)
        {
            var a = addr & (AddressSpace - 1);
            readDefaults[a] = value;
            registers[a] = value;
        }

        public int TransactionCount
        {
            get { return transactions.Count; }
        }

        // --- internals --------------------------------------------------------------------

        private void EmitTransaction()
        {
            var t = new Transaction
            {
                Write = isWrite,
                Address = address,
                Data = currentData.ToArray()
            };
            transactions.Add(t);
            this.Log(LogLevel.Info, "{0}", Format(t));
        }

        private byte ReadRegister(int a)
        {
            byte v;
            if(readDefaults.TryGetValue(a, out v))
            {
                return v;
            }
            return registers[a];
        }

        private void SetResetState()
        {
            Array.Clear(registers, 0, registers.Length);
            // UG-570 product-id register. AD9361 reports 0x0A; the AD9363 revision differs,
            // so confirm/tune this at run time. Seeded so a presence check does not stall.
            registers[0x037] = 0x0A;
            foreach(var kv in readDefaults)
            {
                registers[kv.Key] = kv.Value;
            }
        }

        private string Format(Transaction t)
        {
            var sb = new StringBuilder();
            sb.Append(t.Write ? "W " : "R ");
            sb.AppendFormat("0x{0:X3} ", t.Address);
            sb.Append("[");
            for(var i = 0; i < t.Data.Length; i++)
            {
                if(i > 0)
                {
                    sb.Append(' ');
                }
                sb.AppendFormat("0x{0:X2}", t.Data[i]);
            }
            sb.Append("]");
            var note = RegisterNote(t.Address);
            if(note != null)
            {
                sb.Append("  ; ");
                sb.Append(note);
            }
            return sb.ToString();
        }

        // Only registers we are confident about from UG-570 are annotated. The full numeric
        // decode (BBPLL -> sample rate, RFPLL -> centre freq, Rx/Tx BW, gains) is done at
        // decode time against UG-570 in docs/phy-params.md. Do not over-label (honesty rule).
        private static string RegisterNote(int a)
        {
            switch(a)
            {
            case 0x000: return "SPI config / soft reset";
            case 0x001: return "multichip sync & reset";
            case 0x002: return "TX enable & filter ctrl";
            case 0x003: return "RX enable & filter ctrl";
            case 0x017: return "ENSM / state";
            case 0x037: return "product id";
            default: return null;
            }
        }

        private struct Transaction
        {
            public bool Write;
            public int Address;
            public byte[] Data;
        }

        private int byteIndex;
        private int headerHi;
        private int command;
        private bool isWrite;
        private int dataLen;
        private int address;

        private readonly List<byte> currentData;
        private readonly byte[] registers;
        private readonly List<Transaction> transactions;
        private readonly List<byte> rawMosi;
        private readonly Dictionary<int, byte> readDefaults;

        private const int AddressSpace = 0x400;
    }
}
