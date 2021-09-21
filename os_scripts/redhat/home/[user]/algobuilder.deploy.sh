#!/bin/bash
# Deploy latest version of algobuilder.
# 1) Fetches from github
# 2) Copies new or changed files to /opt/algobuilder
# Does not migrate any database changes or restart services. This should be done manually depending on what has changed.

# First we will pull the latest from github
cd ~/git/algobuilder || { echo "Could not cd to ~/git/algobuilder."; exit 1; }
git pull

# Then we will copy any changed files to /opt/algobuilder and change owner to algobuilder
cd /opt/algobuilder || { echo "Could not cd to /opt/algobuilder."; exit 1; }
sudo rsync -rtv ~/git/algobuilder/ .
cd /opt || { echo "Could not cd to /opt."; exit 1; }
sudo chown algobuilder:algobuilder algobuilder/