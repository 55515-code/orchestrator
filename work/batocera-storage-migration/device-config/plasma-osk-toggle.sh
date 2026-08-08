#!/bin/bash

command_file="$(dirname "$(readlink -f "$0")")/plasma-command"
printf '%s\n' osk-toggle > "$command_file"
