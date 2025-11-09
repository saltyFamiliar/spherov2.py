import time
from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.types import Color

print("Testing Starting...")
print("Connecting to Bolt...")
toy = scanner.find_BOLT()

if toy is not None:
    print("Connected.")
    with SpheroEduAPI(toy) as bolt:
        for heading in [0, 90, 180, 270]:
            bolt.roll(heading, 80, 0.75)
