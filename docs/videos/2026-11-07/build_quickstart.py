"""A 90-second cut of the real UI captures, with shorter Korean captions."""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import build_video as video

CUT = [
    ("01_start", 6, "문헌 한 편에서 보고서 한 문단까지 따라 해 보세요.\n조사 질문 또는 이미 가진 PDF로 시작합니다."),
    ("02_question", 7, "알아볼 질문과 검색어를 적습니다.\n예: AI 도구는 숙련 개발자의 작업 시간을 줄여줄까?"),
    ("04b_results", 7, "검색 결과에서 관심 있는 논문을 후보함에 담습니다.\n다시 읽을 이유도 메모해 두세요."),
    ("06_pdf_collect", 7, "‘공개 PDF 찾아 등록’으로 원문을 가져옵니다.\n이미 받은 PDF는 ‘내 PDF’에서 직접 등록할 수 있습니다."),
    ("07_local_search", 7, "‘원문 검색·노트’에서 필요한 단어를 찾습니다.\n이 검색은 내 PDF 안에서 AI 없이 작동합니다."),
    ("09_note", 9, "원문 발췌와 내 생각을 구분해 노트로 저장하세요.\n문헌과 PDF 쪽수가 함께 남아 인용 근거를 되짚을 수 있습니다."),
    ("10_note_to_report", 6, "‘저장한 노트로 보고서 쓰기’를 누릅니다.\n읽은 내용이 보고서의 근거로 연결됩니다."),
    ("11_draft", 9, "논점 제목·핵심 주장·내 문단을 작성하고 저장하세요.\n연결한 원문과 메모를 옆에서 보며 쓸 수 있습니다."),
    ("12_source_back", 6, "근거가 궁금하면 ‘원문에서 확인’을 누르세요.\n원문을 읽고 다시 초안으로 돌아올 수 있습니다."),
    ("14_report_preview", 7, "전체 초안에서 문단과 출처 주석을 확인합니다.\nMarkdown 문서로 내려받아 집필을 이어가세요."),
    ("21_pdf_highlight", 10, "여러 편을 비교할 때는 ‘근거 비교’를 추가로 쓰세요.\nAI 결과는 원문을 읽고 판단합니다. 이 화면은 사전 준비한 예제입니다."),
    ("29_finish", 9, "검색 → PDF 확보 → 노트 → 보고서, 이 네 단계로 시작하세요.\n자세한 기능은 전체 사용법 영상에서 볼 수 있습니다."),
]


def main():
    video.BUILD = video.ROOT / "build-quickstart"
    video.BUILD.mkdir(exist_ok=True)
    originals = {s["id"]: s for s in json.loads((video.ROOT / "scenes.json").read_text())}
    scenes, srt, elapsed = [], [], 0
    for i, (ident, seconds, caption) in enumerate(CUT):
        scene = {**originals[ident], "seconds": seconds, "caption": caption,
                 "chapter": "90초 빠른 시작 · 문헌 한 편에서 보고서까지", "start_seconds": elapsed}
        scenes.append(scene)
        video.make_scene(scene, i+1, len(CUT)).save(video.BUILD / f"{i:02d}-base.png")
        srt.append(f"{i+1}\n{video.clock(elapsed)} --> {video.clock(elapsed+seconds)}\n{caption}\n")
        elapsed += seconds
    assert elapsed == 90
    video.make_pointer_assets()
    (video.ROOT / "deep-research-kit-quickstart-ko.srt").write_text("\n".join(srt), encoding="utf-8")
    (video.ROOT / "quickstart-timeline.json").write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    with ThreadPoolExecutor(max_workers=3) as pool:
        for job in as_completed([pool.submit(video.render_clip, s, i) for i, s in enumerate(scenes)]):
            i, _ = job.result()
            print(f"Rendered quickstart {i+1}/{len(CUT)}", flush=True)
    concat = video.BUILD / "concat.txt"
    concat.write_text("\n".join(f"file '{i:02d}-clip.mp4'" for i in range(len(CUT))))
    out = video.ROOT / "deep-research-kit-quickstart-ko.mp4"
    subprocess.run([video.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-c:v", "copy", "-metadata", "title=Deep Research Kit · 90초 빠른 시작",
                    "-movflags", "+faststart", str(out)], check=True)
    print(f"DONE: {out} ({out.stat().st_size/1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
