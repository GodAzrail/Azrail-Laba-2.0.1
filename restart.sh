#!/bin/bash
sleep 2
pkill -9 -f app.py
nohup /opt/Azrail-Laba/venv/bin/python /opt/Azrail-Laba/app.py > /opt/Azrail-Laba/panel.log 2>&1 &
