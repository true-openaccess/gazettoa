#!/bin/sh
# Install one executable from a release archive, pinned by the archive's SHA-256:
#
#   sh scripts/install-tool.sh URL SHA256 NAME BIN_DIR
#
# The archive (.tar.gz or .zip) is checked before it is opened; the first regular file called
# NAME inside it is copied to BIN_DIR. Used by the workflows for rnl (toa has no release yet and is
# built from its source; see gaze-pages.yml).
set -eu
url=${1-}; sum=${2-}; name=${3-}; bin=${4-}
if [ -z "$url" ] || [ -z "$sum" ] || [ -z "$name" ] || [ -z "$bin" ]; then
  echo "install-tool: no release given for ${name:-the tool}: set its URL and SHA-256" >&2
  exit 2
fi
d=$(mktemp -d)
trap 'rm -rf "$d"' EXIT
curl -fsSL --retry 3 "$url" -o "$d/archive"
echo "$sum  $d/archive" | sha256sum --check --strict --quiet -
mkdir "$d/x"
case "$url" in
  *.zip) unzip -q "$d/archive" -d "$d/x" ;;
  *) tar -xzf "$d/archive" -C "$d/x" ;;
esac
exe=$(find "$d/x" -type f -name "$name" | head -n 1)
if [ -z "$exe" ]; then
  echo "install-tool: no file called $name in $url" >&2
  exit 1
fi
mkdir -p "$bin"
install -m 755 "$exe" "$bin/$name"
"$bin/$name" --version
