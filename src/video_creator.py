from pathlib import Path
from typing import List, Dict
import subprocess
import os

# MoviePy is only used for probing when needed; output is assembled with ffmpeg for reliability
from moviepy.video.io.VideoFileClip import VideoFileClip


def _quote_filter_str(s: str) -> str:
	# Quote for FFmpeg filter parameter values
	return "'" + s.replace("'", r"\'") + "'"


def _write_overlay_text(tmp_dir: Path, idx: int, text: str) -> Path:
	path = tmp_dir / f"overlay_{idx}.txt"
	path.parent.mkdir(parents=True, exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		f.write(text or "")
	return path


def _build_drawtext_filter_from_file(textfile: Path) -> str:
	# Avoid fontfile to reduce Windows parsing issues; rely on default font
	options: list[str] = []
	options.append(f"textfile={_quote_filter_str(textfile.resolve().as_posix())}")
	options.extend([
		"fontcolor=white",
		"fontsize=24",
		"borderw=2",
		"bordercolor=black",
		"x=(w-text_w)/2",
		"y=(h-text_h)/2",
		"line_spacing=8",
		"box=1",
		"boxcolor=black@0.3",
		"boxborderw=12",
	])
	return "drawtext=" + ":".join(options)


def _run_ffmpeg(cmd: list[str]) -> bool:
	try:
		subprocess.run(cmd, check=True)
		return True
	except Exception as e:
		print(f"ffmpeg error: {e}")
		return False


def _ffprobe_duration_seconds(path: Path) -> float | None:
	try:
		result = subprocess.run([
			"ffprobe", "-v", "error", "-show_entries", "format=duration",
			"-of", "default=noprint_wrappers=1:nokey=1", str(path)
		], capture_output=True, text=True, check=True)
		val = result.stdout.strip()
		return float(val) if val else None
	except Exception:
		return None


def _format_srt_timestamp(seconds: float) -> str:
	# Format seconds into SRT timestamp: HH:MM:SS,mmm
	hours = int(seconds // 3600)
	minutes = int((seconds % 3600) // 60)
	secs = int(seconds % 60)
	millis = int((seconds - int(seconds)) * 1000)
	return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_srt(tmp_dir: Path, segments: List[Dict[str, str]], durations: List[float]) -> Path:
	path = tmp_dir / "subtitles.srt"
	path.parent.mkdir(parents=True, exist_ok=True)
	start = 0.0
	with open(path, "w", encoding="utf-8") as f:
		for idx, (seg, dur) in enumerate(zip(segments, durations), start=1):
			text = (seg.get("text") or "").strip()
			if not text:
				start += dur
				continue
			end = start + dur
			f.write(f"{idx}\n")
			f.write(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n")
			# SRT expects plain text lines. Enforce a maximum of two lines.
			# If the text has multiple lines, flatten and re-wrap into up to two lines
			# by splitting on words and balancing roughly.
			single = " ".join([ln.strip() for ln in text.splitlines() if ln.strip()])
			words = single.split()
			if len(words) <= 0:
				lines = [""]
			elif len(words) <= 10:
				# short text, keep as single line
				lines = [single]
			else:
				# split into two roughly equal halves
				half = len(words) // 2
				# try to balance by moving boundary to nearest space that keeps line lengths similar
				left = words[:half]
				right = words[half:]
				lines = [" ".join(left).strip(), " ".join(right).strip()]
			for line in lines[:2]:
				f.write(line + "\n")
			f.write("\n")
			start = end
	return path


def _format_ass_timestamp(seconds: float) -> str:
	# ASS uses H:MM:SS.cc where cc = centiseconds
	hours = int(seconds // 3600)
	minutes = int((seconds % 3600) // 60)
	secs = int(seconds % 60)
	cents = int((seconds - int(seconds)) * 100)
	return f"{hours:d}:{minutes:02d}:{secs:02d}.{cents:02d}"


def _write_ass(tmp_dir: Path, segments: List[Dict[str, str]], durations: List[float]) -> Path:
	path = tmp_dir / "subtitles.ass"
	path.parent.mkdir(parents=True, exist_ok=True)
	# Basic ASS header with a Default style centered and fontsize 24
	header = [
		"[Script Info]",
		"ScriptType: v4.00+",
		"PlayResX: 1920",
		"PlayResY: 1080",
		"",
		"[V4+ Styles]",
		"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
		"Style: Default,Arial,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,5,10,10,10,1",
		"",
		"[Events]",
		"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
	]
	lines = []
	start = 0.0
	for seg, dur in zip(segments, durations):
		text = (seg.get("text") or "").strip()
		if not text:
			start += dur
			continue
		end = start + dur
		# flatten and limit to two lines via the same logic as SRT
		single = " ".join([ln.strip() for ln in text.splitlines() if ln.strip()])
		words = single.split()
		if len(words) <= 10:
			out_lines = [single]
		else:
			half = len(words) // 2
			out_lines = [" ".join(words[:half]).strip(), " ".join(words[half:]).strip()]
		# ASS line breaks are \N
		ass_text = "\\N".join(out_lines[:2])
		lines.append(f"Dialogue: 0,{_format_ass_timestamp(start)},{_format_ass_timestamp(end)},Default,,0,0,0,,{ass_text}")
		start = end
	with open(path, "w", encoding="utf-8") as f:
		f.write("\n".join(header + lines))
	return path


def _build_subtitles_filter_from_file(srtfile: Path, width: int, height: int) -> str:
	# Use libass via subtitles filter and force styling to centre the text.
	# Use the 'filename=' option. Prefer a relative path (no drive letter) when
	# the srt lives under the current working directory to avoid parsing issues
	# with Windows drive letters (C:). If relative path is not possible, fall
	# back to the absolute posix path.
	s_path = srtfile.resolve()
	try:
		rel = s_path.relative_to(Path.cwd()).as_posix()
		s = rel
	except Exception:
		s = s_path.as_posix()
	# Alignment=5 centers subtitle text in the middle (ASS alignment mapping)
	# Use a fixed fontsize of 24 for clarity on small screens
	style = "Alignment=5,FontName=Arial,Fontsize=24,PrimaryColour=&H00FFFFFF&,BackColour=&H00000000&,Outline=1,BorderStyle=3"
	# Surround filename with single quotes if it contains characters that could
	# confuse the filter parser (spaces, commas). Use single quotes inside the
	# filter expression; ffmpeg's parser expects that.
	needs_quotes = any(ch in s for ch in [' ', ',', ':'])
	filename_part = f"filename='{s}'" if needs_quotes else f"filename={s}"
	return f"subtitles={filename_part}:force_style='{style}'"


def _reencode_with_ffmpeg(src: Path, dst: Path, width: int, height: int, fps: int, max_seconds: float | None = None, overlay_textfile: Path | None = None) -> bool:
	dst.parent.mkdir(parents=True, exist_ok=True)
	vf_parts = [
		f"scale='min({width},iw)':'min({height},ih)':force_original_aspect_ratio=decrease",
		f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
		f"fps={fps}",
	]
	if overlay_textfile:
		vf_parts.append(_build_drawtext_filter_from_file(overlay_textfile))
	vf = ",".join(vf_parts)
	cmd = [
		"ffmpeg", "-y", "-v", "error",
		"-i", str(src),
		"-vf", vf,
		"-r", str(fps),
		"-an",
		"-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
	]
	if max_seconds is not None and max_seconds > 0:
		cmd.extend(["-t", str(max_seconds)])
	cmd.append(str(dst))
	if _run_ffmpeg(cmd):
		return True
	# Retry without overlay if drawtext caused failure
	if overlay_textfile:
		vf_no = ",".join(vf_parts[:-1])
		cmd_no = [
			"ffmpeg", "-y", "-v", "error",
			"-i", str(src),
			"-vf", vf_no,
			"-r", str(fps),
			"-an",
			"-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
		]
		if max_seconds is not None and max_seconds > 0:
			cmd_no.extend(["-t", str(max_seconds)])
		cmd_no.append(str(dst))
		return _run_ffmpeg(cmd_no)
	return False


def _image_to_video(src: Path, dst: Path, width: int, height: int, fps: int, seconds: int = 5, overlay_textfile: Path | None = None) -> bool:
	dst.parent.mkdir(parents=True, exist_ok=True)
	vf_parts = [
		f"scale='min({width},iw)':'min({height},ih)':force_original_aspect_ratio=decrease",
		f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
		f"zoompan=z='min(zoom+0.0015,1.1)':d={seconds*fps}:s={width}x{height}",
	]
	if overlay_textfile:
		vf_parts.append(_build_drawtext_filter_from_file(overlay_textfile))
	vf = ",".join(vf_parts)
	cmd = [
		"ffmpeg", "-y", "-v", "error",
		"-loop", "1",
		"-t", str(seconds),
		"-i", str(src),
		"-vf", vf,
		"-r", str(fps),
		"-an",
		"-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
		str(dst),
	]
	if _run_ffmpeg(cmd):
		return True
	# Retry without overlay
	if overlay_textfile:
		vf_no = ",".join(vf_parts[:-1])
		cmd_no = [
			"ffmpeg", "-y", "-v", "error",
			"-loop", "1",
			"-t", str(seconds),
			"-i", str(src),
			"-vf", vf_no,
			"-r", str(fps),
			"-an",
			"-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
			str(dst),
		]
		return _run_ffmpeg(cmd_no)
	return False


def _concat_segments_ffmpeg(segments: List[Path], dst: Path) -> bool:
	if not segments:
		return False
	list_file = dst.with_suffix(".list.txt")
	list_file.parent.mkdir(parents=True, exist_ok=True)
	with open(list_file, "w", encoding="utf-8") as f:
		for seg in segments:
			abs_posix = seg.resolve().as_posix()
			f.write(f"file '{abs_posix}'\n")
	cmd = [
		"ffmpeg", "-y", "-v", "error",
		"-f", "concat", "-safe", "0",
		"-i", str(list_file.resolve()),
		"-c", "copy",
		str(dst),
	]
	return _run_ffmpeg(cmd)


def _mux_audio(video_src: Path, audio_src: Path, dst: Path) -> bool:
	cmd = [
		"ffmpeg", "-y", "-v", "error",
		"-i", str(video_src),
		"-i", str(audio_src),
		"-map", "0:v:0", "-map", "1:a:0",
		"-c:v", "copy", "-c:a", "aac",
		"-shortest",
		str(dst),
	]
	return _run_ffmpeg(cmd)


def _black_fallback(dst: Path, width: int, height: int, fps: int, seconds: int, overlay_textfile: Path | None = None) -> bool:
	cmd = [
		"ffmpeg", "-y", "-v", "error",
		"-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
		"-t", str(seconds),
	]
	if overlay_textfile:
		vf = _build_drawtext_filter_from_file(overlay_textfile)
		cmd.extend(["-vf", vf])
	cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst)])
	return _run_ffmpeg(cmd)


def create_video_with_subtitles(assets: List[Path], voiceover: Path, segments: List[Dict[str, str]], width: int, height: int, fps: int, max_duration: int, out_path: Path) -> Path:
	tmp_dir = out_path.parent / "tmp_v"
	tmp_dir.mkdir(parents=True, exist_ok=True)

	# Derive per-line duration from narration duration, capped by max_duration
	audio_dur = _ffprobe_duration_seconds(voiceover) or float(max_duration)
	target_total = min(float(max_duration), audio_dur)
	num_lines = max(1, len(segments))
	per_line = max(0.8, target_total / num_lines)  # at least ~0.8s per line

	# Prepare one segment per line, cycling assets as needed
	prepared: List[Path] = []
	used = 0.0
	durations: List[float] = []
	if not assets:
		# if no assets, use black clips per line
		for i in range(num_lines):
			if used >= target_total - 0.01:
				break
			seg_path = tmp_dir / f"seg_{i}.mp4"
			secs = min(per_line, target_total - used)
			_black_fallback(seg_path, width, height, fps, seconds=int(secs))
			prepared.append(seg_path)
			durations.append(secs)
			used += secs
	else:
		for i in range(num_lines):
			if used >= target_total - 0.01:
				break
			asset = assets[i % len(assets)]
			seg_path = tmp_dir / f"seg_{i}.mp4"
			secs = min(per_line, target_total - used)
			if asset.suffix.lower() == ".mp4":
				_ok = _reencode_with_ffmpeg(asset, seg_path, width, height, fps, max_seconds=secs)
				if not _ok:
					# fallback to black if this asset fails
					_black_fallback(seg_path, width, height, fps, seconds=int(secs))
			else:
				_ok = _image_to_video(asset, seg_path, width, height, fps, seconds=int(secs))
				if not _ok:
					_black_fallback(seg_path, width, height, fps, seconds=int(secs))
			prepared.append(seg_path)
			durations.append(secs)
			used += secs

	if not prepared:
		# final safety
		first_text = (segments[0]["text"].strip() if segments and segments[0].get("text") else "")
		black = tmp_dir / "black.mp4"
		_black_fallback(black, width, height, fps, seconds=int(target_total))
		prepared.append(black)
		durations.append(float(target_total))

	concat_out = tmp_dir / "concat.mp4"
	if len(prepared) == 1:
		try:
			os.replace(prepared[0], concat_out)
		except Exception:
			_ = _reencode_with_ffmpeg(prepared[0], concat_out, width, height, fps)
	else:
		_ = _concat_segments_ffmpeg(prepared, concat_out)

	# Write ASS for the whole video and burn subtitles onto the concatenated video
	srt = _write_srt(tmp_dir, segments[:len(durations)], durations)
	ass = _write_ass(tmp_dir, segments[:len(durations)], durations)
	# Try burning ASS (reliable styling via libass)
	burned = tmp_dir / "concat_subs.mp4"
	try:
		cmd_burn = [
			"ffmpeg", "-y", "-v", "error",
			"-i", str(concat_out),
			"-vf", f"ass={ass.as_posix()}",
			"-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
			str(burned),
		]
		if _run_ffmpeg(cmd_burn):
			concat_for_audio = burned
		else:
			# Try embedding as soft subtitles (mov_text) as a fallback
			soft = tmp_dir / "concat_with_soft_subs.mp4"
			try:
				cmd_soft = [
					"ffmpeg", "-y", "-v", "error",
					"-i", str(concat_out),
					"-i", str(srt),
					"-c:v", "copy", "-c:s", "mov_text",
					str(soft),
				]
				if _run_ffmpeg(cmd_soft):
					concat_for_audio = soft
				else:
					concat_for_audio = concat_out
			except Exception:
				concat_for_audio = concat_out
	except Exception:
		concat_for_audio = concat_out

	# Mux narration audio onto the concatenated (and possibly burned) video
	final_tmp = tmp_dir / "final_with_audio.mp4"
	if not _mux_audio(concat_for_audio, voiceover, final_tmp):
		cmd = [
			"ffmpeg", "-y", "-v", "error",
			"-i", str(concat_for_audio),
			"-i", str(voiceover),
			"-c:v", "libx264", "-c:a", "aac", "-shortest",
			str(final_tmp),
		]
		if not _run_ffmpeg(cmd):
			if concat_out.exists():
				os.replace(concat_out, out_path)
				return out_path
			else:
				raise

	out_path.parent.mkdir(parents=True, exist_ok=True)
	try:
		os.replace(final_tmp, out_path)
	except Exception:
		subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(final_tmp), "-c", "copy", str(out_path)], check=False)

	return out_path
