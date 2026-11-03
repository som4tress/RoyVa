#!/bin/bash

unknown_os ()
{
  echo "Unfortunately, your operating system distribution and version are not supported by this script."
  echo
  echo "You can override the OS detection by setting os= and dist= prior to running this script."
  echo "You can find a list of supported OSes and distributions on our website: https://packagecloud.io/docs#os_distro_version"
  echo
  echo "For example, to force Ubuntu Trusty: os=ubuntu dist=trusty ./script.sh"
  echo
  echo "You can override the dpkg lock timeout (default 300 seconds) by setting dpkg_lock_timeout= prior to running this script."
  echo
  echo "Please contact the owner of this repository/package for further support."
  exit 1
}

gpg_check ()
{
  echo "Checking for gpg..."
  if command -v gpg > /dev/null; then
    echo "Detected gpg..."
  else
    echo "Installing gnupg for GPG verification..."
    apt-get install -y gnupg -o DPkg::Lock::Timeout=${dpkg_lock_timeout}
    if [ "$?" -ne "0" ]; then
      echo "Unable to install GPG! Your base system has a problem; please check your default OS's package repositories because GPG should work."
      echo "Repository installation aborted."
      exit 1
    fi
  fi
}

curl_check ()
{
  echo "Checking for curl..."
  if command -v curl > /dev/null; then
    echo "Detected curl..."
  else
    echo "Installing curl..."
    apt-get install -q -y curl -o DPkg::Lock::Timeout=${dpkg_lock_timeout}
    if [ "$?" -ne "0" ]; then
      echo "Unable to install curl! Your base system has a problem; please check your default OS's package repositories because curl should work."
      echo "Repository installation aborted."
      exit 1
    fi
  fi
}

install_debian_keyring ()
{
  if [ "${os,,}" = "debian" ]; then
    echo "Installing debian-archive-keyring which is needed for installing "
    echo "apt-transport-https on many Debian systems."
    apt-get install -y debian-archive-keyring -o DPkg::Lock::Timeout=${dpkg_lock_timeout} &> /dev/null
  fi
}


