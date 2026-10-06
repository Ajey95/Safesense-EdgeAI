CC ?= gcc
CFLAGS = -std=c11 -Wall -Wextra -Werror -I../components/bme280/include

test_bme680_driver: test_bme680_driver.c ../components/bme680/bme680_driver.c
	$(CC) $(CFLAGS) -I../components/bme680/include $^ -lm -o $@

test_tx_protocol: test_tx_protocol.c ../components/tx_protocol/tx_protocol.c
	$(CC) $(CFLAGS) -I../components/tx_protocol/include $^ -lm -o $@

# Build the RX ESP-IDF project first so its declared cJSON dependency is available.
CJSON_DIR = ../node2_csi_gateway/managed_components/espressif__cjson/cJSON
test_rx_protocol: test_rx_protocol.c ../components/rx_protocol/rx_protocol.c $(CJSON_DIR)/cJSON.c
	$(CC) $(CFLAGS) -I../components/rx_protocol/include -I$(CJSON_DIR) $^ -lm -o $@

test_tx_queue_namespace: test_tx_queue_namespace.c ../components/delivery/delivery_queue.c
	$(CC) $(CFLAGS) -Istubs -I../components/delivery/include $^ -o $@

test_bme280_driver: test_bme280_driver.c ../components/bme280/bme280_driver.c
	$(CC) $(CFLAGS) $^ -lm -o $@

test_fusion_engine: test_fusion_engine.c ../components/fusion/fusion_engine.c
	$(CC) $(CFLAGS) -I../components/fusion/include $^ -o $@

test_csi_gas: test_csi_gas.c ../components/csi/csi_pipeline.c ../components/gas_risk/gas_risk.c

	$(CC) $(CFLAGS) -I../components/csi/include -I../components/gas_risk/include $^ -lm -o $@

test: test_bme280_driver test_bme680_driver test_tx_protocol test_rx_protocol test_tx_queue_namespace test_fusion_engine test_csi_gas
	./test_bme280_driver
	./test_bme680_driver
	./test_tx_protocol
	./test_rx_protocol
	./test_tx_queue_namespace
	./test_fusion_engine
	./test_csi_gas
