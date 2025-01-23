# Juniper Mist - Guest logger

Python script to log guest clients data from a Juniper Mist Wi-Fi infrastructure
For legal purposes in France (guest Internet access log retention for a year)

![screenshot](mist-guest-logger-screenshot01.png)

Authors: Jonathan Rambeau

Date: 03 jan 2025

Changelog:
- 27 jun 2024: creation
- 03 jan 2025: solved an issue where too many API calls where being made and trigger throttling (when getting client details using RESTFUL APIs) 

## 1. Installation

1. Install python
2. Check if pip is installed ``` python -m pip --version ```. If not installed, install it: https://pip.pypa.io/en/stable/installing/
3. Upgrade pip ``` python.exe -m pip install --upgrade pip ```
4. Install additionnal required libraries:
    1. ```pip install -r requirements.txt```
5. Customize file apivariables.py with your API Token and Organization ID. I recommend using a Token generated from a service account of your Organization (and not an actual user account)

## 2. Run the script

1. From a terminal, start the script: ``` mist-guest-logger.py ```
2. Alternatively, use the Powershell script ```run-mist-guest-logger.ps1``` if you want to configure a scheduled task on a Windows machine