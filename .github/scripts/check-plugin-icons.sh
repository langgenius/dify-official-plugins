#!/usr/bin/env bash
set -euo pipefail

# Check every plugin icon in the repository, applying the same validations as
# the "Check Plugin Icon" step in langgenius/dify-plugins:
#   1. The icon declared in manifest.yaml must exist under _assets/
#   2. The icon must not contain the template placeholder text
#   3. The icon must not be the default template icon

if ! command -v yq >/dev/null 2>&1; then
  echo "yq is required" >&2
  exit 1
fi

# Default icon content from the plugin template
DEFAULT_ICON='<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
  <path d="M20 20 V80 M20 20 H60 Q80 20 80 40 T60 60 H20" 
        fill="none" 
        stroke="black" 
        stroke-width="5"/>
</svg>'
DEFAULT_ICON_NORMALIZED=$(echo "$DEFAULT_ICON" | tr -d '\n\r\t ')

ERROR_FILE="${ERROR_FILE:-$(mktemp)}"
: > "$ERROR_FILE"

report_error() {
  echo "$1"
  echo "$1" >> "$ERROR_FILE"
}

check_icon_file() {
  local plugin_path="$1"
  local icon_filename="$2"
  local icon_file="$plugin_path/_assets/$icon_filename"

  # Check if icon file exists
  if [ ! -f "$icon_file" ]; then
    report_error "!!! [$plugin_path] Plugin icon file not found: _assets/$icon_filename"
    return
  fi

  # Check if icon contains template placeholder text
  if grep -q "DIFY_MARKETPLACE_TEMPLATE_ICON_DO_NOT_USE" "$icon_file"; then
    report_error "!!! [$plugin_path] Plugin icon contains template placeholder text 'DIFY_MARKETPLACE_TEMPLATE_ICON_DO_NOT_USE', change default icon before submitting to marketplace."
    return
  fi

  # Check if icon content matches default icon (normalize whitespace)
  local icon_content
  icon_content=$(tr -d '\n\r\t \000' < "$icon_file")
  if [ "$icon_content" = "$DEFAULT_ICON_NORMALIZED" ]; then
    report_error "!!! [$plugin_path] Plugin icon is using the default template icon and must be customized"
  fi
}

check_plugin() {
  local manifest="$1"
  local plugin_path
  plugin_path=$(dirname "$manifest")

  # Get icon filename from manifest.yaml
  local icon_filename
  icon_filename=$(yq '.icon' "$manifest")
  if [ -z "$icon_filename" ] || [ "$icon_filename" = "null" ]; then
    report_error "!!! [$plugin_path] manifest.yaml does not declare an icon"
    return
  fi
  check_icon_file "$plugin_path" "$icon_filename"

  # Check dark icon if declared
  local icon_dark_filename
  icon_dark_filename=$(yq '.icon_dark' "$manifest")
  if [ -n "$icon_dark_filename" ] && [ "$icon_dark_filename" != "null" ]; then
    check_icon_file "$plugin_path" "$icon_dark_filename"
  fi
}

checked=0
while IFS= read -r manifest; do
  check_plugin "$manifest"
  checked=$((checked + 1))
done < <(find . -mindepth 3 -maxdepth 3 -name manifest.yaml -not -path './.scripts/*' | sort)

echo ""
echo "Checked $checked plugin(s)."

if [ -s "$ERROR_FILE" ]; then
  echo ""
  echo "Icon validation failed:"
  cat "$ERROR_FILE"
  exit 1
fi

echo "All plugin icons passed validation."
