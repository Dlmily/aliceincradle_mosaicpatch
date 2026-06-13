# effects.py (V3) - Integrated CIPIC HRIR + partitioned FFT convolution for realistic HRTF binauralization
import os
import json
import threading
import numpy as np
from scipy import signal
import math
import time

try:
    from scipy.io import loadmat
except Exception:
    loadmat = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    from rich.table import Table
    import readchar
    import pyaudio
except ImportError as e:
    print(f"缺少依赖库: {e}")
    print("请运行: pip install rich readchar pyaudio numpy scipy pydub requests")
    raise

# Default location to store HRIR after download
HRIR_DIR = "hrtf"
HRIR_FILENAME = "cipic_subject_003_hrir.mat"
HRIR_PATH = os.path.join(HRIR_DIR, HRIR_FILENAME)
HRIR_DOWNLOAD_URL = "https://github.com/amini-allight/cipic-hrtf-database/blob/master/standard_hrir_database/subject_003/hrir_final.mat?raw=true"

CONFIG_FILE = "sound_effects_config.json"

PRESET_DATA = {
    "无": (50, 50, 0, 0),
    "ACG": (60, 75, 40, 20),
    "民谣": (45, 60, 20, 10),
    "低音": (85, 40, 30, 20),
    "低音&高音": (80, 80, 40, 30),
    "蓝调": (65, 55, 30, 25),
    "古风": (40, 70, 50, 40),
    "古典": (55, 65, 45, 30),
    "电音": (90, 70, 60, 50),
    "流行": (60, 60, 30, 20),
    "超重低音": (70, 30, 50, 50),
    "原声": (50, 50, 0, 0),
    "空间": (65, 60, 80, 40),
    "环绕": (55, 70, 90, 30),
}

# ============================================================
# Utilities
# ============================================================
def ensure_hrir_downloaded(url=HRIR_DOWNLOAD_URL, target_path=HRIR_PATH):
    if os.path.exists(target_path):
        return target_path
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    print(f"HRIR 文件不存在，正在下载到 {target_path} ...")
    try:
        import requests
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(target_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        print("HRIR 下载完成。")
        return target_path
    except Exception as e:
        print(f"requests 下载失败: {e}，尝试 urllib...")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, target_path)
            print("HRIR 下载完成（urllib）。")
            return target_path
        except Exception as e2:
            raise RuntimeError(f"无法下载 HRIR: {e2}")

def next_pow2(x):
    return 1 << (int(x - 1).bit_length())

# ============================================================
# 2. 分频器模块
# ============================================================
class FrequencySplitter:
    def __init__(self, sr=44100):
        self.sr = sr
        self.crossovers = [150, 800, 4000]
        self.lp_b, self.lp_a = signal.butter(4, self.crossovers[0] / (sr / 2), btype='low')
        self.bp1_b, self.bp1_a = signal.butter(4, [self.crossovers[0] / (sr / 2), 
                                                    self.crossovers[1] / (sr / 2)], btype='band')
        self.bp2_b, self.bp2_a = signal.butter(4, [self.crossovers[1] / (sr / 2), 
                                                    self.crossovers[2] / (sr / 2)], btype='band')
        self.hp_b, self.hp_a = signal.butter(4, self.crossovers[2] / (sr / 2), btype='high')
        self.lp_zi = np.zeros((len(self.lp_b)-1, 2), dtype=np.float32)
        self.bp1_zi = np.zeros((len(self.bp1_b)-1, 2), dtype=np.float32)
        self.bp2_zi = np.zeros((len(self.bp2_b)-1, 2), dtype=np.float32)
        self.hp_zi = np.zeros((len(self.hp_b)-1, 2), dtype=np.float32)
    
    def process(self, data):
        low, self.lp_zi = signal.lfilter(self.lp_b, self.lp_a, data, axis=0, zi=self.lp_zi)
        bp1, self.bp1_zi = signal.lfilter(self.bp1_b, self.bp1_a, data, axis=0, zi=self.bp1_zi)
        bp2, self.bp2_zi = signal.lfilter(self.bp2_b, self.bp2_a, data, axis=0, zi=self.bp2_zi)
        high, self.hp_zi = signal.lfilter(self.hp_b, self.hp_a, data, axis=0, zi=self.hp_zi)
        return {'sub': low, 'low': bp1, 'mid': bp2, 'high': high}
    
    def combine(self, bands):
        return bands['sub'] + bands['low'] + bands['mid'] + bands['high']

