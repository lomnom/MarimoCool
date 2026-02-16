#!/bin/bash
cd ../marimo

# Stopping both screens
echo "Sending ctrl-c to service screens..."
screen -S web_service -X at "#" stuff '^C'
screen -S temp_manager -X at "#" stuff '^C'
screen -S gpio_service -X at "#" stuff '^C'