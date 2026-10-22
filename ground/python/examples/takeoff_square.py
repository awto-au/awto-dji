"""Fly a small square, then return home. Run the sim bridge first, or point it at the
real Android bridge.

    # terminal 1
    python -m awto_dji_ground.sim_bridge --listen udpin:0.0.0.0:14550
    # terminal 2
    python examples/takeoff_square.py udpout:127.0.0.1:14550
"""

import sys

from awto_dji_ground import Vehicle


def main(device: str) -> None:
    with Vehicle.connect(device) as v:
        print("waiting for bridge...")
        v.wait_ready()
        print("taking off")
        v.takeoff(blocking=True)
        for leg in range(4):
            print(f"leg {leg + 1}: forward 3 m")
            v.set_velocity(forward=2.0, duration=1.5)
            print("yaw 90 deg")
            v.set_velocity(yaw_rate_dps=45.0, duration=2.0)
        print("returning home")
        v.return_to_home(blocking=True)
        print("done")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "udpout:127.0.0.1:14550")
