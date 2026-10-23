<#
Decode CDC-ACM class control requests (baud / data format / DTR+RTS / break) from a USBPcap capture.

tshark does not dissect these for vendor "USB Serial Device" ports, so the 8-byte setup packet
and the 7-byte line-coding data are decoded here from the raw USBPcap URBs.
USBPcap pseudo-header: headerLen(2) at 0, transfer type at 22 (2=control), control stage at 27
(0=setup, 1=data, 2=status), setup bytes at headerLen..headerLen+7, data stage payload after headerLen.

Prints one line per request: time, bus.addr, request name, wValue, decoded value.
Requests: 0x20 SET_LINE_CODING, 0x21 GET_LINE_CODING, 0x22 SET_CONTROL_LINE_STATE, 0x23 SEND_BREAK.
Usage: pwsh scripts/cdc_ctrl_decode.ps1 captures/foo.pcapng
#>
param(
    [Parameter(Mandatory)][string]$Pcap,
    [string]$Tshark = 'C:\Program Files\Wireshark\tshark.exe'
)
$names = @{ 0x20 = 'SET_LINE_CODING'; 0x21 = 'GET_LINE_CODING'; 0x22 = 'SET_CONTROL_LINE_STATE'; 0x23 = 'SEND_BREAK' }
$json = & $Tshark -r $Pcap -Y 'usb.transfer_type==0x02' -T json -x 2>$null | ConvertFrom-Json
$lastReq = @{}
function LineCoding($t, $key, $kind, $d) {
    $rate = [BitConverter]::ToUInt32([byte[]]$d[0..3], 0)
    $stop = @('1', '1.5', '2')[$d[4]]; $par = @('N', 'O', 'E', 'M', 'S')[$d[5]]
    "{0}  {1}    {2} line coding: {3} baud, {4}{5}{6}" -f $t, $key, $kind, $rate, $d[6], $par, $stop
}
foreach ($p in $json) {
    $l = $p._source.layers
    $hex = $l.frame_raw[0] -replace '[^0-9a-fA-F]', ''   # frame_raw = [hex, offset, len, ...]
    $b = for ($i = 0; $i -lt $hex.Length; $i += 2) { [Convert]::ToByte($hex.Substring($i, 2), 16) }
    $hl = $b[0] + 256 * $b[1]
    $bus = [BitConverter]::ToUInt16($b, 17); $dev = [BitConverter]::ToUInt16($b, 19)
    $stage = $b[27]
    $t = '{0:N3}' -f [double]$l.frame.'frame.time_relative'
    $key = "$bus.$dev"
    if ($stage -eq 0) {
        $rt = $b[$hl]; $rq = $b[$hl + 1]
        if (($rt -band 0x60) -ne 0x20) { $lastReq.Remove($key); continue }   # class requests only
        $wv = $b[$hl + 2] + 256 * $b[$hl + 3]; $wl = $b[$hl + 6] + 256 * $b[$hl + 7]
        $lastReq[$key] = $rq
        $nm = if ($names[[int]$rq]) { $names[[int]$rq] } else { '0x{0:x2}' -f $rq }
        if ($rq -eq 0x22) {
            "{0}  {1}  {2}  wValue=0x{3:x4}  DTR={4} RTS={5}" -f $t, $key, $nm, $wv, ($wv -band 1), (($wv -shr 1) -band 1)
        } elseif ($rq -eq 0x23) {
            "{0}  {1}  {2}  duration={3} ms" -f $t, $key, $nm, $wv
        } else {
            "{0}  {1}  {2}  wLength={3}" -f $t, $key, $nm, $wl
        }
        # SET_LINE_CODING carries its 7 data bytes right after the setup packet
        if ($rq -eq 0x20 -and $b.Length -ge $hl + 8 + 7) { LineCoding $t $key 'set' $b[($hl + 8)..($hl + 14)] }
    } elseif ($stage -ge 1 -and $lastReq.ContainsKey($key) -and $lastReq[$key] -eq 0x21 -and $b.Length -ge $hl + 7) {
        # GET_LINE_CODING answer arrives in the data/complete stage
        LineCoding $t $key 'get' $b[$hl..($hl + 6)]
    }
}
