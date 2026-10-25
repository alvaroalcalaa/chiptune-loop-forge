"""Seeded procedural chiptune loops. Python 3.10+, standard library only."""
import argparse
from array import array
import json
import math
from pathlib import Path
import random
import sys
import wave

RATE = 22050
SCALES = {"minor": (0, 3, 5, 7, 10), "major": (0, 2, 4, 7, 9)}
PROGRESSIONS = {"minor": (0, 8, 3, 10), "major": (0, 9, 5, 7)}


def make_score(seed=42, bpm=120, bars=4, root=60, mode="minor"):
    for name, value, low, high in [("seed", seed, 0, 2**32-1),
                                    ("bpm", bpm, 60, 200), ("bars", bars, 1, 8),
                                    ("root", root, 48, 72)]:
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} debe ser un entero entre {low} y {high}")
    if mode not in SCALES:
        raise ValueError("mode debe ser minor o major")
    rng = random.Random(seed)
    motif = [rng.choice(SCALES[mode]) for _ in range(8)]
    events = []
    for bar in range(bars):
        chord = root + PROGRESSIONS[mode][bar % 4] - 12
        for step in range(8):
            pitch = root + 12 + (motif[step] if bar % 2 == 0
                                else rng.choice(SCALES[mode]))
            events.append({"voice": "lead", "beat": bar * 4 + step / 2,
                           "duration": .42, "midi": pitch})
            events.append({"voice": "hat", "beat": bar * 4 + step / 2,
                           "duration": .10, "midi": None})
        for beat in range(4):
            events.append({"voice": "bass", "beat": bar * 4 + beat,
                           "duration": .82, "midi": chord})
            events.append({"voice": "kick" if beat % 2 == 0 else "snare",
                           "beat": bar * 4 + beat, "duration": .28, "midi": None})
    return {"seed": seed, "bpm": bpm, "bars": bars, "root_midi": root, "mode": mode,
            "beats": bars * 4, "events": sorted(events, key=lambda e: (e["beat"], e["voice"]))}


def synthesize(score):
    seconds_per_beat = 60 / score["bpm"]
    count = round(score["beats"] * seconds_per_beat * RATE)
    mix = [0.0] * count
    noise = random.Random(score["seed"] ^ 0xA53C)
    for event in score["events"]:
        start = round(event["beat"] * seconds_per_beat * RATE)
        length = max(2, round(event["duration"] * seconds_per_beat * RATE))
        voice = event["voice"]
        frequency = 440 * 2 ** ((event["midi"] - 69) / 12) if event["midi"] is not None else 0
        for i in range(min(length, count-start)):
            t = i / RATE
            # Short attack and release, with exact zero at both event endpoints.
            envelope = min(1.0, i / max(1, RATE * .004),
                           (length-1-i) / max(1, RATE * .015))
            if voice == "lead":
                sample, gain = (1.0 if (frequency*t) % 1 < .25 else -1.0), .22
            elif voice == "bass":
                sample, gain = 1 - 4 * abs((frequency*t) % 1 - .5), .30
            elif voice == "kick":
                # Integral of a frequency sweep from 120 Hz towards 45 Hz.
                phase = 2 * math.pi * (45*t + 75*.025*(1-math.exp(-t/.025)))
                sample, gain = math.sin(phase) * math.exp(-t*18), .65
            elif voice == "snare":
                sample, gain = noise.uniform(-1, 1) * math.exp(-t*25), .32
            else:
                sample, gain = noise.uniform(-1, 1) * math.exp(-t*70), .12
            mix[start+i] += gain * envelope * sample
    fade = max(1, round(RATE*.005))
    for i in range(min(fade, count//2)):
        gain = i / fade
        mix[i] *= gain
        mix[-1-i] *= gain
    peak = max(abs(s) for s in mix) or 1
    samples = array("h", (round(s / peak * .9 * 32767) for s in mix))
    if sys.byteorder != "little":
        samples.byteswap()
    pcm = samples.tobytes()
    return pcm, {"sample_rate": RATE, "channels": 1, "bits": 16,
                 "frames": count, "seconds": count/RATE,
                 "peak_pcm": round(.9*32767)}


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(pcm)


def piano_roll(score):
    lead = [e for e in score["events"] if e["voice"] == "lead"]
    width, height = 900, 270
    left, top, usable = 42, 62, 820
    shapes = []
    for beat in range(score["beats"]+1):
        x = left + usable * beat / score["beats"]
        shapes.append(f'<path d="M{x} {top}v155" stroke="#2a3a54" stroke-width="1"/>')
    for event in lead:
        x = left + usable * event["beat"] / score["beats"]
        y = top + 140 - (event["midi"]-score["root_midi"]-12)*10
        w = usable * event["duration"] / score["beats"]
        shapes.append(f'<rect x="{x}" y="{y}" width="{w}" height="8" rx="2" fill="#70e1ca"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">'
            '<title>Melodía generada: piano roll</title><rect width="100%" height="100%" fill="#0d1425"/>'
            '<g font-family="system-ui,sans-serif"><text x="42" y="32" fill="#eef5ff" font-size="22">'
            f'Chiptune Loop Forge · semilla {score["seed"]} · {score["bpm"]} BPM</text>'
            + "".join(shapes) +
            '<text x="42" y="246" fill="#b3c1dc" font-size="14">'
            'Melodía: tiempo → / altura = tono MIDI · bajo y percusión no representados</text></g></svg>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bpm", type=int, default=120)
    parser.add_argument("--bars", type=int, default=4)
    parser.add_argument("--root", type=int, default=60, help="Nota raíz MIDI, 48–72")
    parser.add_argument("--mode", choices=tuple(SCALES), default="minor")
    parser.add_argument("--out", type=Path, default=Path("loop.wav"))
    parser.add_argument("--score", type=Path, help="Partitura de eventos JSON")
    parser.add_argument("--svg", type=Path, help="Piano roll de la melodía")
    args = parser.parse_args()
    paths = [p.resolve() for p in (args.out, args.score, args.svg) if p]
    if len(paths) != len(set(paths)):
        parser.error("Las salidas deben tener rutas distintas")
    if args.out.suffix.lower() != ".wav":
        parser.error("--out debe tener extensión .wav")
    try:
        score = make_score(args.seed, args.bpm, args.bars, args.root, args.mode)
        pcm, info = synthesize(score)
        write_wav(args.out, pcm)
        if args.score:
            args.score.write_text(json.dumps(score, indent=2) + "\n", encoding="utf-8")
        if args.svg:
            args.svg.write_text(piano_roll(score), encoding="utf-8")
        print(json.dumps({**info, "seed": args.seed, "output": str(args.out)}, indent=2))
    except (ValueError, OSError, wave.Error) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
