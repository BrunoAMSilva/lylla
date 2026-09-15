#include "../vader_dsp.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

void require(bool pass, const char* message) {
  if (!pass) { std::fprintf(stderr, "FAIL: %s\n", message); std::exit(1); }
}

void testPitch(float hz, float ratio) {
  vader::PitchShifter pitch;
  pitch.setRatio(ratio);
  unsigned crossings = 0, n = 0;
  float last = 0, peak = 0;
  double power = 0, windowPower = 0;
  float minRms = 1, maxRms = 0;
  for (unsigned i = 0; i < 5 * 44100; ++i) {
    const float in = 0.4f * std::sin(2 * vader::kPi * hz * i / vader::SAMPLE_RATE);
    const float out = pitch.tick(in);
    require(std::isfinite(out), "pitch output must be finite");
    if (i >= 44100) {
      if (last <= 0 && out > 0) ++crossings;
      peak = std::fmax(peak, std::fabs(out));
      power += out * out;
      windowPower += out * out;
      if (++n % 441 == 0) {
        const float rms = std::sqrt(windowPower / 441);
        minRms = std::fmin(minRms, rms); maxRms = std::fmax(maxRms, rms);
        windowPower = 0;
      }
    }
    last = out;
  }
  const float measured = crossings / 4.0f;
  std::printf("pitch %.0f Hz x %.2f -> %.2f Hz; RMS %.3f; 10 ms RMS %.3f..%.3f\n",
              hz, ratio, measured, std::sqrt(power / n), minRms, maxRms);
  require(std::fabs(measured - hz * ratio) < 2.0f, "pitch error exceeds 2 Hz");
  require(minRms > 0.15f, "a sustained vowel must not drop into periodic holes");
  require(peak <= 0.4001f, "crossfade must not amplify the source");
}

void testSilenceAndGate() {
  vader::Processor voice;
  voice.setMode(vader::Mode::Voice);
  for (unsigned i = 0; i < 44100; ++i)
    require(std::fabs(voice.tick(0)) < 1e-7f, "voice mode must be silent without input");
  bool opened = false;
  for (unsigned i = 0; i < 22050; ++i) {
    voice.tick(0.03f * std::sin(2 * vader::kPi * 180 * i / 44100));
    opened = opened || voice.meters().gateOpen;
  }
  require(opened, "normal speech level must open the gate");
  float tail = 0;
  for (unsigned i = 0; i < 44100; ++i) {
    const float y = voice.tick(0);
    if (i > 40000) tail = std::fmax(tail, std::fabs(y));
  }
  require(!voice.meters().gateOpen && tail < 1e-5f, "gate must close after speech");
  std::puts("silence, gate opening and release: PASS");
}

void testBreathAndClick() {
  vader::Breathing withClick, withoutClick;
  double clickPower = 0, inhale = 0, exhale = 0, pause = 0;
  for (unsigned i = 0; i < 180000; ++i) {
    const float a = withClick.tick(1), b = withoutClick.tick(0);
    const double difference = a - b;
    if (i < 4000) clickPower += difference * difference;
    if (i > 10000 && i < 40000) inhale += a * a;
    if (i > 100000 && i < 130000) exhale += a * a;
    if (i > 70000 && i < 80000) pause += a * a;
  }
  require(clickPower > 0.01, "valve click must be audible and independent of airflow");
  require(inhale > 1 && exhale > 1, "both breathing phases must sound without a microphone");
  require(pause < 0.0001, "breath must have a quiet pause between phases");
  std::printf("breath: inhale RMS %.3f, exhale RMS %.3f, valve energy %.3f; PASS\n",
              std::sqrt(inhale / 30000), std::sqrt(exhale / 30000), clickPower);
}

void testOverloadAndSwitching() {
  vader::Tuning tuning;
  tuning.master = 1;
  tuning.voice = 4;
  tuning.breath = 4;
  vader::Processor processor(tuning);
  vader::Noise noise;
  float peak = 0;
  for (unsigned i = 0; i < 44100 * 30; ++i) {
    if (i % 10003 == 0) processor.setChild((i / 10003) & 1);
    if (i % 44100 == 0) processor.setMode(static_cast<vader::Mode>((i / 44100) % 4));
    const float mic = i < 44100 ? 0.7f : noise.tick();
    const float y = processor.tick(mic);
    require(std::isfinite(y), "DC, overload and switching must not produce NaN");
    peak = std::fmax(peak, std::fabs(y));
  }
  require(peak > 0.3f && peak <= 0.88001f, "output limiter must bound overloaded mixes");
  processor.setMode(vader::Mode::Calibration);
  float tail = 0;
  for (unsigned i = 0; i < 44100; ++i) {
    const float y = processor.tick(noise.tick());
    if (i > 40000) tail = std::fmax(tail, std::fabs(y));
  }
  require(tail < 1e-6f, "calibration must mute both voice and breath");
  std::printf("30 s overload, DC, preset/mode changes, mute: PASS; peak %.3f\n", peak);
}

void testSampleLoop() {
  const int16_t pcm[] = {0, 1000, 2000, 1000};
  const int16_t expected[] = {0, 500, 1000, 1500, 2000, 1500, 1000, 500};
  vader::Breathing breath;
  breath.useSample(pcm, 4);
  for (unsigned i = 0; i < 800; ++i)
    require(std::fabs(breath.tick(1) * 32768 - expected[i % 8]) < 0.01f,
            "22050 Hz flash samples must interpolate and wrap correctly");
  std::puts("flash sample interpolation and loop: PASS");
}

int main() {
  for (float hz : {70.0f, 90.0f, 160.0f, 260.0f, 380.0f})
    for (float ratio : {0.55f, 0.64f, 0.80f, 1.0f}) testPitch(hz, ratio);
  testSilenceAndGate();
  testBreathAndClick();
  testOverloadAndSwitching();
  testSampleLoop();
  std::puts("All DSP checks passed.");
}
