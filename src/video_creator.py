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
		"fontsize=48",
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
	if not assets:
		# if no assets, use black clips per line
		for i in range(num_lines):
			if used >= target_total - 0.01:
				break
			textfile = _write_overlay_text(tmp_dir, i, (segments[i].get("text") or ""))
			seg_path = tmp_dir / f"seg_{i}.mp4"
			secs = min(per_line, target_total - used)
			_black_fallback(seg_path, width, height, fps, seconds=int(secs), overlay_textfile=textfile)
			prepared.append(seg_path)
			used += secs
	else:
		for i in range(num_lines):
			if used >= target_total - 0.01:
				break
			asset = assets[i % len(assets)]
			text = (segments[i].get("text") or "")
			textfile = _write_overlay_text(tmp_dir, i, text)
			seg_path = tmp_dir / f"seg_{i}.mp4"
			secs = min(per_line, target_total - used)
			if asset.suffix.lower() == ".mp4":
				_ok = _reencode_with_ffmpeg(asset, seg_path, width, height, fps, max_seconds=secs, overlay_textfile=textfile)
				if not _ok:
					# fallback to black if this asset fails
					_black_fallback(seg_path, width, height, fps, seconds=int(secs), overlay_textfile=textfile)
			else:
				_ok = _image_to_video(asset, seg_path, width, height, fps, seconds=int(secs), overlay_textfile=textfile)
				if not _ok:
					_black_fallback(seg_path, width, height, fps, seconds=int(secs), overlay_textfile=textfile)
			prepared.append(seg_path)
			used += secs

	if not prepared:
		# final safety
		first_text = (segments[0]["text"].strip() if segments and segments[0].get("text") else "")
		textfile = _write_overlay_text(tmp_dir, 0, first_text)
		black = tmp_dir / "black.mp4"
		_black_fallback(black, width, height, fps, seconds=int(target_total), overlay_textfile=textfile)
		prepared.append(black)

	concat_out = tmp_dir / "concat.mp4"
	if len(prepared) == 1:
		try:
			os.replace(prepared[0], concat_out)
		except Exception:
			_ = _reencode_with_ffmpeg(prepared[0], concat_out, width, height, fps)
	else:
		_ = _concat_segments_ffmpeg(prepared, concat_out)

	# Mux narration audio onto the concatenated video
	final_tmp = tmp_dir / "final_with_audio.mp4"
	if not _mux_audio(concat_out, voiceover, final_tmp):
		cmd = [
			"ffmpeg", "-y", "-v", "error",
			"-i", str(concat_out),
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
