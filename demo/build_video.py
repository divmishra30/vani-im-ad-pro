"""Build the VANI demo video from demo-script.md: voices, dashboard screenshots, captions, MP4 and transcript.

    python demo/build_video.py              # Microsoft neural Indian voices (pip install edge-tts, needs internet)
    python demo/build_video.py --voice sarvam # Sarvam voices (needs a working SARVAM_API_KEY)
    python demo/build_video.py --voice sapi # offline Windows voices, for a quick preview of timing and visuals

Steps: parse the script → text-to-speech per line (cached in demo/out/tts) → run the dashboard on a throwaway
database and screenshot it → replay the three calls' tools and transcripts into that database → screenshot the
"after" pages → draw one 1920x1080 frame per line → ffmpeg each frame with its audio → concatenate.
Outputs in demo/out: vani-demo.mp4, vani-demo.srt, transcript.md. Your real data/vani.db is never touched.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "out"
DEMO_DB = OUT / "demo.db"
os.environ["VANI_DB"] = str(DEMO_DB)  # before importing vani, so seeding goes to the throwaway database
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

load_dotenv(ROOT / ".env")
import imageio_ffmpeg  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
W, H = 1920, 1080

# Sarvam bulbul:v3 speakers. Set VANI to the voice your live agent uses.
VOICES = {
    "NARRATOR": ("shubh", "en-IN"),
    "VANI": ("ritu", "hi-IN"),
    "154979145": ("rahul", "hi-IN"),
    "118932009": ("amit", "hi-IN"),
    "132281146": ("aditya", "hi-IN"),
}
# Microsoft neural voices via edge-tts: (voice, pitch). en-IN voices read Romanised Hinglish well.
EDGE_VOICES = {
    "NARRATOR": ("en-US-AndrewMultilingualNeural", "+0Hz"),
    "VANI": ("en-IN-NeerjaExpressiveNeural", "+0Hz"),
    "154979145": ("en-IN-PrabhatNeural", "+0Hz"),
    "118932009": ("en-IN-PrabhatNeural", "-12Hz"),
    "132281146": ("en-IN-PrabhatNeural", "+10Hz"),
}
SPEED = 1.2  # speech pace and pauses; 1.0 is natural speed
SAPI_VOICES = {"NARRATOR": ("Microsoft Hazel Desktop", 0), "VANI": ("Microsoft Zira Desktop", 0), "SELLER": ("Microsoft Hazel Desktop", -2)}

CALLS = {  # scene number → the seller on the call
    3: {"glid": "154979145", "name": "Miracle Tools And Tackle LLP", "label": "Renew",
        "tool_args": {"create_renewal_link": {"plan": "smaller"}, "schedule_callback": {}},
        "summary": "Renewal agreed on the smaller plan (60 leads, 7,400 rupees); renewal link sent on WhatsApp."},
    4: {"glid": "118932009", "name": "Sovisy India Private Limited", "label": "Upsell",
        "tool_args": {"send_quote": {"category": "RCC Water Tank"}, "schedule_callback": {"time": "in two days", "reason": "upsell follow-up"}},
        "summary": "Interested in RCC Water Tank ads; Premium quote sent on WhatsApp, follow-up in two days."},
    5: {"glid": "132281146", "name": "Chirab Technologies", "label": "Improve",
        "tool_args": {"schedule_callback": {"time": "in two weeks", "reason": "check leads after adding products"}},
        "summary": "All 5 products already in the campaign; seller will list about 5 more Transformer Testers this week. Check-in in two weeks."},
}
GAP, SCENE_GAP, OUTCOME_SECS = 0.35 / SPEED, 0.8 / SPEED, 3.0 / SPEED

# Colours
BG, INK, MUTED, ACCENT = (15, 23, 42), (248, 250, 252), (170, 182, 200), (99, 102, 241)
SPEAKER_COLOUR = {"NARRATOR": (148, 163, 184), "VANI": (129, 140, 248), "SELLER": (52, 211, 153)}


def font(size, bold=False, italic=False):
    name = "segoeuib.ttf" if bold else "segoeuii.ttf" if italic else "segoeui.ttf"
    return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)


# --- Script ----------------------------------------------------------------------------------
def parse_script(path):
    """Scenes with their items: spoken lines (speaker, text, english, tools), and outcome cards."""
    scenes, scene, pending_tools, lines = [], None, [], path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if m := re.match(r"## Scene (\d+) · (.+?)\s+\(", ln):
            scene = {"n": int(m[1]), "title": m[2], "items": [], "quotes": [], "lower_third": ""}
            scenes.append(scene)
        elif ln.startswith("## ") and scene:
            scene = None  # production notes
        elif scene is None:
            pass
        elif ln.startswith("**SCREEN:**"):
            if "Outcome card:" in ln:
                scene["items"].append({"kind": "outcome", "fields": re.findall(r"`(\w+): ([^`]+)`", ln)})
            else:
                quotes = re.findall(r'"([^"]+)"', ln)
                if m := re.search(r'Lower-third: "([^"]+)"', ln):
                    scene["lower_third"] = m[1]
                else:
                    scene["quotes"] += quotes
        elif ln == "**NARRATOR:**":
            i += 1
            while i < len(lines) and lines[i].strip():
                for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", lines[i].strip()):
                    scene["items"].append({"kind": "line", "speaker": "NARRATOR", "text": s, "english": "", "tools": []})
                i += 1
            continue
        elif m := re.match(r"\*\*(VANI|SELLER):\*\* (.+)", ln):
            english = ""
            if i + 1 < len(lines) and (e := re.match(r"\*\((.+)\)\*$", lines[i + 1].strip())):
                english, i = e[1], i + 1
            scene["items"].append({"kind": "line", "speaker": m[1], "text": m[2], "english": english, "tools": pending_tools})
            pending_tools = []
        elif m := re.match(r"`tool: (\w+)`", ln):
            pending_tools = pending_tools + [m[1]]
        i += 1
    return scenes


# --- Voices ----------------------------------------------------------------------------------
def wav_seconds(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def run_ffmpeg(*args):
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])


def tts(item, glid, engine):
    who = item["speaker"] if item["speaker"] != "SELLER" else glid
    voice = {"sarvam": VOICES.get(who), "edge": EDGE_VOICES.get(who), "sapi": SAPI_VOICES[item["speaker"]]}[engine]
    key = (voice, item["text"], engine, SPEED)
    out = OUT / "tts" / (hashlib.sha1(json.dumps(key).encode()).hexdigest()[:16] + ".wav")
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    if engine == "sarvam":
        from sarvamai import SarvamAI
        speaker, lang = VOICES[who]
        r = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"].strip()).text_to_speech.convert(
            text=item["text"], language_code=lang, speaker=speaker, model="bulbul:v3", pace=SPEED,
            speech_sample_rate=24000, output_audio_codec="wav")
        parts = []
        for k, a in enumerate(r.audios):
            p = out.with_suffix(f".part{k}.wav")
            p.write_bytes(base64.b64decode(a))
            parts.append(p)
        if len(parts) == 1:
            parts[0].replace(out)
        else:
            lst = out.with_suffix(".txt")
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
            run_ffmpeg("-f", "concat", "-safe", 0, "-i", lst, out)
    elif engine == "edge":
        name, pitch = voice
        mp3 = out.with_suffix(".mp3")
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", name, f"--rate=+{round(SPEED * 100 - 100)}%",
                        f"--pitch={pitch}", "--text", item["text"], "--write-media", str(mp3)], check=True)
        run_ffmpeg("-i", mp3, "-ar", 24000, "-ac", 1, out)
        mp3.unlink()
    else:
        name, rate = voice
        rate += round((SPEED - 1) * 10)
        txt = out.with_suffix(".txt")
        txt.write_text(item["text"], encoding="utf-8")
        ps = (f"Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SelectVoice('{name}'); $s.Rate={rate}; $s.SetOutputToWaveFile('{out}'); "
              f"$s.Speak([IO.File]::ReadAllText('{txt}')); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return out


# --- Dashboard screenshots -------------------------------------------------------------------
def start_server():
    env = {**os.environ, "VANI_DB": str(DEMO_DB)}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--port", str(PORT)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("dashboard did not start")


def screenshots(browser, shots):
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
    for name, path, prep in shots:
        page.goto(BASE + path, wait_until="networkidle")
        if prep == "conversations":
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            page.evaluate("""() => { const h = [...document.querySelectorAll('h2,h3,summary,b')]
                .find(e => e.textContent.trim().startsWith('Conversations')); if (h) h.scrollIntoView({block: 'start'});
                window.scrollBy(0, -30); }""")
        page.screenshot(path=str(OUT / "shots" / f"{name}.png"))
    page.close()


def seed_calls(scenes):
    """Replay each call's tools and transcript into the demo database, as the live agent would."""
    from vani import tools
    for s in scenes:
        if not (c := CALLS.get(s["n"])):
            continue
        transcript, fields = [], {}
        for it in s["items"]:
            if it["kind"] == "outcome":
                fields = {k: v.strip() for k, v in it["fields"]}
                continue
            for t in it.get("tools", []):
                tools.run(t, c["glid"], c["tool_args"].get(t, {}))
            if it["speaker"] != "NARRATOR":
                transcript.append(f"{'Seller' if it['speaker'] == 'SELLER' else 'VANI'}: {it['text']}")
        tools.log_outcome(c["glid"], channel="phone call", transcript="\n".join(transcript), summary=c["summary"], **fields)