# ============================================================
# HRIR Loader for CIPIC .mat (subject files)
# ============================================================
class HRIRLoader:
    def __init__(self, path=None):
        self.path = path or HRIR_PATH
        self.loaded = False
        self.positions = []  # list of (az_rad, el_rad)
        self.hrir_l = None
        self.hrir_r = None
        self.hrir_len = 0

    def load(self, path=None):
        p = path or self.path
        if not os.path.exists(p):
            # try to download
            ensure_hrir_downloaded()
        if loadmat is None:
            raise RuntimeError("scipy.io.loadmat not available")
        mat = loadmat(p)
        # Common keys in CIPIC mirrors: 'hrir_l', 'hrir_r', 'azimuth' and 'elevation' or 'azimuths','elevations'
        if 'hrir_l' not in mat or 'hrir_r' not in mat:
            # some copies use 'hrir_l' under different name, try lower-case keys
            keys = [k.lower() for k in mat.keys()]
            if 'hrir_l' in keys and 'hrir_r' in keys:
                # attempt fallback - but most likely fine
                pass
            else:
                raise RuntimeError("无法在 mat 文件中找到 hrir_l / hrir_r")
        h_l = np.array(mat['hrir_l'])
        h_r = np.array(mat['hrir_r'])
        # CIPIC original shape: (25,50,200) -> elevation x azimuth x samples
        if h_l.ndim == 3:
            el_count, az_count, samples = h_l.shape
            # CIPIC provides 'azimuth' (50) and 'elevation' (25)
            azs = None
            els = None
            for k in ('azimuth','azimuths','azi'):
                if k in mat:
                    azs = np.array(mat[k]).squeeze()
                    break
            for k in ('elevation','elevations','ele'):
                if k in mat:
                    els = np.array(mat[k]).squeeze()
                    break
            # If azs/els not present, generate arrays: az 1..50 mapped to [-80..80], el accordingly
            if azs is None:
                azs = np.linspace(-80, 80, az_count)
            if els is None:
                els = np.linspace(-45, 90, el_count)
            # Create flattened list of positions
            pos_list = []
            lefts = []
            rights = []
            for i_el in range(el_count):
                for j_az in range(az_count):
                    az_deg = float(azs[j_az])
                    el_deg = float(els[i_el])
                    az_rad = math.radians(az_deg)
                    el_rad = math.radians(el_deg)
                    pos_list.append((az_rad, el_rad))
                    lefts.append(h_l[i_el, j_az, :].astype(np.float32))
                    rights.append(h_r[i_el, j_az, :].astype(np.float32))
            self.positions = np.array(pos_list)  # (N,2)
            self.hrir_l = np.stack(lefts, axis=0)  # (N, samples)
            self.hrir_r = np.stack(rights, axis=0)
            self.hrir_len = self.hrir_l.shape[1]
            self.loaded = True
            return
        elif h_l.ndim == 2:
            # Common mirror shape: (Ndirs, samples)
            samples = h_l.shape[1]
            n_dirs = h_l.shape[0]
            # try to find 'azimuth' and 'elevation' arrays
            azs = None
            els = None
            for k in ('azimuth','azimuths'):
                if k in mat:
                    azs = np.array(mat[k]).squeeze()
                    break
            for k in ('elevation','elevations'):
                if k in mat:
                    els = np.array(mat[k]).squeeze()
                    break
            # If azs / els present as grids, try to map
            if azs is not None and els is not None:
                # If azs/els are vectors, assume grid shape
                if azs.size * els.size == n_dirs:
                    pos_list = []
                    lefts = []
                    rights = []
                    for i_el in range(els.size):
                        for j_az in range(azs.size):
                            idx = i_el * azs.size + j_az
                            az_rad = math.radians(float(azs[j_az]))
                            el_rad = math.radians(float(els[i_el]))
                            pos_list.append((az_rad, el_rad))
                            lefts.append(h_l[idx, :].astype(np.float32))
                            rights.append(h_r[idx, :].astype(np.float32))
                    self.positions = np.array(pos_list)
                    self.hrir_l = np.stack(lefts, axis=0)
                    self.hrir_r = np.stack(rights, axis=0)
                    self.hrir_len = self.hrir_l.shape[1]
                    self.loaded = True
                    return
            # If we can't deduce layout, assume entries are direction-ordered and create dummy positions on circle
            pos_list = []
            lefts = []
            rights = []
            for i in range(n_dirs):
                az_deg = -180.0 + (360.0 * i / n_dirs)
                az_rad = math.radians(az_deg)
                el_rad = 0.0
                pos_list.append((az_rad, el_rad))
                lefts.append(h_l[i, :].astype(np.float32))
                rights.append(h_r[i, :].astype(np.float32))
            self.positions = np.array(pos_list)
            self.hrir_l = np.stack(lefts, axis=0)
            self.hrir_r = np.stack(rights, axis=0)
            self.hrir_len = self.hrir_l.shape[1]
            self.loaded = True
            return
        else:
            raise RuntimeError("无法解析的 HRIR 形状: %s" % (h_l.shape,))

    def nearest_hrir(self, az_rad, el_rad):
        if not self.loaded:
            self.load()
        # compute great-circle-like distance by converting az/el to cartesian unit vector
        az = az_rad
        el = el_rad
        # convert degrees: angles are in radians already
        x = math.cos(el) * math.cos(az)
        y = math.cos(el) * math.sin(az)
        z = math.sin(el)
        v = np.array([x, y, z])
        pos = self.positions  # (N,2)
        # convert all to vectors
        azs = pos[:, 0]
        els = pos[:, 1]
        xs = np.cos(els) * np.cos(azs)
        ys = np.cos(els) * np.sin(azs)
        zs = np.sin(els)
        vecs = np.stack([xs, ys, zs], axis=1)
        dots = vecs @ v
        idx = int(np.argmax(dots))
        return self.hrir_l[idx], self.hrir_r[idx]

