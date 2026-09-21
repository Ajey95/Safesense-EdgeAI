CC ?= gcc
CFLAGS = -std=c11 -Wall -Wextra -Werror

.PHONY: test test_bme680_driver clean

test_bme680_driver: bme680_driver_test
	./bme680_driver_test

bme680_driver_test: test_bme680_driver.c ../components/bme680/bme680_driver.c
	$(CC) $(CFLAGS) -I../components/bme680/include $^ -lm -o $@

test_fusion_engine: test_fusion_engine.c ../components/fusion/fusion_engine.c
	$(CC) $(CFLAGS) -I../components/fusion/include $^ -o $@

test_csi_gas: test_csi_gas.c ../components/csi/csi_pipeline.c ../components/gas_risk/gas_risk.c

	$(CC) $(CFLAGS) -I../components/csi/include -I../components/gas_risk/include $^ -lm -o $@

test: bme680_driver_test test_fusion_engine test_csi_gas
	./bme680_driver_test
	./test_fusion_engine
	./test_csi_gas

clean:
ifeq ($(OS),Windows_NT)
	cmd /C "del /Q bme680_driver_test.exe test_bme680_driver.exe test_bme280_driver.exe test_fusion_engine.exe test_csi_gas.exe 2>NUL || exit /B 0"
else
	$(RM) bme680_driver_test test_bme680_driver test_fusion_engine test_csi_gas
endif
