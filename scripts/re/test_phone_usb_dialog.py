"""phone_usb_dialog: canned uiautomator XML, no phone."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phone_usb_dialog as d

def xml(checked, with_dialog=True):
    if not with_dialog:
        return '<hierarchy><node text="Home" class="android.widget.TextView" bounds="[0,0][10,10]"/></hierarchy>'
    return f'''<hierarchy>
<node text="Allow AWTO DJI to access DJI T600?" class="android.widget.TextView" bounds="[0,0][100,50]"/>
<node text="Use by default for this USB accessory" resource-id="android:id/alwaysUse" class="android.widget.CheckBox" checked="{checked}" bounds="[100,200][300,260]"/>
<node text="Cancel" resource-id="android:id/button2" class="android.widget.Button" bounds="[0,400][100,460]"/>
<node text="OK" resource-id="android:id/button1" class="android.widget.Button" bounds="[200,400][400,460]"/>
</hierarchy>'''

def test_parse_centres_from_bounds():
    r = d.parse_dialog(xml("false"))
    assert r == dict(checkbox=(200, 230), checked=False, ok=(300, 430))

def test_no_dialog():
    assert d.parse_dialog(xml("false", False)) is None
    assert d.accept("x", dump_fn=lambda: xml("false", False), tap_fn=lambda xy: None,
                    log=lambda m: None) == 1

def test_accept_ticks_then_ok():
    seq = iter([xml("false"), xml("true"), xml("true", False)])
    taps = []
    rc = d.accept("x", dump_fn=lambda: next(seq), tap_fn=taps.append, log=lambda m: None)
    assert rc == 0 and taps == [(200, 230), (300, 430)]

def test_already_checked_only_taps_ok():
    seq = iter([xml("true"), xml("true", False)])
    taps = []
    assert d.accept("x", dump_fn=lambda: next(seq), tap_fn=taps.append, log=lambda m: None) == 0
    assert taps == [(300, 430)]

def test_checkbox_never_ticks_exit_2():
    taps = []
    rc = d.accept("x", dump_fn=lambda: xml("false"), tap_fn=taps.append, log=lambda m: None)
    assert rc == 2 and len(taps) == d.TRIES

def test_controls_missing_exit_2():
    bad = '<hierarchy><node text="Allow X to access Y?" class="android.widget.TextView" bounds="[0,0][1,1]"/></hierarchy>'
    assert d.accept("x", dump_fn=lambda: bad, tap_fn=lambda xy: None, log=lambda m: None) == 2
