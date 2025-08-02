#!/bin/bash

root="/ix1/whcdh/data"

print_tree() {
  local dir="$1"
  local prefix="$2"
  local is_last="$3"

  # Count and size
  count=$(find "$dir" -maxdepth 1 -type f | wc -l)
  size=$(du -sh "$dir" 2>/dev/null | cut -f1)
  word="file"; [ "$count" -ne 1 ] && word="files"

  # Tree connector
  connector="├──"
  [ "$is_last" = true ] && connector="└──"

  echo "${prefix}${connector} [$size] $(basename "$dir") ($count $word)"

  # Get list of subdirs manually
  IFS=$'\n' read -d '' -r -a subdirs < <(find "$dir" -mindepth 1 -maxdepth 1 -type d | sort && printf '\0')
  local total=${#subdirs[@]}

  for i in "${!subdirs[@]}"; do
    local last=false
    [ "$i" -eq $((total - 1)) ] && last=true

    # Update prefix for next level
    local new_prefix="$prefix"
    if [ "$is_last" = true ]; then
      new_prefix+="    "
    else
      new_prefix+="│   "
    fi

    print_tree "${subdirs[$i]}" "$new_prefix" "$last"
  done
}

# Start tree print
echo "$root"
print_tree "$root" "" true