detect_os ()
{
  if [[ ( -z "${os}" ) && ( -z "${dist}" ) ]]; then
    # some systems dont have lsb-release yet have the lsb_release binary and
    # vice-versa
    if [ -e /etc/lsb-release ]; then
      . /etc/lsb-release

      if [ "${ID}" = "raspbian" ]; then
        os=${ID}
        dist=`cut --delimiter='.' -f1 /etc/debian_version`
      else
        os=${DISTRIB_ID}
        dist=${DISTRIB_CODENAME}

        if [ -z "$dist" ]; then
          dist=${DISTRIB_RELEASE}
        fi
      fi

    elif [ `which lsb_release 2>/dev/null` ]; then
      dist=`lsb_release -c | cut -f2`
      os=`lsb_release -i | cut -f2 | awk '{ print tolower($1) }'`

    elif [ -e /etc/debian_version ]; then
      # some Debians have jessie/sid in their /etc/debian_version
      # while others have '6.0.7'
      os=`cat /etc/issue | head -1 | awk '{ print tolower($1) }'`
      if grep -q '/' /etc/debian_version; then
        dist=`cut --delimiter='/' -f1 /etc/debian_version`
      else
        dist=`cut --delimiter='.' -f1 /etc/debian_version`
      fi

    else
      unknown_os
    fi
  fi

  if [ -z "$dist" ]; then
    unknown_os
  fi

  # remove whitespace from OS and dist name
  os="${os// /}"
  dist="${dist// /}"

  # os and dist are plugged directly into request URLs below, so reject
  # anything that isn't a plain identifier (this also catches the case
  # where only one of os=/dist= was set, leaving the other blank).
  if ! [[ "$os" =~ ^[A-Za-z0-9_.-]+$ ]] || ! [[ "$dist" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    unknown_os
  fi

  echo "Detected operating system as $os/$dist."
}

detect_apt_version ()
{
  apt_version_full=`apt-get -v | head -1 | awk '{ print $2 }'`
  apt_version_major=`echo $apt_version_full | cut -d. -f1`
  apt_version_minor=`echo $apt_version_full | cut -d. -f2`
  apt_version_modified="${apt_version_major}${apt_version_minor}0"

  echo "Detected apt version as ${apt_version_full}"
}

apt_get_update ()
{
  # apt-get update locks /var/lib/apt/lists/lock, which DPkg::Lock::Timeout
  # does not cover, so apt itself will not wait or retry here. Retry it
  # ourselves, but only when the output says another process currently
  # holds the lock. apt uses the same "Unable to lock directory" wording
  # for permission-denied and read-only-filesystem errors too, so matching
  # on that alone would retry failures that waiting can never fix. Any
  # other apt-get update error is returned right away instead of being
  # retried for the full dpkg_lock_timeout budget.
  local elapsed=0
  local interval=3
  local output

  echo -n "Running apt-get update... "
  while true; do
    # DPkg::Lock::Timeout has no effect here (see comment above), so it is
    # intentionally left off this call. LC_ALL=C keeps apt's error text in
    # English so the lock-contention check below is reliable regardless of
    # the system's locale.
    output=`LC_ALL=C apt-get update 2>&1`
    if [ "$?" -eq "0" ]; then
      echo "done."
      return 0
    fi

    if ! echo "$output" | grep -qiE "held by process|resource temporarily unavailable"; then
      echo
      echo "Warning: apt-get update failed:"
      echo "$output"
      return 1
    fi

    if [ "$elapsed" -ge "$dpkg_lock_timeout" ]; then
      echo
      echo "Warning: apt-get update did not complete within ${dpkg_lock_timeout} seconds while waiting for the apt lock."
      echo "Your package lists may be out of date. You can override this timeout by setting dpkg_lock_timeout= prior to running this script."
      return 1
    fi

    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
}

main ()
{
  # Number of seconds to wait for apt/dpkg locks before giving up: used both
  # as apt's DPkg::Lock::Timeout (covers the dpkg lock, e.g. while installing
  # packages) and as the retry budget for apt-get update when it is blocked
  # on the apt lock specifically (see apt_get_update above). Set and
  # validated first, before curl_check/gpg_check/install_debian_keyring run
  # their own apt-get install calls, since they need this value too.
  # Override by setting dpkg_lock_timeout= prior to running this script,
  # e.g.: dpkg_lock_timeout=600 ./script.sh
  dpkg_lock_timeout="${dpkg_lock_timeout:-300}"

  # dpkg_lock_timeout must be a whole number of seconds. Negative values
  # (e.g. apt's own "-1 = wait forever") are intentionally rejected too:
  # this script exists to bound how long automated, non-interactive runs
  # wait, so an unbounded wait is not a supported setting here.
  if ! [[ "$dpkg_lock_timeout" =~ ^[0-9]+$ ]]; then
    echo "The dpkg_lock_timeout value \"${dpkg_lock_timeout}\" is not valid."
    echo "dpkg_lock_timeout must be a whole number of seconds (0 or greater)."
    echo "For example: dpkg_lock_timeout=600 ./script.sh"
    exit 1
  fi

  detect_os
  curl_check
  gpg_check
  detect_apt_version

  # Need to first run apt-get update so that apt-transport-https can be
  # installed
  apt_get_update

  # Install the debian-archive-keyring package on debian systems so that
  # apt-transport-https can be installed next
  install_debian_keyring

  echo -n "Installing apt-transport-https... "
  apt-get install -y apt-transport-https -o DPkg::Lock::Timeout=${dpkg_lock_timeout} &> /dev/null
  echo "done."


  gpg_key_url="https://packagecloud.io/ookla/speedtest-cli/gpgkey"
  apt_config_url="https://packagecloud.io/install/repositories/ookla/speedtest-cli/config_file.list?os=${os}&dist=${dist}&source=script"

  apt_source_path="/etc/apt/sources.list.d/ookla_speedtest-cli.list"
  apt_keyrings_dir="/etc/apt/keyrings"
  if [ ! -d "$apt_keyrings_dir" ]; then
    install -d -m 0755 "$apt_keyrings_dir"
  fi
  gpg_keyring_path="$apt_keyrings_dir/ookla_speedtest-cli-archive-keyring.gpg"
    gpg_key_path_old="/etc/apt/trusted.gpg.d/ookla_speedtest-cli.gpg"

  echo -n "Installing $apt_source_path..."

  # create an apt config file for this repository
  curl -sSf "${apt_config_url}" > $apt_source_path
  curl_exit_code=$?

  if [ "$curl_exit_code" = "22" ]; then
    echo
    echo
    echo -n "Unable to download repo config from: "
    echo "${apt_config_url}"
    echo
    echo "This usually happens if your operating system is not supported by "
    echo "packagecloud.io, or this script's OS detection failed."
    echo
    echo "You can override the OS detection by setting os= and dist= prior to running this script."
    echo "You can find a list of supported OSes and distributions on our website: https://packagecloud.io/docs#os_distro_version"
    echo
    echo "For example, to force Ubuntu Trusty: os=ubuntu dist=trusty ./script.sh"
    echo
    echo "If you are running a supported OS, contact the owner of this repository/package for further support."
    [ -e $apt_source_path ] && rm $apt_source_path
    exit 1
  elif [ "$curl_exit_code" = "35" -o "$curl_exit_code" = "60" ]; then
    echo "curl is unable to connect to packagecloud.io over TLS when running: "
    echo "    curl ${apt_config_url}"
    echo "This is usually due to one of two things:"
    echo
    echo " 1.) Missing CA root certificates (make sure the ca-certificates package is installed)"
    echo " 2.) An old version of libssl. Try upgrading libssl on your system to a more recent version"
    echo
    echo "Please contact the owner of this repository/package with information about your system for help."
    [ -e $apt_source_path ] && rm $apt_source_path
    exit 1
  elif [ "$curl_exit_code" -gt "0" ]; then
    echo
    echo "Unable to run: "
    echo "    curl ${apt_config_url}"
    echo
    echo "Double check your curl installation and try again."
    [ -e $apt_source_path ] && rm $apt_source_path
    exit 1
  else
    echo "done."
  fi


  echo -n "Importing packagecloud gpg key... "
  # import the gpg key
  curl -fsSL "${gpg_key_url}" | gpg --dearmor > ${gpg_keyring_path}
  # grant 644 permisions to gpg keyring path
  chmod 0644 "${gpg_keyring_path}"

  # move gpg key to old path if apt version is older than 1.1
  if [ "${apt_version_modified}" -lt 110 ]; then
    # move to trusted.gpg.d

    mv ${gpg_keyring_path} ${gpg_key_path_old}
    # grant 644 permisions to gpg key path
    chmod 0644 "${gpg_key_path_old}"

    # deletes the keyrings directory if it is empty
    if ! ls -1qA $apt_keyrings_dir | grep -q .;then
      rm -r $apt_keyrings_dir
    fi
    echo "Packagecloud gpg key imported to ${gpg_key_path_old}"
  else
    echo "Packagecloud gpg key imported to ${gpg_keyring_path}"
  fi
  echo "done."

  # update apt on this system
  apt_get_update

  echo
  echo "The repository is setup! You can now install packages."
}

main


