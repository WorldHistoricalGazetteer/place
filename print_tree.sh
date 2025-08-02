#!/bin/bash

root="/ix1/whcdh/data"

print_tree() {
  local dir="$1"
  local prefix="$2"
  local is_last="$3"

  # Count and size
  local count size
  count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l)
  size=$(du -sh "$dir" 2>/dev/null | cut -f1)
  [ -z "$size" ] && size="??"

  local word="file"
  [ "$count" -ne 1 ] && word="files"

  local connector="├──"
  [ "$is_last" = true ] && connector="└──"

  echo "${prefix}${connector} [$size] $(basename "$dir") ($count $word)"

  # List subdirectories safely
  local subdirs=()
  while IFS= read -r sub; do
    subdirs+=("$sub")
  done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)

  local total=${#subdirs[@]}
  for i in "${!subdirs[@]}"; do
    local last=false
    [ "$i" -eq $((total - 1)) ] && last=true

    local new_prefix="$prefix"
    if [ "$is_last" = true ]; then
      new_prefix+="    "
    else
      new_prefix+="│   "
    fi

    print_tree "${subdirs[$i]}" "$new_prefix" "$last"
  done
}

# Run
echo "$root"
print_tree "$root" "" true
