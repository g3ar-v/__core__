#!/usr/bin/env bash

SOURCE="${BASH_SOURCE[0]}"
cd -P "$(dirname "$SOURCE")"/.. || exit
DIR="$(pwd)"


echo "file watcher starting... $DIR"
# skills component dev loop
ls $DIR/core/skills/*.py $DIR/core/intent_services/*.py $DIR/core/llm/*.py | entr -s 'core-start restart skills' > /var/log/core/skills.log &

# voice component dev loop
ls $DIR/core/client/voice/*.py $DIR/core/stt/*.py | entr -s 'core-start restart voice' > /var/log/core/voice.log &

# audio component dev loop
ls $DIR/core/audio/*.py | entr -s 'core-start restart audio' > /var/log/core/audio.log &


