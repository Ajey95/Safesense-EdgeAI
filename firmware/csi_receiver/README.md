# CSI Receiver

Configure Wi-Fi with `idf.py menuconfig`. The application connects before enabling CSI, keeps the ESP-IDF callback non-blocking, queues records, validates them in the processing task, and produces windows for the deferred model interface. The access point fixes the collection channel for both devices.

`csi_model_infer` defaults to the `UNKNOWN` stub. After a release manifest is reviewed, generate the model and normalization headers, then enable `CONFIG_SAFESENSE_CSI_TFLM_MODEL` in `menuconfig`. The component manifest pulls the version-pinned Espressif TensorFlow Lite Micro runtime at configure time.
