"""Build the Korean-captioned walkthrough from actual application captures.

Requires Pillow and ffmpeg. Run from any directory with Python 3.11+.
The screenshots document real interactions; this is an edited walkthrough,
not a continuous screen recording. No speech or external AI calls are added.
"""

import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
BUILD = ROOT / "build"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
W, H, FPS = 1920, 1080, 24
SX, SY, SCALE = 160, 60, 1.25
BG = "#101626"
FG = "#F5F7FF"
MUTED = "#AEBAD4"
ACCENT = "#A99CFF"
CLICK_IDS = {
    "01_start", "02_question", "03_search", "04b_results", "05_reason",
    "06_pdf_collect", "07_local_search", "09_note", "10_note_to_report",
    "11_draft", "12_source_back", "13_return", "16_exports", "17_comparison",
    "22_review_save", "23_next", "24_filter", "26_evidence_export", "28_local",
}


def font(size):
    return ImageFont.truetype(FONT, size)


def center_text(draw, text, y, size, fill=FG):
    f = font(size)
    draw.text(((W - draw.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def clock(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_intro():
    out = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((78, 70, 377, 114), radius=22, fill="#292445")
    d.text((100, 78), "실제 화면 · 한국어 자막", font=font(24), fill="#D5CCFF")
    d.text((80, 155), "Deep Research Kit", font=font(70), fill=FG)
    d.text((84, 250), "문헌 찾기부터", font=font(50), fill=FG)
    d.text((84, 315), "근거가 남는 보고서까지", font=font(50), fill=FG)
    d.text((86, 435), "찾고  →  읽고  →  검토하고  →  쓰기", font=font(29), fill=ACCENT)
    d.text((86, 503), "실제 기능을 눌러 보며 따라가는 활용 안내", font=font(27), fill=MUTED)
    shots = [
        ("11_draft", (944, 120, 1760, 579)),
        ("21_pdf_highlight", (1040, 440, 1856, 899)),
    ]
    for ident, rect in shots:
        x1, y1, x2, y2 = rect
        d.rounded_rectangle((x1-8, y1-8, x2+8, y2+8), radius=14, fill="#3B4564")
        shot = Image.open(ASSETS / f"{ident}.jpg").convert("RGB")
        out.paste(shot.resize((x2-x1, y2-y1), Image.Resampling.LANCZOS), (x1, y1))
    d.text((86, 738), "이럴 때 유용합니다", font=font(25), fill=ACCENT)
    for i, line in enumerate(["읽은 논문의 핵심과 내 생각을 남길 때", "여러 연구의 결과와 한계를 비교할 때", "원문을 다시 확인하며 보고서를 쓸 때"]):
        d.text((86, 785+i*43), line, font=font(28), fill=FG)
    d.rectangle((0, 970, W, H), fill="#0A0F1C")
    center_text(d, "검색부터 원문 검토, 노트와 보고서까지 실제 사용 흐름을 살펴봅니다.", 985, 32)
    center_text(d, "앱 조작 전후 화면을 편집했으며, 한국어 자막으로 설명합니다.", 1031, 28, MUTED)
    return out


def make_scene(scene, number, count):
    out = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(out)
    d.text((SX, 15), scene["chapter"], font=font(27), fill=FG)
    label = f"DEEP RESEARCH KIT     {number:02d} / {count:02d}"
    f = font(20)
    d.text((W-SX-d.textlength(label, font=f), 20), label, font=f, fill=MUTED)
    shot = Image.open(ASSETS / f"{scene['id']}.jpg").convert("RGB")
    if shot.size != (1280, 720):
        raise ValueError(f"Unexpected screenshot size: {scene['id']} {shot.size}")
    out.paste(shot.resize((1600, 900), Image.Resampling.LANCZOS), (SX, SY))
    d.rectangle((0, 965, W, H), fill="#0A0F1C")
    lines = scene["caption"].splitlines()
    size = 32
    while max(d.textlength(line, font=font(size)) for line in lines) > 1790:
        size -= 1
    for i, line in enumerate(lines):
        center_text(d, line, 985 + i * 44, size)
    d.rectangle((0, H-4, int(W * number / count), H), fill=ACCENT)
    return out


def make_pointer_assets():
    # Supersampling keeps the cursor crisp on high-density screens.
    s = 4
    cur = Image.new("RGBA", (48*s, 58*s))
    d = ImageDraw.Draw(cur)
    points = [(3, 2), (3, 43), (14, 34), (23, 53), (31, 49), (22, 30), (38, 30)]
    d.polygon([(x*s, y*s) for x, y in points], fill="white", outline="#172036", width=2*s)
    cur.resize((48, 58), Image.Resampling.LANCZOS).save(BUILD / "cursor.png")
    ripple = Image.new("RGBA", (96*s, 96*s))
    d = ImageDraw.Draw(ripple)
    d.ellipse((4*s, 4*s, 92*s, 92*s), fill=(124, 96, 255, 25), outline=(124, 96, 255, 220), width=3*s)
    d.ellipse((23*s, 23*s, 73*s, 73*s), fill=(124, 96, 255, 40), outline=(224, 219, 255, 230), width=2*s)
    ripple.resize((96, 96), Image.Resampling.LANCZOS).save(BUILD / "click.png")


def render_clip(scene, index):
    duration = scene["seconds"]
    base = BUILD / f"{index:02d}-base.png"
    clip = BUILD / f"{index:02d}-clip.mp4"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(base)]
    target = scene.get("target")
    if target and scene["id"] in CLICK_IDS:
        tx = SX + SCALE * (target["x"] + target["width"] / 2)
        ty = SY + SCALE * (target["y"] + target["height"] / 2)
        move_start = duration - 1.5
        progress = f"clip((t-{move_start})/0.85,0,1)"
        for asset in ("cursor.png", "click.png"):
            cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(BUILD / asset)]
        # Pointer arrives, a short click pulse appears, and the next actual UI state follows.
        graph = (
            f"[0:v][2:v]overlay=x={tx-48}:y={ty-48}:enable='gte(t,{duration-0.32})'[ring];"
            f"[ring][1:v]overlay=x='{tx}+80*(1-{progress})':"
            f"y='{ty}+48*(1-{progress})':enable='gte(t,{move_start})',format=yuv420p[v]"
        )
        cmd += ["-filter_complex_threads", "1", "-filter_complex", graph, "-map", "[v]"]
    else:
        cmd += ["-vf", "format=yuv420p"]
    cmd += ["-t", str(duration), "-r", str(FPS), "-an", "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "19", "-tune", "stillimage", "-movflags", "+faststart", str(clip)]
    subprocess.run(cmd, check=True, capture_output=True)
    return index, clip


def main():
    BUILD.mkdir(exist_ok=True)
    scenes = json.loads((ROOT / "scenes.json").read_text())
    intro = {"id": "intro", "chapter": "소개", "seconds": 6, "caption": "검색부터 원문 검토, 노트와 보고서까지 실제 사용 흐름을 살펴봅니다.\n앱 조작 전후 화면을 편집했으며, 한국어 자막으로 설명합니다."}
    all_scenes = [intro] + scenes
    make_intro().save(BUILD / "00-base.png")
    make_intro().save(ROOT / "deep-research-kit-intro-poster.jpg", quality=94)
    for i, scene in enumerate(scenes, 1):
        make_scene(scene, i, len(scenes)).save(BUILD / f"{i:02d}-base.png")
    make_pointer_assets()
    elapsed = 0
    srt = []
    chapter_data = []
    for i, scene in enumerate(all_scenes, 1):
        srt.append(f"{i}\n{clock(elapsed)} --> {clock(elapsed + scene['seconds'])}\n{scene['caption']}\n")
        if not chapter_data or chapter_data[-1]["title"] != scene["chapter"]:
            chapter_data.append({"title": scene["chapter"], "start": elapsed})
        scene["start_seconds"] = elapsed
        elapsed += scene["seconds"]
    (ROOT / "deep-research-kit-intro-ko.srt").write_text("\n".join(srt), encoding="utf-8")
    (ROOT / "timeline.json").write_text(json.dumps(all_scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = [";FFMETADATA1", "title=Deep Research Kit 기능 소개 · 한국어 자막", "comment=실제 앱 조작 전후 화면을 편집한 안내 영상. AI 비교표는 준비된 예제 응답을 사용했습니다."]
    for i, chapter in enumerate(chapter_data):
        end = chapter_data[i+1]["start"] if i+1 < len(chapter_data) else elapsed
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={chapter['start']*1000}", f"END={end*1000}", f"title={chapter['title']}"]
    (BUILD / "chapters.ffmeta").write_text("\n".join(meta), encoding="utf-8")
    print(f"Rendering {len(all_scenes)} scenes, {elapsed} seconds", flush=True)
    clips = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(render_clip, scene, i) for i, scene in enumerate(all_scenes)]
        for job in as_completed(jobs):
            i, path = job.result()
            clips[i] = path
            print(f"Rendered {i:02d}: {all_scenes[i]['id']}", flush=True)
    concat = BUILD / "concat.txt"
    concat.write_text("\n".join(f"file '{clips[i].name}'" for i in range(len(all_scenes))), encoding="utf-8")
    dest = ROOT / "deep-research-kit-intro-ko.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(BUILD / "chapters.ffmeta"), "-map", "0:v:0", "-map_metadata", "1", "-map_chapters", "1", "-c:v", "copy", "-movflags", "+faststart", str(dest)], check=True)
    print(f"DONE: {dest} ({dest.stat().st_size / 1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
