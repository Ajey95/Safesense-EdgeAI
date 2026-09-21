# CSI Transmitter

Configure the same Wi-Fi network as the receiver and its IPv4 address with `idf.py menuconfig`. The application connects before sending bounded UDP sequence packets at 50 Hz for controlled CSI collection. Wi-Fi credentials are intentionally not stored in source control.