# ============================================================
# Partitioned (block) FFT Convolver (simple overlap-add per HRIR)
# ============================================================
class PartitionedConvolver:
    def __init__(self, hrir, block_size):
        """
        hrir: 1D numpy array
        block_size: incoming block size (samples)
        """
        self.hrir = np.asarray(hrir, dtype=np.float32)
        self.hlen = len(self.hrir)
        self.block = block_size
        self.nfft = next_pow2(self.block + self.hlen - 1)
        # Precompute HRIR FFT (zero-padded)
        self.H = np.fft.rfft(self.hrir, self.nfft)
        self.overlap = np.zeros(self.hlen - 1, dtype=np.float32)

    def reset_hrir(self, new_hrir):
        self.hrir = np.asarray(new_hrir, dtype=np.float32)
        self.hlen = len(self.hrir)
        self.nfft = next_pow2(self.block + self.hlen - 1)
        self.H = np.fft.rfft(self.hrir, self.nfft)
        self.overlap = np.zeros(self.hlen - 1, dtype=np.float32)

    def process_block(self, block):
        """
        block: 1D numpy array length == self.block
        returns: 1D numpy array length == self.block (streaming overlap-add)
        """
        x = np.asarray(block, dtype=np.float32)
        if len(x) != self.block:
            # pad or trim
            if len(x) < self.block:
                x = np.pad(x, (0, self.block - len(x)))
            else:
                x = x[:self.block]
        X = np.fft.rfft(x, self.nfft)
        Y = X * self.H
        y = np.fft.irfft(Y, self.nfft).astype(np.float32)
        # y length is nfft, the valid convolution output for this block-stream is:
        out = y[:self.block] + self.overlap[:self.block] if len(self.overlap) >= self.block else y[:self.block] + np.pad(self.overlap, (0, self.block - len(self.overlap)))
        # update overlap: tail of y beyond this block
        new_overlap = y[self.block:self.block + self.hlen - 1]
        # rotate/replace overlap buffer
        # if overlap length > new_overlap len, keep only corresponding portion
        if len(self.overlap) == len(new_overlap):
            self.overlap = new_overlap.copy()
        else:
            # resize
            self.overlap = np.zeros(len(new_overlap), dtype=np.float32)
            self.overlap[:] = new_overlap
        return out

