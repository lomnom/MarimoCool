#!/bin/bash
cd ../marimo

# Stopping both screens
echo "Sending ctrl-c to service screens..."

screen -S warn_service -X at "#" stuff '^C'
while screen -list | grep -q "warn_service"; 
    do sleep 1; 
done

screen -S web_service -X at "#" stuff '^C'
while screen -list | grep -q "web_service"; 
    do sleep 1; 
done

screen -S temp_manager -X at "#" stuff '^C'
while screen -list | grep -q "temp_manager"; 
    do sleep 1; 
done

screen -S gpio_service -X at "#" stuff '^C'
while screen -list | grep -q "gpio_service"; 
    do sleep 1; 
done