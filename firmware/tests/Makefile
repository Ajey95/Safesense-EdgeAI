CC ?= gcc
CFLAGS = -std=c11 -Wall -Wextra -Werror

.PHONY: test test_bme680_driver test_gas_risk test_node_protocol clean

test_bme680_driver: bme680_driver_test
	./bme680_driver_test

bme680_driver_test: test_bme680_driver.c ../components/bme680/bme680_driver.c
	$(CC) $(CFLAGS) -I../components/bme680/include $^ -lm -o $@

test_gas_risk: gas_risk_test
	./gas_risk_test

gas_risk_test: test_gas_risk.c ../components/gas_risk/gas_risk.c
	$(CC) $(CFLAGS) -I../components/gas_risk/include $^ -lm -o $@

test_node_protocol: node_protocol_test
	./node_protocol_test

node_protocol_test: test_node_protocol.c ../components/node_protocol/node_protocol.c
	$(CC) $(CFLAGS) -I../components/node_protocol/include -I../components/gas_risk/include $^ -o $@

test_fusion_engine: test_fusion_engine.c ../components/fusion/fusion_engine.c
	$(CC) $(CFLAGS) -I../components/fusion/include $^ -o $@

test_csi_gas: test_csi_gas.c ../components/csi/csi_pipeline.c
	$(CC) $(CFLAGS) -I../components/csi/include $^ -lm -o $@

test: bme680_driver_test gas_risk_test node_protocol_test test_fusion_engine test_csi_gas
	./bme680_driver_test
	./gas_risk_test
	./node_protocol_test
	./test_fusion_engine
	./test_csi_gas

clean:
ifeq ($(OS),Windows_NT)
	cmd /C "del /Q bme680_driver_test.exe gas_risk_test.exe node_protocol_test.exe test_bme680_driver.exe test_bme280_driver.exe test_fusion_engine.exe test_csi_gas.exe 2>NUL || exit /B 0"
else
	$(RM) bme680_driver_test gas_risk_test node_protocol_test test_bme680_driver test_fusion_engine test_csi_gas
endif