# ============================================================
# 3. Enhanced Early Reflections (kept similar but tuned)
# ============================================================
class EnhancedEarlyReflections:
    def __init__(self, sr=44100):
        self.sr = sr
        self.reflections = [
            (5.0, 0.65),
            (12.0, 0.45),
            (25.0, 0.30),
            (45.0, 0.15)
        ]
        self.max_delay = int(0.25 * sr)
        self.delay_buf = np.zeros(self.max_delay, dtype=np.float32)
        self.delay_pos = 0
    
    def process(self, data, room_size=0.5):
        if room_size < 0.01:
            return data.copy()
        out = data.copy()
        n = len(data)
        scale = 0.6 + room_size * 0.6
        mix_factor = 0.6 + room_size * 0.4
        for i in range(n):
            for ch in range(2):
                sample = data[i, ch]
                refl_sum = 0.0
                for delay_ms, gain in self.reflections:
                    delay_samples = int(delay_ms * self.sr / 1000.0 * scale)
                    if 0 < delay_samples < self.max_delay:
                        idx = (self.delay_pos - delay_samples) % self.max_delay
                        refl_sum += self.delay_buf[idx] * gain * (0.4 + room_size * 0.6)
                self.delay_buf[self.delay_pos] = sample
                self.delay_pos = (self.delay_pos + 1) % self.max_delay
                out[i, ch] = sample + refl_sum * mix_factor
        return out

# ============================================================
# 4. Echoes (multi-tap stereo) - tuned
# ============================================================
class EchoesProcessor:
    def __init__(self, sr=44100):
        self.sr = sr
        delay_secs = [0.30, 0.45, 0.22, 0.35]
        self.delays = [int(s * sr) for s in delay_secs]
        self.feedback = 0.6
        self.dry_wet = 0.9
        self.bufs = [np.zeros((d + 1, 2), dtype=np.float32) for d in self.delays]
        self.pos = [0] * len(self.delays)
    
    def process(self, data):
        n = len(data)
        out = data.copy()
        for i in range(n):
            for d_idx, delay in enumerate(self.delays):
                pos = self.pos[d_idx]
                buf = self.bufs[d_idx]
                read_pos = (pos - delay) % (delay + 1)
                delayed = buf[read_pos]
                buf[pos, 0] = data[i, 0] + delayed[0] * self.feedback
                buf[pos, 1] = data[i, 1] + delayed[1] * self.feedback
                self.pos[d_idx] = (pos + 1) % (delay + 1)
                pan = math.sin((d_idx + 1) * 0.5) * 0.3
                left_gain = 0.5 + 0.5 * (1 - pan)
                right_gain = 0.5 + 0.5 * (1 + pan)
                out[i, 0] += delayed[0] * self.dry_wet * left_gain
                out[i, 1] += delayed[1] * self.dry_wet * right_gain
        return out * 0.98

