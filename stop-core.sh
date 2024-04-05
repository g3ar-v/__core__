#!/bin/sh

# This script is never sourced but always directly executed, so this is safe to do
SOURCE="$0"

script=${0}
script=${script##*/}
cd -P "$(dirname "$SOURCE")" || exit 1 # quit if change of folder fails

help() {
	echo "${script}:  System service stopper"
	echo "usage: ${script} [service]"
	echo
	echo "Service:"
	echo "  all       ends core services: bus, audio, core, listener"
	echo "  (none)    same as \"all\""
	echo "  bus       stop the System messagebus service"
	echo "  audio     stop the audio playback service"
	echo "  core    stop the skill service"sk
	echo "  listener     stop listener capture service"
	# echo "  enclosure stop enclosure (hardware/gui interface) service"
	echo "  ui        stop ui service"
	echo "  backend   stop ui backend service"
	echo "  dev   	  stop file monitor for CORE"
	echo
	echo "Examples:"
	echo "  ${script}"
	echo "  ${script} audio"

	exit 0
}

process_running() {
	if [ "$(pgrep -f "${1}")" ]; then
		return 0
	else
		return 1
	fi
}

end_process() {
	if process_running "$1"; then
		# Find the process by name, only returning the oldest if it has children
		pid=$(pgrep -o -f "${1}")
		printf "Stopping %s (%s)..." "$OPT" "${pid}"
		kill -s INT "${pid}"

		# Wait up to 5 seconds (50 * 0.1) for process to stop
		c=1
		while [ $c -le 50 ]; do
			if process_running "$1"; then
				sleep 0.1
				c=$((c + 1))
			else
				c=999 # end loop
			fi
		done

		if process_running "$1"; then
			echo "failed to stop."
			pid=$(pgrep -o -f "${1}")
			printf "  Killing %s (%s)...\n" "$OPT" "${pid}"
			kill -9 "${pid}"
			echo "killed."
			result=120
		else
			echo "stopped."
			if [ $result -eq 0 ]; then
				result=100
			fi
		fi
	fi
}

result=0 # default, no change

OPT=$1
if [ $# -gt 0 ]; then
	shift
fi

case ${OPT} in
"" | "all")
	echo "Stopping all core services"
	end_process "(python3|python|Python) (.*)-m source.*core"
	end_process "(python3|python|Python) (.*)-m source.*listener"
	end_process "(python3|python|Python) (.*)-m source.*enclosure"
	end_process "(python3|python|Python) (.*)-m source.*messagebus.service"
	end_process "(python3|python|Python) (.*)-m source.*client"
	end_process "(python3|python|Python) (.*)-m source.*audio"
	end_process "uvicorn source.ui.backend.__main__:app"
	end_process "npm run dev"
	end_process "entr -s core-start restart core"
	end_process "entr -s core-start restart listener"
	end_process "entr -s core-start restart audio"

	;;
"bus")
	end_process "(python3|python|Python) (.*)-m source.*messagebus.service"
	;;
"audio")
	end_process "(python3|python|Python) (.*)-m source.*audio"
	;;
"core")
	end_process "(python3|python|Python) (.*)-m source.*core"
	;;
"listener")
	end_process "(python3|python|Python) (.*)-m source.*listener"
	;;
"enclosure")
	end_process "(python3|python|Python) (.*)-m source.*enclosure"
	;;
"client")
	end_process "(python3|python|Python) (.*)-m source.*client"
	;;
"backend")
	end_process "uvicorn source.ui.backend.__main__:app"
	;;
"ui")
	end_process "npm run dev"
	;;
"web")
	end_process "(python3|python|Python) (.*)-m source.*web"
	;;
"dev")
	end_process "entr -s core-start restart core"
	end_process "entr -s core-start restart listener"
	end_process "entr -s core-start restart audio"
	;;
*)
	help
	;;
esac

# Exit codes:
#     0   if nothing changed (e.g. --help or no process was running)
#     100 at least one process was stopped
#     120 if any process had to be killed
exit $result
