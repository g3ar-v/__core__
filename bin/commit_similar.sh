#!/usr/bin/env bash

if [ $# -lt 1 ]
  then
    echo "Please provide at least one directory path"
    exit 1
fi

# Get the current directory
current_dir="${0:a:h}"

# Loop through the provided directory paths
for name in "$@"
do 
  # Build the absolute path of the directory to commit to
  dir="$current_dir/$name"
  
  if [ ! -d "$dir" ]
  then
    echo "Directory $dir does not exist"
    exit 1
  fi

  # Change directory to the specified path
  cd $dir 

  echo "Please enter commit type (e.g. feat, fix, docs):"
  read -r type
  echo "Please enter scope (optional):"
  read -r scope
  echo "Please enter commit message:"
  read -r message


  cz commit --type="$type" --scope="$scope" --message="$message"
done
