#include "../vader_dsp.h"
#include <cstdio>
#include <cstring>

#if __has_include("../breath_sample.h")
#define PROGMEM
#include "../breath_sample.h"
#endif

int main(int argc, char** argv) {
  if (argc != 5) {
    std::fprintf(stderr, "Usage: render breath|voice|full adult|child input.f32|- output.f32\n");
    return 2;
  }
  vader::Processor processor;
  if (!std::strcmp(argv[1], "breath")) processor.setMode(vader::Mode::Breath);
  else if (!std::strcmp(argv[1], "voice")) processor.setMode(vader::Mode::Voice);
  else if (std::strcmp(argv[1], "full")) return 2;
  if (!std::strcmp(argv[2], "child")) processor.setChild(true);
  else if (std::strcmp(argv[2], "adult")) return 2;
#if __has_include("../breath_sample.h")
  processor.useBreathSample(VADER_BREATH_PCM, VADER_BREATH_SAMPLES);
#endif

  const bool silence = !std::strcmp(argv[3], "-");
  FILE* input = silence ? nullptr : std::fopen(argv[3], "rb");
  if (!silence && !input) { std::perror(argv[3]); return 1; }
  FILE* output = std::fopen(argv[4], "wb");
  if (!output) { if (input) std::fclose(input); std::perror(argv[4]); return 1; }
  float in = 0, peak = 0;
  double squares = 0;
  unsigned samples = 0;
  while (silence ? samples < 4 * 44100 * 5 : std::fread(&in, sizeof(in), 1, input) == 1) {
    const float value = processor.tick(in);
    if (!std::isfinite(value) || std::fabs(value) > 0.88001f) {
      std::fprintf(stderr, "Invalid audio at sample %u\n", samples);
      return 1;
    }
    if (std::fwrite(&value, sizeof(value), 1, output) != 1) return 1;
    peak = std::fmax(peak, std::fabs(value));
    squares += value * value;
    ++samples;
  }
  const bool readError = input && std::ferror(input);
  if (input) std::fclose(input);
  if (std::fclose(output) != 0 || readError || samples == 0) return 1;
  std::printf("%.2f s, peak %.4f, RMS %.4f\n", samples / vader::SAMPLE_RATE,
              peak, std::sqrt(squares / samples));
  return 0;
}
