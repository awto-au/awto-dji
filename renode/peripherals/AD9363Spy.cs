//
// Capture-only SPI slave standing in for the AD9363 on m0900.
//
// Logs each SPI transaction (bytes between chip-select assert/deassert) via Renode's own
// logger (redirect with the monitor's `logFile`, see ../m0900_boot.resc), so the MCU's real
// config sequence can be decoded offline against the ADI UG-570 register map. Deliberately
// does not decode register semantics here — see docs/fpga-emulation-plan.md step 3 and
// renode/README.md: that mapping is unverified, so it stays out of the capture tool and
// gets done as a separate, checkable step.
//
using System.Collections.Generic;

using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.SPI;

// Namespace must start with "Antmicro.Renode" - TypeManager.IsInterestingType only
// registers ad-hoc-compiled types under that prefix (or NetMQ) for .repl resolution.
namespace Antmicro.Renode.Peripherals.AwtoDji
{
    public class AD9363Spy : ISPIPeripheral
    {
        public AD9363Spy()
        {
            frame = new List<byte>();
        }

        public byte Transmit(byte data)
        {
            frame.Add(data);
            // AD9361/63 datasheet framing is unverified here (needs-tooling, see header);
            // we only echo back 0x00 since the real readback value isn't modeled.
            return 0;
        }

        public void FinishTransmission()
        {
            if(frame.Count == 0)
            {
                return;
            }
            var bytes = string.Join(" ", frame.ConvertAll(b => b.ToString("X2")));
            var rw = (frame[0] & 0x80) != 0 ? "W" : "R";
            this.Log(LogLevel.Info, "AD9363Spy transaction: {0} {1}", rw, bytes);
            frame.Clear();
        }

        public void Reset()
        {
            frame.Clear();
        }

        private readonly List<byte> frame;
    }
}
