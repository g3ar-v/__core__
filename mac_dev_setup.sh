#!/usr/bin/env bash
# Set a default locale to handle output from commands reliably
export LANG=C.UTF-8
export LANGUAGE=en
export CONDA_ENV_NAME="core"

# exit on any error
set -Ee

ROOT_DIRNAME=$(dirname "$0")
cd "$ROOT_DIRNAME"
TOP=$(pwd -L)

function clean_mycroft_files() {
    echo '
This will completely remove any files installed by mycroft (including pairing
information). 

Do you wish to continue? (y/n)'
    while true; do
        read -rN1 -s key
        case $key in
        [Yy])
            sudo rm -rf /var/log/core
            rm -f /var/tmp/mycroft_web_cache.json
            rm -rf "${TMPDIR:-/tmp}/core"
            rm -rf "$HOME/.core"
            rm -f "skills"  # The Skills directory symlink
            sudo rm -rf "/opt/core"
            exit 0
            ;;
        [Nn])
            exit 1
            ;;
        esac
    done
    

}
function show_help() {
    echo '
Usage: dev_setup.sh [options]
Prepare your environment for running the mycroft-core services.

Options:
    --clean                 Remove files and folders created by this script
    -h, --help              Show this message
    -fm                     Force mimic build
    -n, --no-error          Do not exit on error (use with caution)
    -p arg, --python arg    Sets the python version to use
    -r, --allow-root        Allow to be run as root (e.g. sudo)
    -sm                     Skip mimic build

'
}

function found_exe() {
    hash "$1" 2>/dev/null
}

# Parse the command line
opt_forcemimicbuild=false
opt_allowroot=false
opt_skipmimicbuild=false
opt_python=python3.9
disable_precise_later=false
param=''

if found_exe sudo ; then
    SUDO=sudo
elif found_exe doas ; then
    SUDO=doas
elif [[ $opt_allowroot != true ]]; then
    echo 'This script requires "sudo" to install system packages. Please install it, then re-run this script.'
    exit 1
fi

# create and set permissions for logging
if [[ ! -w /var/log/core/ ]] ; then
    # Creating and setting permissions
    echo 'Creating /var/log/core/ directory'
    if [[ ! -d /var/log/core/ ]] ; then
        $SUDO mkdir /var/log/core/
    fi
    $SUDO chmod 777 /var/log/core/
fi

for var in "$@" ; do
    # Check if parameter should be read
    if [[ $param == 'python' ]] ; then
        opt_python=$var
        param=""
        continue
    fi

    # Check for options
    if [[ $var == '-h' || $var == '--help' ]] ; then
        show_help
        exit 0
    fi

    if [[ $var == '--clean' ]] ; then
        if clean_mycroft_files; then
            exit 0
        else
            exit 1
        fi
    fi
    

    if [[ $var == '-r' || $var == '--allow-root' ]] ; then
        opt_allowroot=true
    fi

    if [[ $var == '-fm' ]] ; then
        opt_forcemimicbuild=true
    fi
    if [[ $var == '-n' || $var == '--no-error' ]] ; then
        # Do NOT exit on errors
        set +Ee
    fi
    if [[ $var == '-sm' ]] ; then
        opt_skipmimicbuild=true
    fi
    if [[ $var == '-p' || $var == '--python' ]] ; then
        param='python'
    fi
done

if [[ $(id -u) -eq 0 && $opt_allowroot != true ]] ; then
    echo 'This script should not be run as root or with sudo.' | tee -a /var/log/core/setup.log
    echo 'If you really need to for this, rerun with --allow-root' | tee -a /var/log/core/setup.log
    exit 1
fi

function get_YN() {
    # Loop until the user hits the Y or the N key
    echo -e -n "Choice [${CYAN}Y${RESET}/${CYAN}N${RESET}]: "
      while true; do
          read -r key
          case $key in
          [Yy])
              return 0
              ;;
          [Nn])
              return 1
              ;;
          esac
      done
}

