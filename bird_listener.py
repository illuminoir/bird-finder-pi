import time
import os
import tempfile
import sounddevice as sd
import soundfile as sf

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

from db import init_db, insert_detection

from dotenv import load_dotenv


# ----------------------------
# CONFIG
# ----------------------------

LATITUDE = 52.5        # <-- change to your location
LONGITUDE = 13.4       # <-- change to your location
CHUNK_DURATION = 5          # seconds
SAMPLE_RATE = 44100
MIN_CONFIDENCE = 0.5
SPECIES_COOLDOWN = 300      # seconds per species (5 mins)

# ----------------------------
# INIT
# ----------------------------

print("🐦 Starting Bird Listener...")
init_db()

load_dotenv()

analyzer = Analyzer()

last_species_seen = {}

print("Listening...\n")

# ----------------------------
# MAIN LOOP
# ----------------------------

while True:
    try:
        print("🎤 Recording...")
        audio = sd.rec(
            int(CHUNK_DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32"
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio, SAMPLE_RATE)
            temp_path = tmp.name

        recording = Recording(
            analyzer,
            temp_path,
            lat=LATITUDE,
            lon=LONGITUDE,
            min_conf=MIN_CONFIDENCE
        )

        recording.analyze()
        os.remove(temp_path)

        if recording.detections:
            now = time.time()

            for detection in recording.detections:
                species = detection["common_name"]
                confidence = detection["confidence"]

                last_seen = last_species_seen.get(species, 0)

                if now - last_seen > SPECIES_COOLDOWN:
                    insert_detection(species, confidence)
                    last_species_seen[species] = now
                    print(f"🐦 Stored: {species} ({round(confidence * 100, 1)}%)")
                else:
                    print(f"Skipped {species} (cooldown active)")
        else:
            print("No birds detected.")

        time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping listener.")
        break

    except Exception as e:
        print("Error:", e)
        time.sleep(2)