# ============================================================
# 5. Dattorro Reverb (tuned)
# ============================================================
class DattorroReverb:
    def __init__(self, sr=44100):
        self.sr = sr
        self.comb_delays_ms = [29.7, 37.1, 41.1, 43.7]
        self.comb_delays = [int(round(d_ms * sr / 1000.0)) for d_ms in self.comb_delays_ms]
        self.comb_bufs = [np.zeros(d + 1, dtype=np.float32) for d in self.comb_delays]
        self.comb_pos = [0] * len(self.comb_delays)
        self.comb_filters = [0.0] * len(self.comb_delays)
        self.ap_delays_ms = [5.0, 1.7]
        self.ap_delays = [int(round(d_ms * sr / 1000.0)) for d_ms in self.ap_delays_ms]
        self.ap_bufs = [np.zeros(d + 1, dtype=np.float32) for d in self.ap_delays]
        self.ap_pos = [0] * len(self.ap_delays)
        self.mod_freq = 0.2
        self.mod_depth = 10
        self.max_predelay = int(0.5 * sr)
        self.predelay_buf = np.zeros(self.max_predelay, dtype=np.float32)
        self.predelay_pos = 0
        self.mod_delay_buf = np.zeros(int(0.08 * sr), dtype=np.float32)
        self.mod_delay_pos = 0
    
    def process(self, data, wet, decay_time, damping, predelay_ms=0.0, diffusion=0.65, mod_amount=0.5):
        if wet <= 0.01:
            return data.copy()
        out = data.copy()
        n = len(data)
        predelay_samples = min(int(predelay_ms * self.sr / 1000.0), self.max_predelay - 1)
        diffusion = np.clip(diffusion, 0.3, 0.98)
        mod_phase = 0.0
        mod_step = 2 * np.pi * self.mod_freq / self.sr
        lp_a = 0.1 + damping * 0.6
        
        for i in range(n):
            for ch in range(2):
                if predelay_samples > 0:
                    self.predelay_buf[self.predelay_pos] = data[i, ch]
                    delayed_inp = self.predelay_buf[(self.predelay_pos - predelay_samples) % self.max_predelay]
                    self.predelay_pos = (self.predelay_pos + 1) % self.max_predelay
                else:
                    delayed_inp = data[i, ch]
                reverb = 0.0
                for c_idx, delay in enumerate(self.comb_delays):
                    pos = self.comb_pos[c_idx]
                    delayed = self.comb_bufs[c_idx][(pos - delay) % (delay + 1)]
                    filtered = self.comb_filters[c_idx] * lp_a + delayed * (1.0 - lp_a)
                    self.comb_filters[c_idx] = filtered
                    fb = 10 ** (-3.0 * delay / (decay_time * self.sr + 1e-8))
                    self.comb_bufs[c_idx][pos] = delayed_inp + filtered * fb * 0.92
                    reverb += filtered
                    self.comb_pos[c_idx] = (pos + 1) % (delay + 1)
                reverb /= len(self.comb_delays)
                for a_idx, delay in enumerate(self.ap_delays):
                    pos = self.ap_pos[a_idx]
                    delayed = self.ap_bufs[a_idx][(pos - delay) % (delay + 1)]
                    ap_out = -diffusion * reverb + delayed
                    self.ap_bufs[a_idx][pos] = reverb + ap_out * diffusion
                    reverb = ap_out
                    self.ap_pos[a_idx] = (pos + 1) % (delay + 1)
                mod_delay = int(mod_amount * self.mod_depth * (0.5 + 0.5 * np.sin(mod_phase)))
                if ch == 1:
                    mod_delay = int(mod_amount * self.mod_depth * (0.5 + 0.5 * np.cos(mod_phase)))
                if mod_delay > 0:
                    delayed_mod = self.mod_delay_buf[(self.mod_delay_pos - mod_delay) % len(self.mod_delay_buf)]
                    self.mod_delay_buf[self.mod_delay_pos] = reverb
                    self.mod_delay_pos = (self.mod_delay_pos + 1) % len(self.mod_delay_buf)
                    reverb = reverb * 0.7 + delayed_mod * 0.3
                dry_gain = np.sqrt(1.0 - wet)
                wet_gain = np.sqrt(wet)
                out[i, ch] = data[i, ch] * dry_gain + reverb * wet_gain
            mod_phase += mod_step
            if mod_phase >= 2 * np.pi:
                mod_phase -= 2 * np.pi
        return np.clip(out, -0.99, 0.99)

