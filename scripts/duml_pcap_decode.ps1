<#
Decode DUML frames (0x55 ...) out of a USBPcap/Wireshark capture of a DJI USB-serial
(CDC) port into a table: time, direction, device, sender/receiver, seq, type, cmd set/id, payload.

Needs Wireshark's tshark (>= 4: usbcom dissector). Offline: reads a .pcapng.
Frame layout used: 55 | len | ver | crc8 | sender | receiver | seq(2, LE) | type | set | id | payload | crc16
CRCs are not verified here.

Usage: pwsh scripts/duml_pcap_decode.ps1 captures/foo.pcapng [-Out captures/foo.decoded.txt]
#>
param(
    [Parameter(Mandatory)][string]$Pcap,
    [string]$Out,
    [string]$Tshark = 'C:\Program Files\Wireshark\tshark.exe'
)
$lines = & $Tshark -r $Pcap -Y 'usb.transfer_type==0x03 && usb.data_len>0' -T fields `
    -e frame.time_relative -e usb.src -e usb.dst -e usbcom.data.out_payload -e usbcom.data.in_payload -E separator=','

$rows = foreach ($l in $lines) {
    $f = $l -split ','
    $hex = (($f[3] + $f[4]) -replace ':', '')
    if (-not $hex) { continue }
    $host_out = $f[1] -eq 'host'
    $o = [ordered]@{ t = '{0:N3}' -f [double]$f[0]; dir = $(if ($host_out) { '>>' } else { '<<' }); dev = $(if ($host_out) { $f[2] } else { $f[1] }) }
    if ($hex.Length -ge 22 -and $hex.StartsWith('55')) {
        $b = 0..($hex.Length / 2 - 1) | ForEach-Object { [Convert]::ToByte($hex.Substring($_ * 2, 2), 16) }
        $o.snd = $b[4].ToString('x2'); $o.rcv = $b[5].ToString('x2')
        $o.seq = '{0:x2}{1:x2}' -f $b[7], $b[6]
        $o.type = $b[8].ToString('x2'); $o.set = $b[9].ToString('x2'); $o.id = $b[10].ToString('x2')
        $pl = if ($b.Length -gt 13) { $b[11..($b.Length - 3)] } else { @() }
        $o.payload = ($pl | ForEach-Object { $_.ToString('x2') }) -join ''
        $ascii = -join ($pl | ForEach-Object { if ($_ -ge 32 -and $_ -lt 127) { [char]$_ } else { '.' } })
        if ($ascii -match '[ -~]{6,}') { $o.ascii = $ascii }
    } else { $o.payload = 'RAW ' + $hex.Substring(0, [Math]::Min(48, $hex.Length)) }
    [pscustomobject]$o
}
$text = $rows | Format-Table -AutoSize | Out-String -Width 400
if ($Out) { $text | Set-Content $Out -Encoding utf8; "wrote $Out ($($rows.Count) frames)" } else { $text }
