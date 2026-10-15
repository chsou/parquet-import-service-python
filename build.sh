#!/usr/bin/env bash
# Copyright (c) 2026 Christoph Souris
set -euo pipefail

# --- colors for terminals, honoring NO_COLOR ---
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  cr=$'\033[0;31m'
  cg=$'\033[0;32m'
  cy=$'\033[1;33m'
  cc=$'\033[0;36m'
  nc=$'\033[0m'
else
  cr='' cg='' cy='' cc='' nc=''
fi

# --- read command line options ---
name=""
version=""
isolation=""
provider=""

# fails unless option $1 has a value $2
assert_arg() { [[ -n "${2:-}" && "$2" != -* ]] || { echo "${cr}Parameter $1 needs an argument.${nc}" >&2; exit 2; }; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      echo "Usage: build.sh -n <name> -v <version> -i <isolation> -p <provider>"
      exit 0
      ;;
    -n|--name)      assert_arg "$@"; name="$2";      shift 2 ;;
    -v|--version)   assert_arg "$@"; version="$2";   shift 2 ;;
    -i|--isolation) assert_arg "$@"; isolation="$2"; shift 2 ;;
    -p|--provider)  assert_arg "$@"; provider="$2";  shift 2 ;;
    *) echo "${cr}Unknown parameter: $1${nc}"; exit 2 ;;
  esac
done

[[ -z "$name" ]]      && { echo "${cr}Missing name parameter (-n/--name).${nc}";            exit 2; }
[[ -z "$version" ]]   && { echo "${cr}Missing version parameter (-v/--version).${nc}";      exit 2; }
[[ -z "$isolation" ]] && { echo "${cr}Missing isolation parameter (-i/--isolation).${nc}";  exit 2; }
[[ -z "$provider" ]]  && { echo "${cr}Missing provider parameter (-p/--provider).${nc}";    exit 2; }

# --- Target is ALWAYS linux/amd64 for Cumulocity; host may differ ---
target_platform="linux/amd64"

host_arch="$(uname -m)"
img_name="$(echo "$name" | tr '[:upper:]' '[:lower:]' | tr '[:punct:]' '-')"
img_tag="local/$img_name:$version"

build_dir="./build"
dist_dir="./dist"
target="$dist_dir/$img_name.zip"

echo "Name: $name, Image Name: $img_name, Version: $version, Isolation: $isolation, Provider: $provider"
echo "Build directory:    $build_dir"
echo "Target location:    $target"
echo "Host Architecture:  $host_arch"
echo "Target platform:    $target_platform"
echo "Image tag (docker): $img_tag"
echo ""

[[ -d "src" ]] || { echo "${cr}This script must be run from the project base directory.${nc}"; exit 2; }

# --- Prepare directories ---
rm -rf "$build_dir" "$dist_dir"
mkdir -p "$build_dir" "$dist_dir"

# --- Copy & render sources (portable sed) ---
cp ./pyproject.toml ./uv.lock "$build_dir"
cp -r src/main "$build_dir"
cp ./src/cumulocity.json "$build_dir/cumulocity.json"
cp ./src/Dockerfile "$build_dir/Dockerfile"

# Portable in-place edit: write to a temp file, then move (works on GNU + BSD sed)
render() {
  local file="$1"
  sed -e "s/{VERSION}/$version/g" \
      -e "s/{ISOLATION}/$isolation/g" \
      -e "s/{PROVIDER}/$provider/g" \
      "$file" > "$file.tmp" && mv "$file.tmp" "$file"
}
render "$build_dir/cumulocity.json"

# --- Build image (always amd64 target, load into local docker) ---
echo "${cc}Building image ($target_platform) ...${nc}"
docker buildx build \
  --platform "$target_platform" \
  --load \
  -t "$img_tag" \
  "$build_dir"
docker save -o "$dist_dir/image.tar" "$img_tag"


# --- Verify image platform ---
echo "${cc}Verifying image platform ...${nc}"
image_os="$(docker inspect --format '{{.Os}}' "$img_tag")"
image_arch="$(docker inspect --format '{{.Architecture}}' "$img_tag")"
image_platform="$image_os/$image_arch"
echo "Image platform is: $image_platform"
[[ "$image_platform" == "$target_platform" ]] || { echo "${cr}ERROR: Wrong image platform, expected $target_platform.${nc}"; exit 1; }

# --- Package uploadable archive ---
zip -j "$target" "$build_dir/cumulocity.json" "$dist_dir/image.tar"

echo ""
echo "${cg}Created uploadable archive: $target${nc}"
