from array import array
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET
from forge import RATE, make_score, piano_roll, synthesize, write_wav


def decode(pcm):
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


class ForgeTests(unittest.TestCase):
    def test_same_seed_reproduces_score_and_pcm(self):
        a, b = make_score(7, bars=1), make_score(7, bars=1)
        self.assertEqual(a, b)
        self.assertEqual(synthesize(a)[0], synthesize(b)[0])

    def test_seed_changes_melody(self):
        a, b = make_score(7, bars=1), make_score(8, bars=1)
        self.assertNotEqual([e["midi"] for e in a["events"] if e["voice"] == "lead"],
                            [e["midi"] for e in b["events"] if e["voice"] == "lead"])

    def test_duration_and_pcm_length(self):
        pcm, info = synthesize(make_score(bpm=120, bars=1))
        self.assertEqual(info["frames"], RATE * 2)
        self.assertEqual(len(pcm), RATE * 2 * 2)

    def test_tempo_changes_duration(self):
        _, slow = synthesize(make_score(bpm=60, bars=1))
        _, fast = synthesize(make_score(bpm=120, bars=1))
        self.assertEqual(slow["frames"], fast["frames"] * 2)

    def test_peak_has_headroom_and_nonzero_audio(self):
        pcm, info = synthesize(make_score(bars=1))
        samples = decode(pcm)
        self.assertEqual(max(abs(s) for s in samples), info["peak_pcm"])
        self.assertLess(info["peak_pcm"], 32767)
        self.assertGreater(sum(s*s for s in samples), 0)

    def test_loop_endpoints_are_zero(self):
        samples = decode(synthesize(make_score(bars=1))[0])
        self.assertEqual((samples[0], samples[-1]), (0, 0))

    def test_real_wave_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "loop.wav"
            pcm, info = synthesize(make_score(bars=1))
            write_wav(path, pcm)
            with wave.open(str(path), "rb") as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, RATE))
                self.assertEqual(w.getnframes(), info["frames"])
                self.assertEqual(w.readframes(info["frames"]), pcm)

    def test_score_stays_inside_loop(self):
        score = make_score(bars=8)
        self.assertEqual(len(score["events"]), 8*24)
        self.assertTrue(all(0 <= e["beat"] < e["beat"]+e["duration"] <= score["beats"]
                            for e in score["events"]))

    def test_mode_and_root(self):
        major = make_score(mode="major", root=72, bars=1)
        allowed = {72+12+i for i in (0, 2, 4, 7, 9)}
        self.assertTrue(all(e["midi"] in allowed for e in major["events"] if e["voice"] == "lead"))

    def test_invalid_parameters(self):
        for kwargs in [{"bpm": 0}, {"bars": 9}, {"bars": True}, {"seed": -1},
                       {"root": 80}, {"mode": "unknown"}]:
            with self.assertRaises(ValueError):
                make_score(**kwargs)

    def test_piano_roll_valid_svg(self):
        svg = piano_roll(make_score(bars=1))
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(len(root.findall(".//{http://www.w3.org/2000/svg}rect")), 9)

    def test_cli_exports_audio_score_and_svg(self):
        script = Path(__file__).parent / "forge.py"
        with tempfile.TemporaryDirectory() as directory:
            wav, score, svg = [Path(directory)/name for name in ("loop.wav", "score.json", "roll.svg")]
            run = subprocess.run([sys.executable, str(script), "--bars", "1", "--out", str(wav),
                                  "--score", str(score), "--svg", str(svg)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(score.read_text())["bars"], 1)
            ET.parse(svg)
            with wave.open(str(wav)) as audio:
                self.assertEqual(audio.getnframes(), RATE*2)

    def test_cli_rejects_overlapping_outputs(self):
        script = Path(__file__).parent / "forge.py"
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "same.wav"
            run = subprocess.run([sys.executable, str(script), "--out", str(out),
                                  "--score", str(out)], capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
