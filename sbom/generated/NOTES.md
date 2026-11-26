# Image SBOM vulnerability notes

Snapshot: 2026-11-26. These findings remain open under demo-only exceptions e753 and e809. An exception is not a fix or a production acceptance. Scanner results reflect the recorded build-time scans, not a current vulnerability assessment.

The public CycloneDX files contain package identities only and omit scanner paths and private registry coordinates. Each file identifies its image by SHA-256 digest. The Workflow Gateway inventory was regenerated from its registry digest; the other inventories came from the corresponding native build scans.

## e753 findings

These were recorded as fixable by the original scanner. Fix availability and applicability have not been independently verified here.

| Image | Advisory | Package | Severity | Status |
| --- | --- | --- | --- | --- |
| shop | CVE-2026-124851 | `libzstd1` | HIGH | Scanner reported a fix |
| crm | CVE-2026-124851 | `libzstd1` | HIGH | Scanner reported a fix |
| crm | CVE-2026-23949 | `jaraco.context` | HIGH | Scanner reported a fix |
| crm | CVE-2026-24049 | `wheel` | HIGH | Scanner reported a fix |
| studio | CVE-2026-124851 | `libzstd1` | HIGH | Scanner reported a fix |
| studio | CVE-2026-53539 | `python-multipart` | HIGH | Scanner reported a fix |
| studio | CVE-2025-47273 | `setuptools` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-84782 | `libssl3` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-39821 | `golang.org/x/net` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-46600 | `golang.org/x/net` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-78661 | `golang.org/x/net` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-78669 | `golang.org/x/net` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-56851 | `golang.org/x/text` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-56852 | `golang.org/x/text` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-84304 | `google.golang.org/grpc` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-84445 | `google.golang.org/grpc` | HIGH | Scanner reported a fix |
| workflow-gateway | GHSA-hrxh-6v49-42gf | `google.golang.org/grpc` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-111943 | `stdlib` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-78667 | `stdlib` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-78669 | `stdlib` | HIGH | Scanner reported a fix |
| workflow-gateway | CVE-2026-97031 | `stdlib` | HIGH | Scanner reported a fix |

## e809 findings

No scanner-listed fix does not establish that an upstream fix does not exist. SQLcl bundles Guava; Spring lists fixes in OSS 7.0.9 and enterprise 6.2.20.

| Image | Advisory | Package | Severity | Status |
| --- | --- | --- | --- | --- |
| java-apm | CVE-2026-47884 | `org.springframework:spring-webmvc` | CRITICAL | Fix in newer major or enterprise release |
| java-apm | CVE-2026-47890 | `org.springframework:spring-webmvc` | CRITICAL | Fix in newer major or enterprise release |
| coordinator-api | CVE-2026-76642 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-54369 | `libacl1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2025-69720 | `libncursesw6` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-119373 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-119374 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-119379 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-107494 | `libssl3t64` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-124709 | `libssl3t64` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-16742 | `libsystemd0` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2025-69720 | `libtinfo6` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-16742 | `libudev1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `login` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `login` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `login` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `login` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `mount` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `mount` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `mount` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `mount` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2025-69720 | `ncurses-base` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2025-69720 | `ncurses-bin` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-107494 | `openssl` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-124709 | `openssl` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-107494 | `openssl-provider-legacy` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-124709 | `openssl-provider-legacy` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-9538 | `perl-base` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-76642 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78408 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78409 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-78410 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-api | CVE-2026-102554 | `com.google.guava:guava` | HIGH | Vendor-bundled Guava; upstream fix available |
| coordinator-agent | CVE-2026-76642 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-54369 | `libacl1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2025-69720 | `libncursesw6` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-119373 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-119374 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-119379 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-107494 | `libssl3t64` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-124709 | `libssl3t64` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-16742 | `libsystemd0` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2025-69720 | `libtinfo6` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-16742 | `libudev1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `login` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `login` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `login` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `login` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `mount` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `mount` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `mount` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `mount` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2025-69720 | `ncurses-base` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2025-69720 | `ncurses-bin` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-107494 | `openssl` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-124709 | `openssl` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-107494 | `openssl-provider-legacy` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-124709 | `openssl-provider-legacy` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-9538 | `perl-base` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-76642 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78408 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78409 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-78410 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-agent | CVE-2026-102554 | `com.google.guava:guava` | HIGH | Vendor-bundled Guava; upstream fix available |
| coordinator-mcp | CVE-2026-76642 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `bsdutils` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-54369 | `libacl1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `libblkid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `liblastlog2-2` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `libmount1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2025-69720 | `libncursesw6` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `libsmartcols1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-119373 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-119374 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-119379 | `libsqlite3-0` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-107494 | `libssl3t64` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-124709 | `libssl3t64` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-16742 | `libsystemd0` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2025-69720 | `libtinfo6` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-16742 | `libudev1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `libuuid1` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `login` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `login` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `login` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `login` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `mount` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `mount` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `mount` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `mount` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2025-69720 | `ncurses-base` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2025-69720 | `ncurses-bin` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-107494 | `openssl` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-124709 | `openssl` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-107494 | `openssl-provider-legacy` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-124709 | `openssl-provider-legacy` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-9538 | `perl-base` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-76642 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78408 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78409 | `util-linux` | HIGH | No scanner-listed fix |
| coordinator-mcp | CVE-2026-78410 | `util-linux` | HIGH | No scanner-listed fix |
