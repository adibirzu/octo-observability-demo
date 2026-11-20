#!/usr/bin/env bash
# Shared packager for the unified and shop-only ORM wrappers.
set -euo pipefail

wrapper="$1"
shift
case "$#" in
    0) build_dir="$wrapper/build" ;;
    2) [[ "$1" == "--output-dir" && -n "$2" ]] || exit 2
       build_dir="$2" ;;
    *) echo "Expected --output-dir DIR" >&2; exit 2 ;;
esac

mkdir -p "$build_dir"
build_dir="$(cd "$build_dir" && pwd)"
stage="$(mktemp -d "$build_dir/stage.XXXXXX")"
trap 'rm -rf "$stage"' EXIT
stack="$stage/stack"
upstream="$(cd "$wrapper/../terraform" && pwd)"
mkdir -p "$stack/modules-shared"
cp "$wrapper/"main.tf "$wrapper/"variables.tf "$wrapper/"schema.yaml "$stack/"
cp "$upstream/"*.tf "$stack/modules-shared/"
(
    cd "$upstream"
    while IFS= read -r -d '' module_file; do
        mkdir -p "$stack/modules-shared/$(dirname "$module_file")"
        cp "$module_file" "$stack/modules-shared/$module_file"
    done < <(find modules -type f -name '*.tf' ! -name backend.tf ! -path '*/.*' -print0)
)
find "$stack" -name backend.tf -type f -delete
sed -i.bak 's#source = "\.\./terraform"#source = "./modules-shared"#' "$stack/main.tf"
rm "$stack/main.tf.bak"

(cd "$stack" && zip -qr "$stage/octo-stack.zip" .)
mv -f "$stage/octo-stack.zip" "$build_dir/octo-stack.zip"
echo "Packaged: $build_dir/octo-stack.zip"