# If tput is available and can handle multiple colors
if found_exe tput ; then
    if [[ $(tput colors) != "-1" && -z $CI ]]; then
        GREEN=$(tput setaf 2)
        BLUE=$(tput setaf 4)
        CYAN=$(tput setaf 6)
        YELLOW=$(tput setaf 3)
        RESET=$(tput sgr0)
        HIGHLIGHT=$YELLOW
    fi
fi

# Run a setup wizard the very first time that guides the user through some decisions
if [[ ! -f .dev_opts.json && -z $CI ]] ; then
    echo "
$CYAN                    core!  $RESET"
    sleep 0.5
    echo 'During this first run of dev_setup we will ask you a few questions to help setup
your environment.'
    sleep 0.5
    # The AVX instruction set is an x86 construct
    # ARM has a range of equivalents, unsure which are (un)supported by TF.
    if ! grep -q avx /proc/cpuinfo && ! [[ $(uname -m) == 'arm'* || $(uname -m) == 'aarch64' ]]; then
        echo "
The Precise Wake Word Engine requires the AVX instruction set, which is
not supported on your CPU. Do you want to fall back to the PocketSphinx
engine? Advanced users can build the precise engine with an older
version of TensorFlow (v1.13) if desired and change use_precise to true
in mycroft.conf.
  Y)es, I want to use the PocketSphinx engine or my own.
  N)o, stop the installation."
        if get_YN ; then
            if [[ ! -f /etc/core/core.conf ]]; then
                $SUDO mkdir -p /etc/core
                $SUDO touch /etc/core/core.conf
                $SUDO bash -c 'echo "{ \"use_precise\": false }" > /etc/core/core.conf'
            else
                # Ensure dependency installed to merge configs
                disable_precise_later=true
            fi
        else
            echo -e "$HIGHLIGHT N - quit the installation $RESET" | tee -a /var/log/core/setup.log
            exit 1
        fi
        echo
    fi

    # Add mycroft-core/bin to the .bashrc PATH?
    sleep 0.5

    echo '
There are several helper commands in the bin folder.  These
can be added to your system PATH, making it simpler to use core.
Would you like this to be added to your PATH in the .profile?'
    if get_YN ; then
        echo -e "$HIGHLIGHT Y - Adding core commands to your PATH $RESET" | tee -a /var/log/core/setup.log

        if [[ ! -f ~/.profile_core ]] ; then
            # Only add the following to the .profile if .profile_core
            # doesn't exist, indicating this script has not been run before
            # Looking to make this available for zsh
            # Atm I'd have to manually add it to .zprofile
            {
                echo ''
                echo '# include core commands'
                echo 'source ~/.profile_core'
            } >> ~/.profile
        fi

        echo "
