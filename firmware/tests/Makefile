CC ?= gcc
CFLAGS = -std=c11 -Wall -Wextra -Werror -I../components/bme280/include

test_bme280_driver: test_bme280_driver.c ../components/bme280/bme280_driver.c
	$(CC) $(CFLAGS) $^ -lm -o $@

test_fusion_engine: test_fusion_engine.c ../components/fusion/fusion_engine.c
	$(CC) $(CFLAGS) -I../components/fusion/include $^ -o $@

test_csi_gas: test_csi_gas.c ../components/csi/csi_pipeline.c ../components/gas_risk/gas_risk.c

	$(CC) $(CFLAGS) -I../components/csi/include -I../components/gas_risk/include $^ -lm -o $@

test: test_bme280_driver test_fusion_engine test_csi_gas
	./test_bme280_driver
	./test_fusion_engine
	./test_csi_gas
