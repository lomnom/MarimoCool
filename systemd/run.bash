#!/bin/bash
cd ../marimo
echo "Starting service screens..."
screen -S gpio_service -d -m python3 -m gpio_service.run
screen -S temp_manager -d -m python3 -m temp_manager.high_run
screen -S web_service -d -m python3 -m web_service.run