# WARNING: This file may be replaced in future, do not customize.
# set path so it includes Core utilities
if [ -d \"${TOP}/bin\" ] ; then
    PATH=\"\$PATH:${TOP}/bin\"
fi" > ~/.profile_core
        echo -e "Type ${CYAN}mycroft-help$RESET to see available commands."
    else
        echo -e "$HIGHLIGHT N - PATH left unchanged $RESET" | tee -a /var/log/core/setup.log
    fi

    # Create a link to the 'skills' folder.
    sleep 0.5
    echo
    echo 'The standard location for core skills is under /opt/core/skills.'
    if [[ ! -d /opt/core/skills ]] ; then
        echo 'This script will create that folder for you.  This requires sudo'
        echo 'permission and might ask you for a password...'
        setup_user=$USER
        setup_group=$(id -gn "$USER")
        $SUDO mkdir -p /opt/core/skills
        $SUDO chown -R "${setup_user}":"${setup_group}" /opt/core
        echo 'Created!'
    fi
    if [[ ! -d skills ]] ; then
        ln -s /opt/core/skills skills
        echo "For convenience, a soft link has been created called 'skills' which leads"
        echo 'to /opt/core/skills.'
    fi

    # Add PEP8 pre-commit hook
    sleep 0.5
    echo '
(Developer) Do you want to automatically check code-style when submitting code.
If unsure answer yes.
'
    if get_YN ; then
        echo 'Will install PEP8 pre-commit hook...' | tee -a /var/log/core/setup.log
        INSTALL_PRECOMMIT_HOOK=true
    fi

    # Save options
    echo '{"use_branch": "'$branch'", "auto_update": '$autoupdate'}' > .dev_opts.json

    echo -e '\nInteractive portion complete, now installing dependencies...\n' | tee -a /var/log/core/setup.log
    sleep 5
fi

function mac_install() {
  APT_PACKAGE_LIST=(python@3.10 jq pulseaudio ffmpeg libtool flac curl mpg123 swig \
    automake bison pkg-config jpeg autoconf screen portaudio) 
    brew install "${APT_PACKAGE_LIST[@]}"
    # /bin/bash -c "$(curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh)"
}

function install_deps() {
    echo 'Installing packages...'
    
    if [[ $(uname -s) == "Darwin" ]]; then
        echo "$GREEN Installing packages for OSX...$RESET" | tee -a /var/log/core/setup.log
        mac_install
    else
        echo
        echo -e "${YELLOW}Could not find package manager
                  ${YELLOW}Make sure to manually install:$BLUE git python3 python-setuptools python-venv pygobject libtool libffi libjpg openssl autoconf bison swig glib2.0 portaudio19 mpg123 flac curl fann g++ jq\n$RESET" | tee -a /var/log/core/setup.log

        echo 'Warning: Failed to install all dependencies. Continue? y/N' | tee -a /var/log/core/setup.log
        read -rn1 continue
        if [[ $continue != 'y' ]] ; then
            exit 1
        fi

    fi
}

# VIRTUALENV_ROOT=${VIRTUALENV_ROOT:-"${TOP}/.venv"}

PYTHON=$(python3 -c "import sys;print('python{}.{}'.format(sys.version_info[0], sys.version_info[1]))")
function install_venv() {
    # $opt_python -m venv "${VIRTUALENV_ROOT}/" 

    # # Check if old script for python 3.6 is needed
    # if "${VIRTUALENV_ROOT}/bin/${opt_python}" --version | grep " 3.6" > /dev/null; then
    #     GET_PIP_URL="https://bootstrap.pypa.io/pip/3.6/get-pip.py"
    # else
    #     GET_PIP_URL="https://bootstrap.pypa.io/get-pip.py"
    # fi

    # Force version of pip for reproducability, but there is nothing special
    # about this version.  Update whenever a new version is released and
    # verified functional.
    # curl "${GET_PIP_URL}" | "${VIRTUALENV_ROOT}/bin/${opt_python}" - 'pip==23.1.2'
    # Function status depending on if pip exists
    # [[ -x ${VIRTUALENV_ROOT}/bin/pip ]]
    # sudo conda install python="$PYTHON"
    if [[ ! $(conda env list | grep -w $CONDA_ENV_NAME) ]]; then
        echo "$HIGHLIGHT Conda environment ($CONDA_ENV_NAME) does not exist. Creating..." $RESET
        sudo conda create --name $CONDA_ENV_NAME python=3.9
    else
        echo "$HIGHLIGHT Not creating ($CONDA_ENV_NAME) environment as it already exists." $RESET
    fi
    
    # NOTE: 
    # conda init zsh
}

install_deps

# It's later. Update existing config with jq.
if [[ $disable_precise_later == true ]]; then
    $SUDO bash -c 'jq ". + { \"use_precise\": false }" /etc/core/core.conf > tmp.core.conf' 
                    $SUDO mv -f tmp.core.conf /etc/core/core.conf
fi

# Configure to use the standard commit template for
# this repo only.
git config commit.template .gitmessage

# Check whether to build mimic (it takes a really long time!)
if [[ ! -x ${VIRTUALENV_ROOT}/bin/activate ]] ; then
    if ! install_venv ; then
        echo 'Failed to set up virtualenv for core, exiting setup.' | tee -a /var/log/core/setup.log
        exit 1
    fi
fi

# Start the virtual environment
# shellcheck source=/dev/null
# source "${VIRTUALENV_ROOT}/bin/activate"
# source "/opt/conda/envs/$CONDA_ENV_NAME/bin/activate"
echo "$HIGHLIGHT Activating conda environment ($CONDA_ENV_NAME)" $RESET
source "/opt/miniconda3/bin/activate" $CONDA_ENV_NAME
cd "$TOP"



# Add mycroft-core to the virtualenv path
# (This is equivalent to typing 'add2virtualenv $TOP', except
# you can't invoke that shell function from inside a script)

# VENV_PATH_FILE="${VIRTUALENV_ROOT}/lib/$PYTHON/site-packages/_virtualenv_path_extensions.pth"
# CONDA_SITE_PACKAGES=$(conda info --base)/envs/$CONDA_ENV_NAME/lib/$PYTHON/site-packages
# if [[ ! -f $VENV_PATH_FILE ]] ; then
#     echo 'import sys; sys.__plen = len(sys.path)' > "$VENV_PATH_FILE" || return 1
#     echo "import sys; new=sys.path[sys.__plen:]; del sys.path[sys.__plen:]; p=getattr(sys,'__egginsert',0); sys.path[p:p]=new; sys.__egginsert = p+len(new)" >> "$VENV_PATH_FILE" || return 1
# fi

# if ! grep -q "$TOP" "$VENV_PATH_FILE" ; then
#     echo 'Adding core to virtualenv path' | tee -a /var/log/core/setup.log
    
#     gsed -i.tmp "1 a$TOP" "$VENV_PATH_FILE"
#     # sed -i.tmp "$(printf '1s/^/%s\n/' "$TOP")" "$VENV_PATH_FILE"
# fi

# install required python modules
if ! pip install -r requirements/requirements.txt ; then
    echo 'Warning: Failed to install required dependencies. Continue? y/N' | tee -a /var/log/core/setup.log
    read -rn1 continue
    if [[ $continue != 'y' ]] ; then
        exit 1
    fi
fi

# install optional python modules
if [[ ! $(pip install -r requirements/extra-audiobackend.txt) ||
    ! $(pip install -r requirements/extra-stt.txt) ]] ; then
    echo 'Warning: Failed to install some optional dependencies. Continue? y/N' | tee -a /var/log/core/setup.log
    read -rn1 continue
    if [[ $continue != 'y' ]] ; then
        exit 1
    fi
fi


if ! pip install -r requirements/tests.txt ; then
    echo "Warning: Test requirements failed to install. Note: normal operation should still work fine..." | tee -a /var/log/core/setup.log
fi

SYSMEM=$(vm_stat | awk '/^Pages free/ { print $3 * 4096 }')
# SYSMEM=$(free | awk '/^Mem:/ { print $2 }')
MAXCORES=$((SYSMEM / 2202010))
MINCORES=1
CORES=$(sysctl -n hw.ncpu)
# CORES=$(nproc)

# ensure MAXCORES is > 0
if [[ $MAXCORES -lt 1 ]] ; then
    MAXCORES=${MINCORES}
fi

# Be positive!
if ! [[ $CORES =~ ^[0-9]+$ ]] ; then
    CORES=$MINCORES
elif [[ $MAXCORES -lt $CORES ]] ; then
    CORES=$MAXCORES
fi

echo "$GREEN Building with $CORES cores. $RESET" | tee -a /var/log/core/setup.log

cd "$TOP"

# set permissions for common scripts
chmod +x start-core.sh
chmod +x stop-core.sh
chmod +x bin/core-cli-client
chmod +x bin/core-help
chmod +x bin/mycroft-mic-test
# chmod +x bin/mycroft-msk
# chmod +x bin/mycroft-msm
# chmod +x bin/mycroft-pip
# chmod +x bin/mycroft-say-to
# chmod +x bin/mycroft-skill-testrunner
chmod +x bin/core-speak

#Store a fingerprint of setup
md5 requirements/requirements.txt requirements/extra-audiobackend.txt requirements/extra-stt.txt requirements/tests.txt mac_dev_setup.sh > .installed

# Build and install core
pip install -e .

echo 'setup complete! Logs can be found at /var/log/core/setup.log' | tee -a /var/log/core/setup.log
