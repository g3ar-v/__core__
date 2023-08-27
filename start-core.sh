#!/bin/sh
SOURCE="$0"

script=${0}
# echo  "script: $script"
script=${script##*/}
# NOTE: for macOS, it seems I have to leave script folder to run the other scripts
if [[ script =~ "start-core" ]]; then
    cd -P "$( dirname "$SOURCE" )"/.. || exit 1 # Enter scripts folder or fail!
else
    cd -P "$( dirname "$SOURCE" )" || exit 1 # Enter scripts folder or fail!
fi
DIR="$( pwd )"
VIRTUALENV_ROOT=${VIRTUALENV_ROOT:-"${DIR}/.venv"}

help() {
    echo "${script}:  core command/service launcher"
    echo "usage: ${script} [COMMAND] [restart] [params]"
    echo
    echo "Services COMMANDs:"
    echo "  all                      runs core services: bus, audio, skills, voice"
    echo "  debug                    runs core services, then starts the CLI"
    echo "  audio                    the audio playback service"
    echo "  bus                      the messagebus service"
    echo "  skills                   the skill service"
    echo "  voice                    voice capture service"
    # echo "  enclosure                enclosure service"
    echo
    echo "Tool COMMANDs:"
    echo "  cli                      the Command Line Interface"
    # echo "  unittest                 run core unit tests (requires pytest)"
    # echo "  skillstest               run the skill autotests for all skills (requires pytest)"
    # echo "  vktest                   run the Voight Kampff integration test suite"
    echo
    # echo "Util COMMANDs:"
    # echo "  audiotest                attempt simple audio validation"
    # echo "  wakewordtest             test selected wakeword engine"
    # echo "  sdkdoc                   generate sdk documentation"
    echo
    echo "Options:"
    echo "  restart                  (optional) Force the service to restart if running"
    echo
    echo "Examples:"
    echo "  ${script} all"
    echo "  ${script} all restart"
    echo "  ${script} cli"
    # echo "  ${script} unittest"

    exit 1
}

_module=""
name_to_script_path() {
    case ${1} in
        "bus")               _module="core.messagebus.service" ;;
        "skills")            _module="core.skills" ;;
        "audio")             _module="core.audio" ;;
        "voice")             _module="core.client.voice" ;;
        "cli")               _module="core.client.text" ;;
        # "audiotest")         _module="core.util.audio_test" ;;
        # "wakewordtest")      _module="test.wake_word" ;;
        # "enclosure")         _module="core.client.enclosure" ;;

        *)
            echo "Error: Unknown name '${1}'"
            exit 1
    esac
}

source_venv() {
    # Enter Python virtual environment, unless under Docker
    echo "Entering virtual environment ${VIRTUALENV_ROOT}"
    if [ ! -f "/.dockerenv" ] ; then
        . "${VIRTUALENV_ROOT}/bin/activate"
    fi
}

first_time=true
init_once() {
    if ($first_time) ; then
        echo "Initializing..."
        "${DIR}/scripts/prepare-msm.sh"
        source_venv
        first_time=false
    fi
    # NOTE: this won't be here if first_time is initially false at runtime
    # source_venv
}

launch_process() {
    init_once

    name_to_script_path "${1}"

    # Launch process in foreground
    echo "Starting $1"
    python3 -m ${_module} "$@"
}

require_process() {
    # Launch process if not found
    name_to_script_path "${1}"
    if ! pgrep -f "(python3|python|Python) (.*)-m ${_module}" > /dev/null ; then
        # Start required process
        launch_background "${1}"
    fi
}

launch_background() {
    init_once

    # Check if given module is running and start (or restart if running)
    name_to_script_path "${1}"
    if pgrep -f "(python3|python|Python) (.*)-m ${_module}" > /dev/null ; then
        if ($_force_restart) ; then
            echo "Restarting: ${1}"
            "${DIR}/stop-core.sh" "${1}"
        else
            # Already running, no need to restart
            return
        fi
    else
        echo "Starting background service $1"
    fi

    # Security warning/reminder for the user
    if [ "${1}" = "bus" ] ; then
        echo "CAUTION: The core bus is an open websocket with no built-in security"
        echo "         measures.  You are responsible for protecting the local port"
        echo "         8181 with a firewall as appropriate."
    fi

    # Launch process in background, sending logs to standard location
    python3 -m ${_module} "$@" >> "/var/log/core/${1}.log" 2>&1 &
}

launch_all() {
    echo "Starting all core services"
    launch_background bus
    launch_background audio
    launch_background voice
    launch_background skills
    # launch_background enclosure
}

check_dependencies() {
    if [ -f .dev_opts.json ] ; then
        auto_update=$( jq -r ".auto_update" < .dev_opts.json 2> /dev/null)
    else
        auto_update="false"
    fi
    if [ "$auto_update" = "true" ] ; then
        # Check github repo for updates (e.g. a new release)
        git pull
    fi

    if [ ! -f .installed ] || ! md5sum -c > /dev/null 2>&1 < .installed ; then
        # Critical files have changed, dev_setup.sh should be run again
        if [ "$auto_update" = "true" ] ; then
            echo "Updating dependencies..."
            bash dev_setup.sh
        else
            echo "Please update dependencies by running ./dev_setup.sh again."
            if command -v notify-send >/dev/null ; then
                # Generate a desktop notification (ArchLinux)
                notify-send "core Dependencies Outdated" "Run ./dev_setup.sh again"
            fi
            exit 1
        fi
    fi
}

_opt=$1
_force_restart=false

if [ $# -eq 0 ]; then
	help
	return
fi

shift
if [ "${1}" = "restart" ] || [ "${_opt}" = "restart" ] ; then
    _force_restart=true
    if [ "${_opt}" = "restart" ] ; then
        # Support "start-mycroft.sh restart all" as well as "start-mycroft.sh all restart"
        _opt=$1
    fi

    if [ $# -gt 0 ]; then
	    shift
    fi
fi

# if [ ! "${_opt}" = "cli" ] ; then
#     # check_dependencies
# fi

case ${_opt} in
    "all")
        launch_all
        ;;

    "bus")
        launch_background "${_opt}"
        ;;
    "audio")
        launch_background "${_opt}"
        ;;
    "skills")
        launch_background "${_opt}"
        ;;
    "voice")
        launch_background "${_opt}"
        ;;

    "debug")
        launch_all
        launch_process cli
        ;;

    "cli")
        require_process bus
        require_process skills
        launch_process "${_opt}"
        ;;

    # TODO: Restore support for Wifi Setup on a Picroft, etc.
    # "wifi")
    #    launch_background ${_opt}
    #    ;;
    "unittest")
        source_venv
        pytest test/unittests/ --cov=mycroft "$@"
        ;;
    "singleunittest")
        source_venv
        pytest "$@"
        ;;
    "skillstest")
        source_venv
        pytest test/integrationtests/skills/discover_tests.py "$@"
        ;;
    "vktest")
        "$DIR/bin/mycroft-skill-testrunner" vktest "$@"
        ;;
    "audiotest")
        launch_process "${_opt}"
        ;;
    "wakewordtest")
        launch_process "${_opt}"
        ;;
    "sdkdoc")
        source_venv
        cd doc || exit 1  # Exit if doc directory doesn't exist
        make "$@"
        cd ..
        ;;
    "enclosure")
        launch_background "${_opt}"
        ;;

    *)
        help
        ;;
esac
