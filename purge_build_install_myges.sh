#!/bin/bash

sudo apt purge mygesclient -y
sudo ./scripts/deb.sh
sudo apt install ./builds/*.deb
