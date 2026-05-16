// Browser-telephony simulator: AudioWorkletProcessor
//
// Downsamples the AudioContext's native rate (typically 44.1 kHz or 48 kHz)
// to 8 kHz mono, converts Float32 to Int16 little-endian, and posts ArrayBuffer
// chunks of 320 bytes (= 160 samples = 20 ms of audio) to the main thread —
// matching the exact frame cadence the backend's Exotel-protocol bridge expects.
//
// Anti-aliasing: a 3-tap moving average is applied before decimation. This is
// not telephony-grade, but it removes the worst of the aliasing artifacts and
// keeps the implementation small. Real PSTN audio is band-limited at ~3.4 kHz
// anyway, so any additional fidelity here is wasted.

class DownsamplerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 8000;
    this.ratio = sampleRate / this.targetRate; // global in AudioWorkletGlobalScope
    this.accum = 0;
    // 3-tap moving average state (cheap low-pass filter).
    this.history = [0, 0, 0];
    this.outBuffer = []; // Int16 samples awaiting flush
    this.FRAME_SAMPLES = 160; // 20 ms @ 8 kHz
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      // Slide the 3-tap moving average window.
      this.history[0] = this.history[1];
      this.history[1] = this.history[2];
      this.history[2] = channel[i];
      const filtered = (this.history[0] + this.history[1] + this.history[2]) / 3;

      this.accum += 1;
      if (this.accum >= this.ratio) {
        this.accum -= this.ratio;
        // Float32 [-1, 1] -> Int16 [-32768, 32767]
        const clamped = Math.max(-1, Math.min(1, filtered));
        const int16 = clamped < 0
          ? Math.round(clamped * 0x8000)
          : Math.round(clamped * 0x7fff);
        this.outBuffer.push(int16);
      }
    }

    while (this.outBuffer.length >= this.FRAME_SAMPLES) {
      const frame = this.outBuffer.splice(0, this.FRAME_SAMPLES);
      const buf = new ArrayBuffer(frame.length * 2);
      const view = new DataView(buf);
      for (let i = 0; i < frame.length; i++) {
        // Little-endian — matches Exotel L16 wire format.
        view.setInt16(i * 2, frame[i], true);
      }
      // Transferable so we don't double-allocate.
      this.port.postMessage(buf, [buf]);
    }
    return true;
  }
}

registerProcessor('sim-downsampler', DownsamplerProcessor);
