#!/bin/bash

root="/ix1/whcdh/data"

# Global counters
total_dirs=0
total_files=0
total_bytes=0

print_tree() {
  local dir="$1"
  local prefix="$2"
  local is_last="$3"

  # Count and size
  local count size raw_size
  count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l)
  size=$(du -sh "$dir" 2>/dev/null | cut -f1)
  raw_size=$(du -sb "$dir" 2>/dev/null | cut -f1)
  [ -z "$size" ] && size="??"
  [ -z "$raw_size" ] && raw_size=0

  total_dirs=$((total_dirs + 1))
  total_files=$((total_files + count))
  total_bytes=$((total_bytes + raw_size))

  local word="file"
  [ "$count" -ne 1 ] && word="files"

  local connector="├──"
  [ "$is_last" = true ] && connector="└──"

  echo "${prefix}${connector} [$size] $(basename "$dir") ($count $word)"

  # List subdirectories
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

# Convert bytes to human-readable
format_bytes() {
  local b=$1
  local units=(B K M G T P)
  for unit in "${units[@]}"; do
    if [ "$b" -lt 1024 ]; then
      echo "${b}${unit}"
      return
    fi
    b=$((b / 1024))
  done
  echo "${b}P"
}

# Run
echo "$root"
print_tree "$root" "" true

echo
echo "Summary:"
echo "  Total directories : $total_dirs"
echo "  Total files       : $total_files"
echo "  Total size        : $(format_bytes $total_bytes)"