# --- Frames ----------------------------------------------------------------------------------
def wrap(draw, text, f, width):
    words, rows, row = text.split(), [], ""
    for w_ in words:
        cand = f"{row} {w_}".strip()
        if draw.textlength(cand, font=f) <= width or not row:
            row = cand
        else:
            rows.append(row)
            row = w_
    return rows + [row] if row else rows


def shot(name, blur=False):
    im = Image.open(OUT / "shots" / f"{name}.png").convert("RGB").resize((W, H))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(14))
        im = Image.blend(im, Image.new("RGB", (W, H), BG), 0.55)
    return im


def caption(im, speaker, label, text, english):
    d = ImageDraw.Draw(im, "RGBA")
    f_main, f_en = font(44 if english else 40), font(30, italic=True)
    rows, en_rows = wrap(d, text, f_main, W - 280), wrap(d, english, f_en, W - 280) if english else []
    h = 70 + len(rows) * 58 + (14 + len(en_rows) * 40 if en_rows else 0) + 30
    top = H - h - 40
    d.rounded_rectangle((100, top, W - 100, H - 40), 22, fill=(10, 14, 28, 225))
    d.text((140, top + 22), label.upper(), font=font(24, bold=True), fill=SPEAKER_COLOUR[speaker])
    y = top + 62
    for r in rows:
        d.text((140, y), r, font=f_main, fill=INK)
        y += 58
    y += 14
    for r in en_rows:
        d.text((140, y), r, font=f_en, fill=MUTED)
        y += 40


