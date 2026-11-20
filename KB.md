# octo-observability-demo knowledge base

Troubleshooting reference. Read it only when an error occurs, not at session start.
Cross-cutting OCI, OKE, IAM and networking issues live in the shared OCI-DEMO KB: `~/dev/OCI-DEMO/KB.md`
(search it with `python3.11 ~/dev/OCI-DEMO/scripts/knowledge_lookup.py --query '<error>'`).

Add an entry after every error that needed investigation and a fix. Use the next number.

## Entry format

```
## KB-NNN: <component> - <short symptom>
- Error: <exact message>
- Root cause: <what was actually wrong>
- Fix: <what changed, with file/command>
- Prevention: <how to avoid it next time>
```

## Resource Manager validation on macOS

- Symptom. `terraform validate` reports `Unrecognized remote plugin message`. Terraform debug output shows `listen unix ... bind: invalid argument` when the provider socket path exceeds the macOS limit.
- Resolution. Set `PLUGIN_UNIX_SOCKET_DIR=.` while running Terraform in the configuration directory. Keep `TMPDIR` in the approved scratch directory.
- Verification. Run `terraform init -backend=false` and `terraform validate` against the source and extracted archive with a CLI version that satisfies `required_version`.