# ============================================================
# 6. FullSpatialController - now uses HRIR-based convolution for mid/high
# ============================================================
class FullSpatialController:
    def __init__(self, sr=44100, block_size=2048):
        self.sr = sr
        self.block_size = block_size
        self.head_radius_cm = 8.5
        self.sound_speed = 34300
        self.distance = 0.0
        self.width = 1.0
        self.rotation_speed = 0.0
        self.rotation_angle = 0.0
        self.splitter = FrequencySplitter(sr)
        self.hp_far_zi = None
        self.perceptual_factor_side = 1.6
        self.hrir_loader = HRIRLoader()
        # try to lazy load HRIR only when first used
        self.hrir_left_conv = None
        self.hrir_right_conv = None
        self.current_hrir_idx = None

    def set_parameters(self, distance, width, rotation_speed):
        self.distance = np.clip(distance, 0.0, 2.0)
        self.width = np.clip(width, 0.0, 1.5)
        self.rotation_speed = rotation_speed

    def _ensure_hrir_for_angle(self, az_rad, el_rad=0.0):
        if not self.hrir_loader.loaded:
            try:
                self.hrir_loader.load()
            except Exception as e:
                print(f"HRIR 加载失败: {e}，回退到内置 binaural 模型（效果较弱）。")
                return False
        l, r = self.hrir_loader.nearest_hrir(az_rad, el_rad)
        # find idx by searching for equality (we can compare first sample)
        # simpler: always re-create convolvers when HRIR changes
        # create or reset convolvers
        if (self.hrir_left_conv is None) or (self.hrir_right_conv is None):
            self.hrir_left_conv = PartitionedConvolver(l, self.block_size)
            self.hrir_right_conv = PartitionedConvolver(r, self.block_size)
            self.current_hrir_idx = True
        else:
            # if HRIR length differs or content differs, reset
            if len(l) != self.hrir_left_conv.hlen:
                self.hrir_left_conv.reset_hrir(l)
                self.hrir_right_conv.reset_hrir(r)
        return True

    def _apply_distance_gain(self, data):
        gain = 1.0 / (1.0 + self.distance * 1.2)
        cutoff = 20000 * (1.0 - min(self.distance, 1.0) * 0.85)
        cutoff = max(1000, cutoff)
        b, a = signal.butter(2, cutoff / (self.sr / 2), btype='low')
        if self.hp_far_zi is None or self.hp_far_zi.shape[0] != len(b)-1:
            self.hp_far_zi = np.zeros((len(b)-1, 2), dtype=np.float32)
        filtered, self.hp_far_zi = signal.lfilter(b, a, data, axis=0, zi=self.hp_far_zi)
        return filtered * gain

    def _apply_width(self, data):
        left, right = data[:, 0], data[:, 1]
        mid = (left + right) / 2.0
        side = (left - right) / 2.0
        side_gain = 1.0 + min(self.width, 1.5) * 3.0
        new_left = mid + side * side_gain
        new_right = mid - side * side_gain
        return np.stack([new_left, new_right], axis=1)

    def _apply_hrir_binaural(self, stereo_block, az_rad):
        """
        stereo_block: (n,2) array -> convert to mono and convolve with HRIR (left/right)
        """
        mono = (stereo_block[:, 0] + stereo_block[:, 1]) * 0.5
        # ensure HRIR convolvers ready
        ok = self._ensure_hrir_for_angle(az_rad, 0.0)
        if not ok:
            # fallback simple panning
            pan = 0.5 + 0.5 * math.sin(az_rad)
            left = mono * (1.0 - pan * 0.5)
            right = mono * (0.5 + pan * 0.5)
            return np.stack([left, right], axis=1)
        # process in blocks of self.block_size (mono length may equal block_size)
        n = len(mono)
        outL = np.zeros(n, dtype=np.float32)
        outR = np.zeros(n, dtype=np.float32)
        # Because our PartitionedConvolver keeps overlap internally, just call for the full block
        # If input n differs from block_size, chunk it
        pos = 0
        while pos < n:
            blk = mono[pos:pos + self.block_size]
            if len(blk) < self.block_size:
                blk = np.pad(blk, (0, self.block_size - len(blk)))
            yL = self.hrir_left_conv.process_block(blk)
            yR = self.hrir_right_conv.process_block(blk)
            take = min(n - pos, self.block_size)
            outL[pos:pos + take] = yL[:take]
            outR[pos:pos + take] = yR[:take]
            pos += take
        return np.stack([outL, outR], axis=1)

    def _apply_rotation(self, data):
        """
        rotation implemented as HRTF convolution with angle that varies over the block
        """
        n = len(data)
        left, right = data[:, 0], data[:, 1]
        mid = (left + right) / 2.0
        max_rot_per_s = 1.0
        rot_per_s = min(self.rotation_speed, 1.5) * max_rot_per_s
        t = np.arange(n) / self.sr
        angles = self.rotation_angle + 2.0 * np.pi * rot_per_s * t
        # Use mean angle over block for HRIR selection
        mean_angle = float(np.mean(angles))
        # Normalize to -pi..pi
        mean_angle = (mean_angle + np.pi) % (2.0 * np.pi) - np.pi
        # Apply width: mix some side into mono to increase perceived width before HRIR
        if self.width > 0.01:
            side = (left - right) / 2.0
            mid = mid + side * (self.width * 0.5)
        stereo = self._apply_hrir_binaural(np.stack([mid, mid], axis=1), mean_angle)
        # update rotation_angle for next block
        self.rotation_angle += 2.0 * np.pi * rot_per_s * (n / self.sr)
        self.rotation_angle = (self.rotation_angle + 2.0 * np.pi) % (2 * np.pi)
        return stereo

    def _frequency_dependent_spatial(self, data):
        bands = self.splitter.process(data)
        if self.width > 0.01 or self.rotation_speed > 0.01:
            mid = bands['mid']
            high = bands['high']
            mid_wide = self._apply_width(mid) * (1.0 + min(self.width,1.0)*0.3)
            high_wide = self._apply_width(high) * (1.0 + min(self.width,1.0)*0.6)
            bands['mid'] = self._apply_rotation(mid_wide)
            bands['high'] = self._apply_rotation(high_wide)
        if self.width > 0.3:
            bands['low'] = self._apply_width(bands['low']) * 0.5
        return self.splitter.combine(bands)

    def process(self, data, distance, width, rotation_speed):
        if distance <= 0.01 and width <= 0.01 and rotation_speed <= 0.01:
            return data.copy()
        self.set_parameters(distance, width, rotation_speed)
        stage1 = self._apply_distance_gain(data)
        stage2 = self._frequency_dependent_spatial(stage1)
        if self.width > 0.7:
            stage2 = self._apply_width(stage2) * 0.8
        return np.clip(stage2, -0.99, 0.99)