def lower_third(im, text):
    d = ImageDraw.Draw(im, "RGBA")
    f = font(34, bold=True)
    w_ = d.textlength(text, font=f)
    d.rounded_rectangle((100, 60, 100 + w_ + 60, 136), 16, fill=(*ACCENT, 235))
    d.text((130, 76), text, font=f, fill=INK)


def tool_chip(im, names):
    d = ImageDraw.Draw(im, "RGBA")
    f = font(28, bold=True)
    y = 330
    for n in names:
        t = f"Tool call  ·  {n}"
        w_ = d.textlength(t, font=f)
        d.rounded_rectangle((W - 160 - w_, y, W - 100, y + 60), 30, fill=(250, 204, 21, 240))
        d.text((W - 130 - w_, y + 11), t, font=f, fill=(30, 27, 10))
        y += 76


def call_card(im, call, speaker):
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((460, 70, W - 460, 290), 28, fill=(15, 23, 42, 235), outline=(255, 255, 255, 40), width=2)
    d.text((W // 2, 104), f"Outbound call  ·  {call['label']}", font=font(26), fill=MUTED, anchor="mm")
    for x, who, name in ((690, "VANI", "VANI"), (W - 690, "SELLER", call["name"])):
        active = speaker == who
        col = SPEAKER_COLOUR[who]
        r = 52 if active else 44
        if active:
            d.ellipse((x - r - 12, 190 - r - 12, x + r + 12, 190 + r + 12), outline=(*col, 160), width=5)
        d.ellipse((x - r, 190 - r, x + r, 190 + r), fill=(*col, 255 if active else 120))
        d.text((x, 190), name[0], font=font(44, bold=True), fill=BG, anchor="mm")
        d.text((x, 268), name if len(name) < 30 else name[:28] + "…", font=font(26, bold=active), fill=INK if active else MUTED, anchor="mm")
    d.line((800, 190, W - 800, 190), fill=(255, 255, 255, 70), width=3)


def title_card(lines, reveal):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im, "RGBA")
    for k in range(0, 600, 4):  # soft glow
        d.ellipse((W // 2 - 900 + k, -700 + k, W // 2 + 900 - k, 900 - k), fill=(*ACCENT, 1))
    d.text((W // 2, 390), lines[0], font=font(76, bold=True), fill=INK, anchor="mm")
    for k, ln in enumerate(lines[1:reveal + 1]):
        d.text((W // 2, 520 + k * 80), ln, font=font(44), fill=MUTED, anchor="mm")
    return im


def outcome_card(im, call, fields):
    d = ImageDraw.Draw(im, "RGBA")
    h = 200 + len(fields) * 74
    top = (H - h) // 2
    d.rounded_rectangle((520, top, W - 520, top + h), 28, fill=(15, 23, 42, 240), outline=(*SPEAKER_COLOUR["SELLER"], 200), width=3)
    d.text((580, top + 50), "Saved after the call", font=font(40, bold=True), fill=INK)
    d.text((580, top + 108), call["name"], font=font(28), fill=MUTED)
    for k, (key, val) in enumerate(fields):
        y = top + 170 + k * 74
        d.text((580, y), key, font=font(30), fill=MUTED)
        d.text((W - 580, y), val, font=font(32, bold=True), fill=SPEAKER_COLOUR["SELLER"], anchor="ra")


SCENE_SHOTS = {  # scene → screenshot per narrator sentence (last one repeats)
    2: ["home", "home", "seller_154979145", "seller_154979145", "home"],
    6: ["conversations_132281146", "whatsapp_118932009", "after_132281146"],
}


def frames(scenes):
    """Yield (scene, item, image) for every item."""
    for s in scenes:
        narr_i = 0
        call = CALLS.get(s["n"])
        for it in s["items"]:
            if it["kind"] == "outcome":
                im = shot(f"after_{call['glid']}", blur=True)
                outcome_card(im, call, it["fields"])
            elif s["n"] in (1, 7):
                lines = s["quotes"] if s["n"] == 1 else [s["quotes"][0], s["quotes"][1]]
                im = title_card(lines, narr_i + (0 if s["n"] == 1 else 1))
                caption(im, "NARRATOR", "Narrator", it["text"], "")
            elif call and it["speaker"] == "NARRATOR":
                im = shot(f"seller_{call['glid']}")
                lower_third(im, s["lower_third"])
                caption(im, "NARRATOR", "Narrator", it["text"], "")
            elif call:
                im = shot(f"seller_{call['glid']}", blur=True)
                call_card(im, call, it["speaker"])
                if it["tools"]:
                    tool_chip(im, it["tools"])
                caption(im, it["speaker"], "VANI" if it["speaker"] == "VANI" else call["name"], it["text"], it["english"])
            else:
                names = SCENE_SHOTS[s["n"]]
                im = shot(names[min(narr_i, len(names) - 1)])
                caption(im, "NARRATOR", "Narrator", it["text"], "")
            if it["kind"] == "line" and it["speaker"] == "NARRATOR":
                narr_i += 1
            yield s, it, im


# --- Main ------------------------------------------------------------------------------------
def ts(t, srt=True):
    h, rem = divmod(t, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{sec:06.3f}".replace(".", ",") if srt else f"{int(m):02}:{int(sec):02}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", choices=["edge", "sarvam", "sapi"], default="edge")
    args = ap.parse_args()

    scenes = parse_script(ROOT / "demo" / "demo-script.md")
    for sub in ("shots", "frames", "segments"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    print("voices…")
    for s in scenes:
        glid = CALLS.get(s["n"], {}).get("glid")
        for it in s["items"]:
            if it["kind"] == "line":
                it["wav"] = tts(it, glid, args.voice)

    print("screenshots…")
    DEMO_DB.unlink(missing_ok=True)
    from playwright.sync_api import sync_playwright
    proc = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            screenshots(browser, [("home", "/", None)] + [(f"seller_{c['glid']}", f"/seller/{c['glid']}", None) for c in CALLS.values()])
            seed_calls(scenes)
            screenshots(browser, [("activity", "/activity", None), ("whatsapp_118932009", "/whatsapp/118932009", None),
                                  ("conversations_132281146", "/seller/132281146", "conversations")]
                        + [(f"after_{c['glid']}", f"/seller/{c['glid']}", None) for c in CALLS.values()])
            browser.close()
    finally:
        proc.kill()

    print("frames and segments…")
    t, srt, md, segs, last_scene = 0.0, [], ["# VANI demo · transcript", ""], [], None
    for k, (s, it, im) in enumerate(frames(scenes)):
        if s is not last_scene:
            md += [f"## Scene {s['n']} · {s['title']}", ""]
            last_scene = s
        png, seg = OUT / "frames" / f"{k:03}.png", OUT / "segments" / f"{k:03}.mp4"
        im.save(png)
        last_in_scene = it is s["items"][-1]
        if it["kind"] == "outcome":
            dur = OUTCOME_SECS
            run_ffmpeg("-loop", 1, "-i", png, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", dur,
                       "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-r", 30, "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-ar", 48000, "-ac", 2, seg)
            md += ["*Saved after the call:* " + " · ".join(f"`{a}: {b}`" for a, b in it["fields"]), ""]
        else:
            speech = wav_seconds(it["wav"])
            dur = speech + (SCENE_GAP if last_in_scene else GAP)
            run_ffmpeg("-loop", 1, "-i", png, "-i", it["wav"], "-af", f"apad=whole_dur={dur}", "-t", dur,
                       "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-r", 30, "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-ar", 48000, "-ac", 2, seg)
            who = {"SELLER": "Seller", "VANI": "VANI", "NARRATOR": "Narrator"}[it["speaker"]]
            srt += [str(len(srt) // 4 + 1), f"{ts(t)} --> {ts(t + speech)}",
                    f"{who}: {it['text']}" + (f"\n{it['english']}" if it["english"] else ""), ""]
            md += ([f"`→ tool: {', '.join(it['tools'])}`", ""] if it["tools"] else []) + [
                   f"**[{ts(t, False)}] {who}:** {it['text']}" + (f"  \n*{it['english']}*" if it["english"] else ""), ""]
        t += dur
        segs.append(seg)

    lst = OUT / "segments.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs))
    video = OUT / "vani-demo.mp4"
    run_ffmpeg("-f", "concat", "-safe", 0, "-i", lst, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", video)
    (OUT / "vani-demo.srt").write_text("\n".join(srt), encoding="utf-8")
    (OUT / "transcript.md").write_text("\n".join(x for x in md if x is not None), encoding="utf-8")
    print(f"done: {video} ({ts(t, False)})")


if __name__ == "__main__":
    main()
