#!/usr/bin/env bash

# wrap in function to allow local variables, since this file will be source'd
function main() { 
    local quiet=0

    for arg in "$@"
    do
        case $arg in
            "-q"|"--quiet" )
               quiet=1
               ;;

            "-h"|"--help" )
               echo "venv-activate.sh:  Enter the Mycroft virtual environment"
               echo "Usage:"
               echo "   source venv-activate.sh"
               echo "or"
               echo "   . venv-activate.sh"
               echo ""
               echo "Options:"
               echo "   -q | --quiet    Don't show instructions."
               echo "   -h | --help    Show help."
               return 0
               ;;

            *)
               echo "ERROR:  Unrecognized option: $arg"
               return 1
               ;;
       esac
    done

    if [[ "$0" == "${BASH_SOURCE[0]}" ]] ; then
        # Prevent running in script then exiting immediately
        echo "ERROR: Invoke with 'source venv-activate.sh' or '. venv-activate.sh'"
    else
        local SRC_DIR
        SRC_DIR="$( builtin cd "$( dirname "${BASH_SOURCE[0]}" )" || exit 1; pwd -P )"
        source "${SRC_DIR}/.venv/bin/activate"
        
        # Provide an easier to find "core-" prefixed command.
        unalias core-venv-activate 2>/dev/null
        # shellcheck disable=SC2139 # The intention _is_ to resolve the variable at define time
        alias core-venv-deactivate="deactivate && unalias core-venv-deactivate 2>/dev/null && alias core-venv-activate=\"source '${SRC_DIR}/venv-activate.sh'\""
        if [ $quiet -eq 0 ] ; then
            echo "Entering Core virtual environment.  Run 'core-venv-deactivate' to exit"
        fi
    fi
}

main "$@"
