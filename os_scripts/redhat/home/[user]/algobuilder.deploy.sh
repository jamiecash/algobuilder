#!/bin/bash
# Deploy latest version of algobuilder.
# 1) Fetches from github
# 2) Copies new or changed files to /opt/algobuilder
# Does not migrate any database changes or restart services. This should be done manually depending on what has changed.

# First we will fetch the latest from github
cd ~/git/algobuilder
git fetch

# Then we will copy any changed files to /opt/algobuilder
sudo su
rsync -rtv ~/git/algobuilder /opt