#include "csi_model.h"

#include <cmath>
#include <cstdint>

#include "esp_log.h"
#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "wisdom48_model_data.h"
#include "wisdom48_normalization.h"

namespace {
constexpr int kArenaBytes = 64 * 1024;
constexpr int kOutputClasses = 3;
constexpr float kMinConfidence = 0.70f;
alignas(16) uint8_t tensor_arena[kArenaBytes];
const tflite::Model *model;
tflite::MicroInterpreter *interpreter;
TfLiteTensor *input;
TfLiteTensor *output;
bool initialized;
const char *TAG = "csi_model";

fusion_activity_t safe_activity(int label) {
    switch (label) {
        case 0: return FUSION_ACTIVITY_VACANT;
        case 1: return FUSION_ACTIVITY_STATIONARY;
        case 2: return FUSION_ACTIVITY_WALKING;
        default: return FUSION_ACTIVITY_UNKNOWN;
    }
}

bool initialize() {
    if (initialized) return true;
    model = tflite::GetModel(g_wisdom48_model);
    if (model->version() != TFLITE_SCHEMA_VERSION) return false;
    static tflite::MicroMutableOpResolver<4> resolver;
    resolver.AddConv2D();
    resolver.AddMean();
    resolver.AddFullyConnected();
    resolver.AddSoftmax();
    static tflite::MicroInterpreter local(model, resolver, tensor_arena, kArenaBytes);
    interpreter = &local;
    if (interpreter->AllocateTensors() != kTfLiteOk) return false;
    input = interpreter->input(0);
    output = interpreter->output(0);
    if (input->type != kTfLiteInt8 || output->type != kTfLiteInt8 ||
        input->bytes != CSI_WINDOW_FRAMES * CSI_DATA_SUBCARRIERS || output->bytes != kOutputClasses) return false;
    initialized = true;
    return true;
}
}

extern "C" fusion_activity_t csi_model_infer(const float window[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS], float *confidence) {
    if (confidence) *confidence = 0.0f;
    if (!window || !initialize()) {
        ESP_LOGE(TAG, "TFLM model initialization failed");
        return FUSION_ACTIVITY_UNKNOWN;
    }
    const float scale = input->params.scale;
    const int zero = input->params.zero_point;
    for (int frame = 0; frame < CSI_WINDOW_FRAMES; ++frame) for (int carrier = 0; carrier < CSI_DATA_SUBCARRIERS; ++carrier) {
        float normalized = (window[frame][carrier] - g_wisdom48_mean[carrier]) / g_wisdom48_std[carrier];
        int quantized = static_cast<int>(std::lround(normalized / scale)) + zero;
        if (quantized < -128) quantized = -128;
        if (quantized > 127) quantized = 127;
        input->data.int8[frame * CSI_DATA_SUBCARRIERS + carrier] = static_cast<int8_t>(quantized);
    }
    if (interpreter->Invoke() != kTfLiteOk) return FUSION_ACTIVITY_UNKNOWN;
    int label = 0; int8_t best = output->data.int8[0];
    for (int index = 1; index < kOutputClasses; ++index) if (output->data.int8[index] > best) { best = output->data.int8[index]; label = index; }
    float probability = (static_cast<float>(best) - output->params.zero_point) * output->params.scale;
    if (confidence) *confidence = probability;
    return probability >= kMinConfidence ? safe_activity(label) : FUSION_ACTIVITY_UNKNOWN;
}
