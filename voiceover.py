import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

SEGMENTS = [
    (0.0, 4.4, "Online-hisobot ilovasidan foydalanish yo'riqnomasi."),
    (4.4, 14.2, "Avval tizimga kiring: ism-familiyangizni yozing va dars o'tadigan faningizni tanlang.So'ng «Tizimga kirish» tugmasini bosing."),
    (14.3, 26.4, "CHSB yoki BSB nazorat turini tanlang. Chorakni va sinfni belgilang. So'ng butun sinfni yoki alohida guruhni tanlang."),
    (23, 37.0, "Jami maksimal ballni kiriting. Plyus tugmasi orqali topshiriqlar qo'shing, har biriga ball belgilang. Kerak bo'lsa, ularni ko'paytiring."),
        (37, 39.8, " So'ng «Yuklab olish» tugmasini bosing, shablon tayyor!"),
    (44.0, 48.2, "Eng qiziq imkoniyat: AI Smart baholash. Uni yoqsangiz, ilova aqlli baholash panelini ochadi.Va sizga o'quvchilar ro'yxatini ko'rsatadi."),
    (54.2, 60.4, "Mikrofon tugmasini bosing va o'quvchining ismi hamda balini ayting. Ilova ballni jadvalga o'zi yozib qo'yadi."),
    (56.4, 67.6, "Jadvalda o'quvchilar ro'yxati va foizlari ko'rinadi. Hisobotni yuklab oling!"),
    (67.6, 76.0, "Hammasi tayyor. Savollaringiz bo'lsa, «Dasturchi bilan bog'lanish» tugmasini bosing."),
]


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


async def synth(text, path, voice, rate, pitch):
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)


def fake_synth(text, path):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={len(text) * 0.065:.2f}", path])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("-o", "--output", default="video_ovozli.mp4")
    p.add_argument("--voice", default="uz-UZ-MadinaNeural")
    p.add_argument("--rate", default="+10%")
    p.add_argument("--pitch", default="+0Hz")
    p.add_argument("--keep-original-audio", action="store_true")
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()

    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        p.error(
            "required tool(s) not found on PATH: " + ", ".join(missing)
            + ". Install FFmpeg, add its bin folder to PATH, and reopen the terminal."
        )

    tmp = tempfile.mkdtemp()
    clips = []
    next_start = 0.0
    for i, (start, _, text) in enumerate(SEGMENTS, 1):
        path = os.path.join(tmp, f"s{i}.mp3")
        if a.dry:
            fake_synth(text, path)
        else:
            asyncio.run(synth(text, path, a.voice, a.rate, a.pitch))
        d = duration(path)
        actual_start = max(start, next_start)
        clips.append((actual_start, path))
        next_start = actual_start + d + 0.15
        print(f"{i}-bo'lak: {actual_start:.1f}s da boshlanadi, {d:.1f}s")

    video_duration = duration(a.video)
    render_duration = max(video_duration, clips[-1][0] + duration(clips[-1][1]) + 0.5)
    black_duration = render_duration - video_duration

    cmd = ["ffmpeg", "-y", "-i", a.video]
    for _, path in clips:
        cmd += ["-i", path]

    parts = []
    labels = []
    for i, (start, _) in enumerate(clips, 1):
        ms = int(start * 1000)
        parts.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    n = len(clips)
    if a.keep_original_audio:
        parts.append("[0:a]volume=0.25[bg]")
        labels.append("[bg]")
        n += 1
    parts.append("".join(labels) + f"amix=inputs={n}:duration=longest:dropout_transition=0,volume={n}[aout]")

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "0:v", "-map", "[aout]",
        "-vf", f"tpad=stop_mode=add:stop_duration={black_duration:.3f}:color=black",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(render_duration),
        a.output,
    ]
    run(cmd)
    print("Tayyor:", a.output)


if __name__ == "__main__":
    main()
