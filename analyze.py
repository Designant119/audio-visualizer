#!/usr/bin/env python3
"""Analyze audio: STFT -> per-video-frame spectral bands + energy + onset, saved as .npz"""
import numpy as np
import subprocess, sys, os

SR = 44100
FPS = 24
WIN = 2048
HOP = 512
N_BANDS = 64

def load_mono(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)

def stft(x):
    n = len(x)
    n_frames = (n - WIN) // HOP + 1
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = x[np.minimum(idx, n - 1)]
    w = np.hanning(WIN)
    S = np.fft.rfft(frames * w, axis=1)
    mag = np.abs(S)
    freqs = np.fft.rfftfreq(WIN, 1 / SR)
    return mag, freqs

def main(audio_path, out_path):
    x = load_mono(audio_path)
    mag, freqs = stft(x)
    n_stft = mag.shape[0]
    total_frames = int(np.ceil(n_stft * HOP / SR * FPS))
    # Band edges over BIN indices (log-spaced), snapped to ints -> every band has >=1 bin
    nbins = mag.shape[1]
    bin_edges = np.unique(np.geomspace(1, nbins, N_BANDS + 1).round().astype(int))
    bin_edges = np.clip(bin_edges, 1, nbins)
    band_idx = np.digitize(np.arange(nbins), bin_edges) - 1
    band_idx = np.clip(band_idx, 0, len(bin_edges) - 2)
    n_bands = len(bin_edges) - 1
    # accumulate magnitude into bands
    bands = np.zeros((n_stft, n_bands), dtype=np.float64)
    rows = np.repeat(np.arange(n_stft)[:, None], nbins, axis=1)
    np.add.at(bands, (rows, np.broadcast_to(band_idx[None, :], (n_stft, nbins))), mag)
    # per-band mean magnitude (normalize by bin count) then dB compression
    counts = np.bincount(band_idx, minlength=n_bands).astype(np.float64)
    band_mean = bands / np.maximum(counts[None, :], 1)
    bands_db = 20 * np.log10(band_mean + 1e-3)
    bands_db = np.clip((bands_db + 20) / 50, 0, 1)
    # per video frame: average over stft frames in window
    def frame_agg(arr):
        n = len(arr)
        out = np.zeros(total_frames, dtype=np.float64)
        cnt = np.zeros(total_frames, dtype=np.float64)
        for i in range(n):
            f = int(i * HOP / SR * FPS)
            if f < total_frames:
                out[f] += arr[i]
                cnt[f] += 1
        return out / np.maximum(cnt, 1)
    band_frames = np.zeros((total_frames, n_bands), dtype=np.float64)
    for b in range(n_bands):
        band_frames[:, b] = frame_agg(bands_db[:, b])
    # overall loudness per frame (linear)
    loud = frame_agg(mag.sum(axis=1))
    loud = loud / np.percentile(loud, 99) if loud.max() > 0 else loud
    # low freq energy (sub 20-120Hz) per frame for pulse
    sub_idx = freqs <= 120
    sub_e = mag[:, sub_idx].sum(axis=1)
    sub_f = frame_agg(sub_e)
    sub_f = sub_f / np.percentile(sub_f, 99) if sub_f.max() > 0 else sub_f
    # onset: positive derivative of loudness, normalized
    onset = np.diff(np.concatenate([[0], loud]))
    onset = np.maximum(onset, 0)
    onset = onset / np.percentile(onset, 98) if onset.max() > 0 else onset
    np.savez(out_path, bands=band_frames.astype(np.float32), loud=loud.astype(np.float32),
             sub=sub_f.astype(np.float32), onset=onset.astype(np.float32))
    print(f"total_frames={total_frames} bands={band_frames.shape} loud range=[{loud.min():.3f},{loud.max():.3f}] "
          f"sub range=[{sub_f.min():.3f},{sub_f.max():.3f}] onset max={onset.max():.3f}")
    print(f"saved -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
