#pragma once

#include <cmath>
#include <cstdint>

// O renderizador no computador e o Teensy executam este mesmo código.
namespace vader {

constexpr float SAMPLE_RATE = 44100.0f;
constexpr float kPi = 3.14159265358979323846f;

struct Tuning {
  // Ajustar primeiro com o modo 'c' do monitor série, enquanto se fala.
  float referenceRms = 0.020f;
  float adultPitch = 0.80f;       // -3,9 semitons
  float childPitch = 0.64f;       // -7,7 semitons
  float master = 0.65f;
  float voice = 1.0f;
  float breath = 0.85f;
  float valve = 1.0f;
  float consonants = 0.55f;
  float gateOpen = 0.22f;         // Fração de referenceRms.
  float gateClose = 0.11f;
  float breathUnderVoice = 0.32f;
};

enum class Mode { Full, Voice, Breath, Calibration };

inline float clamp(float x, float lo, float hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

inline float smooth(float x) {
  x = clamp(x, 0.0f, 1.0f);
  return x * x * (3.0f - 2.0f * x);
}

inline float coefficient(float ms) {
  return 1.0f - std::exp(-1000.0f / (ms * SAMPLE_RATE));
}

// Saturação suave, simétrica e limitada. Não cria um offset de corrente contínua.
inline float saturate(float x) {
  x = clamp(x, -3.0f, 3.0f);
  return x * (27.0f + x * x) / (27.0f + 9.0f * x * x);
}

class Biquad {
 public:
  enum Kind { Lowpass, Highpass, Bandpass, Peak };

  void set(Kind kind, float hz, float q = 0.7071f, float db = 0.0f) {
    const double w = 2.0 * kPi * hz / SAMPLE_RATE;
    const double c = std::cos(w), a = std::sin(w) / (2.0 * q);
    const double gain = std::pow(10.0, db / 40.0);
    double b0, b1, b2, a0 = 1 + a, a1 = -2 * c, a2 = 1 - a;
    if (kind == Lowpass) {
      b0 = b2 = (1 - c) / 2; b1 = 1 - c;
    } else if (kind == Highpass) {
      b0 = b2 = (1 + c) / 2; b1 = -1 - c;
    } else if (kind == Bandpass) {
      b0 = a; b1 = 0; b2 = -a;
    } else {
      b0 = 1 + a * gain; b1 = -2 * c; b2 = 1 - a * gain;
      a0 = 1 + a / gain; a2 = 1 - a / gain;
    }
    b0_ = b0 / a0; b1_ = b1 / a0; b2_ = b2 / a0;
    a1_ = a1 / a0; a2_ = a2 / a0;
  }

  float tick(float x) {
    const float y = b0_ * x + z1_;
    z1_ = b1_ * x - a1_ * y + z2_;
    z2_ = b2_ * x - a2_ * y;
    return y;
  }

 private:
  float b0_ = 1, b1_ = 0, b2_ = 0, a1_ = 0, a2_ = 0;
  float z1_ = 0, z2_ = 0;
};

template <unsigned Size> class Delay {
 public:
  static_assert((Size & (Size - 1)) == 0, "Delay size must be a power of two");

  void push(float x) {
    data_[position_] = x;
    position_ = (position_ + 1) & (Size - 1);
  }

  float read(unsigned samples) const {
    return data_[(position_ - 1 - samples) & (Size - 1)];
  }

  float readFractional(float samples) const {
    const unsigned n = static_cast<unsigned>(samples);
    const float fraction = samples - n;
    return read(n) * (1 - fraction) + read(n + 1) * fraction;
  }

 private:
  float data_[Size] = {};
  unsigned position_ = 0;
};

// Duas cabeças com interpolação. A cabeça muda apenas durante uma transição
// de 8 ms. A correlação alinha a onda na emenda para reduzir o tremolo nas vogais.
class PitchShifter {
 public:
  void setRatio(float ratio) { targetRatio_ = clamp(ratio, 0.55f, 1.0f); }

  float tick(float x) {
    delay_.push(x);
    ratio_ += (targetRatio_ - ratio_) * 0.0008f;
    const float step = 1.0f - ratio_;
    oldDelay_ += step;
    if (fade_ < 0 && oldDelay_ >= 1764.0f) {
      newDelay_ = findSplice();
      fade_ = 0;
    }
    float y = delay_.readFractional(oldDelay_);
    if (fade_ >= 0) {
      newDelay_ += step;
      const float mix = smooth(static_cast<float>(fade_) / FADE_SAMPLES);
      y += mix * (delay_.readFractional(newDelay_) - y);
      if (++fade_ > FADE_SAMPLES) {
        oldDelay_ = newDelay_;
        fade_ = -1;
      }
    }
    return y;
  }

 private:
  float findSplice() const {
    const unsigned old = static_cast<unsigned>(oldDelay_);
    float energy = 0;
    for (unsigned k = 0; k < 192; k += 4) {
      const float x = delay_.read(old + k);
      energy += x * x;
    }
    if (energy < 0.00001f) return 400.0f;
    float bestScore = -1.0f;
    unsigned best = 400;
    // 5 a 20 ms de história. Inclui um período de uma voz de 70 Hz.
    for (unsigned candidate = 220; candidate <= 880; candidate += 4) {
      float cross = 0, candidateEnergy = 0.0000001f;
      for (unsigned k = 0; k < 192; k += 4) {
        const float y = delay_.read(candidate + k);
        cross += delay_.read(old + k) * y;
        candidateEnergy += y * y;
      }
      const float score = cross > 0 ? cross * cross / candidateEnergy : -1;
      if (score > bestScore) { bestScore = score; best = candidate; }
    }
    return static_cast<float>(best);
  }

  static constexpr int FADE_SAMPLES = 353;
  Delay<4096> delay_;
  float oldDelay_ = 900, newDelay_ = 400;
  float ratio_ = 0.80f, targetRatio_ = 0.80f;
  int fade_ = -1;
};

class Noise {
 public:
  float tick() {
    state_ ^= state_ << 13;
    state_ ^= state_ >> 17;
    state_ ^= state_ << 5;
    return static_cast<float>(state_ >> 8) * (2.0f / 16777216.0f) - 1.0f;
  }
 private:
  uint32_t state_ = 0x6d2b79f5;
};

// Cada válvula combina um estalido amortecido com uma fuga curta de ar.
// O segundo contacto chega 13 ms depois do primeiro.
class Valve {
 public:
  Valve() {
    air_.set(Biquad::Bandpass, 2200, 0.9f);
    body_.set(Biquad::Bandpass, 820, 2.8f);
  }

  void trigger(float strength) { age_ = 0; strength_ = strength; }

  float tick(float noise) {
    float impulse = 0;
    if (age_ == 0) impulse = 1.0f;
    if (age_ == 573) impulse = -0.48f;
    const float puff = smooth(age_ / 45.0f)
                     * (1 - smooth((age_ - 90.0f) / 1700.0f));
    const float sound = 1.9f * body_.tick(impulse)
                      + 0.20f * air_.tick(noise * puff);
    if (age_ < 10000) ++age_;
    return strength_ * sound;
  }

 private:
  Biquad air_, body_;
  unsigned age_ = 10000;
  float strength_ = 0;
};

class Breathing {
 public:
  Breathing() {
    inhaleBody_.set(Biquad::Bandpass, 430, 1.8f);
    inhaleRasp_.set(Biquad::Bandpass, 1180, 2.3f);
    inhaleAir_.set(Biquad::Bandpass, 2850, 0.85f);
    exhaleBody_.set(Biquad::Bandpass, 310, 1.4f);
    exhaleRasp_.set(Biquad::Bandpass, 790, 1.5f);
    exhaleAir_.set(Biquad::Lowpass, 1750);
    outputHigh_.set(Biquad::Highpass, 100);
    outputLow_.set(Biquad::Lowpass, 4300);
  }

  // PCM mono de 16 bits a 22050 Hz, residente em flash. Sem cartão SD.
  void useSample(const int16_t* data, uint32_t count) {
    sample_ = data; sampleCount_ = count >= 2 ? count : 0; samplePosition_ = 0;
  }

  float tick(float valveLevel) {
    if (sample_ && sampleCount_) {
      const uint32_t i = samplePosition_ / 2;
      const uint32_t next = i + 1 < sampleCount_ ? i + 1 : 0;
      float y = sample_[i] / 32768.0f;
      if (samplePosition_ & 1) y = 0.5f * (y + sample_[next] / 32768.0f);
      if (++samplePosition_ >= sampleCount_ * 2) samplePosition_ = 0;
      return y;
    }

    const float noise = noise_.tick();
    if (time_ == 0) {
      variation_ = 1 + 0.025f * noise;
      cycleSamples_ = static_cast<uint32_t>(SAMPLE_RATE * (4.35f + 0.10f * noise));
      valve_.trigger(0.75f);
    }
    if (time_ == 57000) valve_.trigger(0.36f);
    if (time_ == 86500) valve_.trigger(0.46f);
    if (time_ == 155000) valve_.trigger(0.24f);

    const float t = time_ / SAMPLE_RATE;
    // A inspiração sobe depressa. A expiração é mais longa e mais escura.
    const float inhale = smooth((t - 0.028f) / 0.11f)
                       * (1 - smooth((t - 0.73f) / 0.61f));
    const float exhale = smooth((t - 1.98f) / 0.16f)
                       * (1 - smooth((t - 2.66f) / 0.92f));
    flutter_ += 0.0017f * (noise - flutter_);
    pink_ += 0.075f * (noise - pink_);
    const float flow = clamp(1 + 3.5f * flutter_, 0.7f, 1.3f);
    const float in = 0.62f * inhaleBody_.tick(noise)
                   + 0.85f * inhaleRasp_.tick(noise)
                   + (0.15f + 0.20f * inhale) * inhaleAir_.tick(noise);
    const float out = 1.25f * exhaleBody_.tick(pink_)
                    + 0.90f * exhaleRasp_.tick(pink_)
                    + 0.12f * exhaleAir_.tick(noise);
    float air = flow * variation_ * (0.58f * inhale * in + 0.68f * exhale * out);
    // Reflexões curtas no tubo. Não há realimentação nem cauda de reverberação.
    tube_.push(air);
    air += 0.22f * tube_.read(157) - 0.12f * tube_.read(263);
    float y = outputLow_.tick(outputHigh_.tick(air + valveLevel * valve_.tick(noise)));
    if (++time_ >= cycleSamples_) time_ = 0;
    return y;
  }

 private:
  Noise noise_;
  Valve valve_;
  Biquad inhaleBody_, inhaleRasp_, inhaleAir_, exhaleBody_, exhaleRasp_, exhaleAir_;
  Biquad outputHigh_, outputLow_;
  Delay<512> tube_;
  float flutter_ = 0, pink_ = 0, variation_ = 1;
  uint32_t time_ = 0, cycleSamples_ = 191835;
  const int16_t* sample_ = nullptr;
  uint32_t sampleCount_ = 0, samplePosition_ = 0;
};

struct Meters {
  float inputRms = 0;
  float inputPeak = 0;
  float outputPeak = 0;
  float limiterGain = 1;
  bool gateOpen = false;
};

class Processor {
 public:
  explicit Processor(const Tuning& tuning = Tuning()) : tuning_(tuning) {
    inputHigh_.set(Biquad::Highpass, 75);
    inputLow_.set(Biquad::Lowpass, 6500);
    chest_.set(Biquad::Peak, 210, 0.8f, 3.5f);
    box_.set(Biquad::Peak, 620, 1.1f, -3.0f);
    mask_.set(Biquad::Peak, 1250, 1.1f, 3.0f);
    shiftedLow_.set(Biquad::Lowpass, 2400);
    consonantsHigh_.set(Biquad::Highpass, 2100);
    consonantsLow_.set(Biquad::Lowpass, 4800);
    outputHigh_.set(Biquad::Highpass, 65);
    outputLow_.set(Biquad::Lowpass, 4700);
    compressorGain_ = 0.14f / tuning_.referenceRms;
    compressorTarget_ = compressorGain_;
    setChild(false);
  }

  void setChild(bool child) { pitch_.setRatio(child ? tuning_.childPitch : tuning_.adultPitch); }
  void setMode(Mode mode) { mode_ = mode; }
  void setMaster(float volume) { tuning_.master = clamp(volume, 0.0f, 1.0f); }
  float master() const { return tuning_.master; }
  void useBreathSample(const int16_t* data, uint32_t count) { breathing_.useSample(data, count); }
  Meters meters() const { return meters_; }
  void resetPeaks() { meters_.inputPeak = meters_.outputPeak = 0; }

  float tick(float mic) {
    const float filtered = inputLow_.tick(inputHigh_.tick(mic));
    meters_.inputPeak = std::fmax(meters_.inputPeak, std::fabs(mic));
    energy_ += rmsCoefficient_ * (filtered * filtered - energy_);
    if (++controlSamples_ == 64) {
      controlSamples_ = 0;
      meters_.inputRms = std::sqrt(std::fmax(energy_, 0.0f));
      const float relative = meters_.inputRms / tuning_.referenceRms;
      if (relative > tuning_.gateOpen) gate_ = true;
      if (relative > tuning_.gateClose) hold_ = 8820;
      if (!hold_) gate_ = false;
      compressorTarget_ = 0.14f / tuning_.referenceRms;
      if (relative > 0.75f) compressorTarget_ *= std::pow(0.75f / relative, 0.667f);
      meters_.gateOpen = gate_;
    }
    if (hold_) --hold_;
    gateGain_ += ((gate_ ? 1.0f : 0.0f) - gateGain_) * (gate_ ? gateAttack_ : gateRelease_);
    compressorGain_ += (compressorTarget_ - compressorGain_)
                    * (compressorTarget_ < compressorGain_ ? compAttack_ : compRelease_);

    // 8 ms de pré-rolo dão tempo à porta para abrir antes da primeira consoante.
    preRoll_.push(filtered);
    const float input = preRoll_.read(353) * compressorGain_ * gateGain_;
    dry_.push(input);
    const float consonants = consonantsLow_.tick(consonantsHigh_.tick(dry_.read(1103)));
    float voice = shiftedLow_.tick(pitch_.tick(input)) + tuning_.consonants * consonants;
    voice = mask_.tick(box_.tick(chest_.tick(voice)));
    voice = saturate(1.65f * voice) * 0.82f;
    reflection_.push(voice);
    voice += 0.10f * reflection_.read(313) + 0.065f * reflection_.read(499);
    voice = outputLow_.tick(outputHigh_.tick(voice));

    const bool voiceOn = mode_ == Mode::Full || mode_ == Mode::Voice;
    const bool breathOn = mode_ == Mode::Full || mode_ == Mode::Breath;
    voiceMix_ += (static_cast<float>(voiceOn) - voiceMix_) * modeCoefficient_;
    breathMix_ += (static_cast<float>(breathOn) - breathMix_) * modeCoefficient_;
    const float duckTarget = gate_ && voiceOn ? tuning_.breathUnderVoice : 1.0f;
    duck_ += (duckTarget - duck_) * (duckTarget < duck_ ? duckAttack_ : duckRelease_);
    master_ += (tuning_.master - master_) * modeCoefficient_;
    const float breath = breathing_.tick(tuning_.valve);
    const float mix = master_ * (voiceMix_ * tuning_.voice * voice
                              + breathMix_ * tuning_.breath * duck_ * breath);

    // Antecipação de 1,45 ms. Mantém o ganho reduzido até o pico sair do atraso.
    // O limite protege a soma digital. O volume acústico depende do amplificador.
    lookahead_.push(mix);
    const float required = std::fmin(1.0f, 0.88f / (std::fabs(mix) + 0.0000001f));
    if (required < limiterGain_) { limiterGain_ = required; limiterHold_ = 65; }
    else if (limiterHold_) --limiterHold_;
    else limiterGain_ += (1 - limiterGain_) * limiterRelease_;
    const float output = clamp(lookahead_.read(64) * limiterGain_, -0.88f, 0.88f);
    meters_.limiterGain = limiterGain_;
    meters_.outputPeak = std::fmax(meters_.outputPeak, std::fabs(output));
    return output;
  }

 private:
  Tuning tuning_;
  Mode mode_ = Mode::Full;
  Meters meters_;
  PitchShifter pitch_;
  Breathing breathing_;
  Biquad inputHigh_, inputLow_, chest_, box_, mask_, shiftedLow_;
  Biquad consonantsHigh_, consonantsLow_, outputHigh_, outputLow_;
  Delay<512> preRoll_, reflection_;
  Delay<2048> dry_;
  Delay<128> lookahead_;
  float energy_ = 0, gateGain_ = 0, compressorGain_ = 1, compressorTarget_ = 1;
  float voiceMix_ = 0, breathMix_ = 0, duck_ = 1, master_ = 0, limiterGain_ = 1;
  unsigned hold_ = 0, controlSamples_ = 0, limiterHold_ = 0;
  bool gate_ = false;
  const float rmsCoefficient_ = coefficient(6), gateAttack_ = coefficient(1.5f);
  const float gateRelease_ = coefficient(65), compAttack_ = coefficient(4);
  const float compRelease_ = coefficient(180), modeCoefficient_ = coefficient(20);
  const float duckAttack_ = coefficient(45), duckRelease_ = coefficient(220);
  const float limiterRelease_ = coefficient(80);
};

}  // namespace vader