# ============================================================
# 7. UltimateAudioEngine
# ============================================================
class UltimateAudioEngine:
    def __init__(self, sr=44100, block_size=2048):
        self.sr = sr
        self.lock = threading.Lock()
        self.settings = {
            "低音": 50, "高音": 50,
            "环绕强度": 0, "环绕深度": 0,
            "环境": "大厅", "环境强度": 100
        }
        self.splitter = FrequencySplitter(sr)
        self.early_reflections = EnhancedEarlyReflections(sr)
        self.echoes = EchoesProcessor(sr)
        self.reverb = DattorroReverb(sr)
        self.spatial = FullSpatialController(sr, block_size=block_size)
        
        self.env_presets = {
            "无":        (0.00, 0.5,  0.50, 0.0,   0.50, 0.0),
            "大厅":      (0.99, 18.0, 0.48, 180.0, 0.96, 0.9),
            "房间":      (0.95, 10.0, 0.52, 100.0, 0.90, 0.8),
            "教室":      (0.96, 12.0, 0.50, 120.0, 0.92, 0.8),
            "声乐板":    (0.98, 15.0, 0.45, 200.0, 0.98, 0.9),
            "弹簧":      (0.92, 8.0,  0.55, 80.0,  0.88, 0.7),
            "夜店":      (0.97, 14.0, 0.48, 150.0, 0.94, 0.9),
            "浴室":      (0.96, 11.0, 0.50, 160.0, 0.96, 0.9),
            "地下通道":  (0.99, 20.0, 0.42, 220.0, 0.92, 0.8),
            "演唱会":    (0.99, 16.0, 0.48, 180.0, 0.95, 0.9),
            "音乐厅":    (1.00, 22.0, 0.45, 200.0, 0.98, 0.9),
        }
        self._init_eq_filters()
        self._init_filter_states()
        self.hp_zi = None
    
    def _init_eq_filters(self):
        self.bass_shelf = self._create_shelf_filter(100, gain_db=0, Q=0.7, shelf_type='low')
        self.treble_shelf = self._create_shelf_filter(4000, gain_db=0, Q=0.7, shelf_type='high')
        self.dehum = self._create_shelf_filter(300, gain_db=-3.0, Q=0.7, shelf_type='low')
        self.band_eq = {
            'sub': self._create_peak_filter(60, gain_db=0, Q=1.2),
            'low': self._create_peak_filter(300, gain_db=0, Q=1.0),
            'mid': self._create_peak_filter(2000, gain_db=0, Q=1.0),
            'high': self._create_peak_filter(6000, gain_db=0, Q=1.2)
        }
    
    def _create_shelf_filter(self, fc, gain_db, Q=0.707, shelf_type='low'):
        A = 10**(gain_db / 40)
        omega = 2 * np.pi * fc / self.sr
        sn, cs = np.sin(omega), np.cos(omega)
        alpha = sn / (2 * Q)
        if shelf_type == 'low':
            b0 = A * ((A + 1) - (A - 1) * cs + 2 * np.sqrt(A) * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cs)
            b2 = A * ((A + 1) - (A - 1) * cs - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) + (A - 1) * cs + 2 * np.sqrt(A) * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cs)
            a2 = (A + 1) + (A - 1) * cs - 2 * np.sqrt(A) * alpha
            a2 = a2
  ipped_due_to_length...