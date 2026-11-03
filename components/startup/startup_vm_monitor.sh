#! /bin/bash

#echo "Disabling ufw"
#sudo ufw disable

while true; do
	echo "Waiting for 30 seconds before launching VMM Monitor"
	sleep 30

	PLUTO_VM_STATUS=$(virsh list --name | grep -w "pluto-vm")
	HAOS_VM_STATUS=$(virsh list --name | grep -w "Haos")

	echo $PLUTO_VM_STATUS
	echo $HAOS_VM_STATUS

	if [[ -n "$PLUTO_VM_STATUS" && -n "$HAOS_VM_STATUS" ]]; then
		echo "Pluto and Haos VM's running"
	else		
		# Define the network interface to check (e.g., eth0, wlan0)
		INTERFACE="nm-bridge" 

		# Get the IP address of the specified interface
		# This command extracts the IPv4 address from the 'ip addr show' output
		IP_ADDRESS=$(ip addr show "$INTERFACE" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)

		# Check if the IP_ADDRESS variable is not empty
		if [ -n "$IP_ADDRESS" ]; then
  			echo "IP address received on $INTERFACE: $IP_ADDRESS"
			echo "Starting VM's"
			virsh start pluto-vm
			virsh start Haos
		else
			echo "No IP address received on $INTERFACE."
		fi
	fi
done;
