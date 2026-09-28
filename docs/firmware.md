# Firmware, CPU cores and GPU routing

These are three separate operations: flashing firmware, configuring CPU/memory settings, and enabling additional GPU execution units. This page records the tested sequence; it is not a universal flash recipe.

## Recovery came first

The board originally reported AMI P3.00, dated 2021-12-09, with a 16 MiB SPI image. Two independent software reads matched byte-for-byte. The original image, CMOS baseline, boot files, kernel module and service configuration were copied off-board before modification.

The operator had physical access and a BIOS programmer. Software identified multiple compatible Macronix chip definitions; that did not establish the exact chip part number or programmer voltage. Identify those from the actual hardware before attempting external recovery. A ROM backup does not also back up CMOS settings.

Device-specific dumps and recovery bundles are deliberately private. Never substitute another board's recovery image for your own backup.

## Firmware used

The operator followed the USB/UEFI workflow from [Forbidden-Darkness](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script), release **v0.5.0**. The archive and README-linked launcher were verified against GitHub release asset digests before extraction:

| Artifact | SHA-256 |
|---|---|
| `release-0.5.0.7z` | `05cca62227ccb3cc953ef883457fc20867d4c3e2af053d2106036be76c8d52c0` |
| `reboot-uefi-v2.0.sh` | `6f3852e697841a540ef28582ebc374bac0e415e67627820ddb55ad8b03b5be9c` |

The requested release files were extracted unchanged to a FAT32 USB. Its existing EFI bootloader was backed up before replacement, and an independent original-ROM copy was added. All 23 extracted files were checked against the staged release.

Two version-specific issues were found during review:

- The launcher reboot path assumes Bazzite/Fedora and can prioritize entry `0003`. On this Ubuntu system, the one-time USB boot target was set directly while preserving the existing Ubuntu boot order.
- The UEFI menu prints a success message without checking AFU's result. Check AFU's actual output before accepting a reset. Menu `0f` exports a backup; `01` selects the no-logo firmware. These labels are specific to this release.

The package's no-logo image differs from a separately reconstructed RescueMei upstream image. Matching the package's release digest establishes download integrity; it does not establish image equivalence or silicon stability. Do not mix their checksums.

The operator performed the flash locally and configured the BIOS. Linux verified **8 CPU cores / 16 threads** and, after the memory experiment, **8 GiB reserved GPU memory**. The exact BIOS menu field labels were not captured. Changing memory settings temporarily returned the CPU to 6/12; a later BIOS visit restored 8/16. Always verify both after a reboot.

The SMBIOS version string still reads P3.00. That string alone cannot distinguish the modified image from the original.

## Live 40-CU GPU unlock

Used [WinnieLV/bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), pinned to:

```
a929085d791f126ce76a60eb609610820fb08066
```

Its dependency [UMR](https://gitlab.freedesktop.org/tomstdenis/umr) was built from:

```
8438c15273f873aa7b06d5e68cf377b76ff617f1
```

UMR was installed under `/opt/bc250-mod-prep/umr` with GUI, server and LLVM disassembly disabled. The stock amdgpu kernel module was retained. The tool auto-detected the GPU's DRI instance, so no fixed card number is required in the boot configuration.

After reviewing the script and stopping inference, the operation was:

```bash
export UMR=/opt/bc250-mod-prep/umr/bin/umr
sudo --preserve-env=UMR bash ./bc250-cu-live-manager.sh status
sudo --preserve-env=UMR bash ./bc250-cu-live-manager.sh --yes --dry-run enable all
# Actual register writes; run only after reviewing the dry-run and recovery plan:
sudo --preserve-env=UMR bash ./bc250-cu-live-manager.sh --yes enable all
```

| Per-array register readback | Factory routing | Full routing |
|---|---|---|
| CC harvest mask | `0xfff80000` | `0xffe00000` |
| SPI WGP dispatch mask | `0x07` | `0x1f` |
| Routed CUs per array | 6 | 10 |
| Total across four arrays | 24 | 40 |

The script also updates the RLC mask. Do not infer all register behavior from the table alone or hand-copy writes onto other hardware.

`vulkaninfo` and amdgpu retained the original 24-CU topology. Register readback, compute correctness and a paired throughput measurement were used together to verify the live change. The [benchmark notes](benchmarks.md) describe those checks.

No GPU clock or voltage tuning was applied in this build. Some sysfs clock readings were inconsistent after flashing, so they were not used to claim actual operating frequency. Temperature readings reported here are the exposed GPU edge sensor.

## Persistence

After the temporary tests passed, the current table was saved and the upstream service installed:

```bash
sudo --preserve-env=UMR bash ./bc250-cu-live-manager.sh --yes write-service-table
sudo --preserve-env=UMR bash ./bc250-cu-live-manager.sh --yes install-service
```

The saved configuration contains four `0x1f` masks. A systemd drop-in makes the AI service want and start after `bc250-cu-live-manager.service`; a second drop-in sets a 60-second startup timeout for the unlock service. See [configuration examples](../config/).

`Wants=` allows the AI API to start if the unlock fails. That is intentional availability behavior, so service availability alone does not prove 40 CUs are active. Inspect the unlock service and register readback.

Validation was performed both by restoring 24-CU routing and starting the service chain, and by an actual reboot. After reboot: eight CPU cores, 40 routed CUs, 8/8 memory allocation, and successful LAN inference.

This is software persistence: the saved table is reapplied on startup. It does not permanently alter hardware fuses.

## Rollback

To disable startup replay, stop inference, disable the CU service, remove the AI service's CU dependency drop-in, reload systemd and restore stock dispatch with the reviewed manager. A reboot without replay restores driver initialization state. Disabling the CU service alone is insufficient if another unit still pulls it in through `Wants=`.

A frozen system may require a physical reset. Do not enable startup replay until temporary operation is verified on the particular board. The eight CPU cores and firmware recovery path are separate from this GPU runtime rollback.

## Later memory-layout experiment

The subsequent [Q36 evaluation](q36.md) changed the GPU reservation from 8 GiB to 512 MiB and expanded GTT/TTM limits. CPU and GPU unlocks survived the reboot. The earlier 8/8 results above remain historical measurements; the new layout is now installed.
