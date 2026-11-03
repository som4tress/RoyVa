#! /bin/bash

#echo "Disabling ufw"
#sudo ufw disable

echo "Waiting for 300 seconds before launching Camera Monitor"
sleep 300

#source /home/pluto/blinkpy/blinkpy/bin/activate
source /home/somdutta/Projects/.venv/bin/activate
cd /home/somdutta/Projects/VideoClassification/
while true; do echo "Launching Security Camera Monitoring Service"; /home/somdutta/Projects/.venv/bin/python3 RLCAnalyzer.py; sleep 30; done

