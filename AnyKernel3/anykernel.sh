# AnyKernel3 Ramdisk Mod Script
# osm0sis @ xda-developers

## AnyKernel setup
# begin properties
properties() { '
kernel.string=CalamityKernel by Neroki
do.devicecheck=1
do.modules=0
do.systemless=1
do.cleanup=1
do.cleanuponabort=0
device.name1=r8q
device.name2=r8qxx
device.name3=r8qxxx
supported.versions=11 - 16
supported.patchlevels=
'; } # end properties

# shell variables
block=/dev/block/platform/soc/1d84000.ufshc/by-name/boot;
is_slot_device=0;
ramdisk_compression=auto;

## AnyKernel methods (DO NOT CHANGE)
# import patching functions/variables - see for reference
. tools/ak3-core.sh;

## AnyKernel file attributes
# set permissions/ownership for included ramdisk files
set_perm_recursive 0 0 755 644 $ramdisk/*;
set_perm_recursive 0 0 750 750 $ramdisk/init* $ramdisk/sbin;

## AnyKernel boot install
dump_boot;

# begin kernel/dtb/dtbo changes
oneui=$(file_getprop /system/build.prop ro.build.version.oneui);
gsi=$(file_getprop /system/build.prop ro.product.system.device);
if [ -n "$oneui" ]; then
    ui_print " "
    ui_print " • ROM OneUI detectada! • "
    ui_print " • Adaptando sensor de digital... • "
    patch_cmdline "android.is_aosp" "android.is_aosp=0";
elif [ $gsi == generic ]; then
    ui_print " "
    ui_print " • ROM GSI detectada! • "
    ui_print " • Adaptando sensor de digital... • "
    patch_cmdline "android.is_aosp" "android.is_aosp=0";
else
    ui_print " "
    ui_print " • ROM AOSP detectada! • "
    ui_print " • Adaptando sensor de digital... • "
    patch_cmdline "android.is_aosp" "android.is_aosp=1";
fi

write_boot;
## end boot install