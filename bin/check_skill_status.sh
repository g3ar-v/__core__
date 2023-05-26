#! /usr/bin/bash
#
# Define the directory to search
directory_to_search="$1"
echo $directory_to_search

# Loop through each subdirectory
for subdirectory in "$directory_to_search"/*/; do
  # Check if the subdirectory is a Git repository
  if [ -d "$subdirectory/.git" ]; then
    # Change to the subdirectory and check the Git status
    cd "$subdirectory" || exit
    git_status=$(git status)

    # Check if there are uncommitted changes or unpushed commits
    if [[ $git_status == *"Changes not staged for commit"* || $git_status == *"Changes to be committed"* || $git_status == *"Your branch is ahead of"* ]]; then
      # Print the subdirectory name
      echo "$subdirectory"
    fi

    # Change back to the parent directory
    cd "$directory_to_search" || exit
  fi
done
