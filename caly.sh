#!/bin/bash

# Define colors
GREEN="\e[1;32m"
RED="\e[1;31m"
YELLOW="\e[1;33m"
MUSTARD="\e[1;33m"
DEFAULT="\e[0m"

LLVM_PATH="/home/ubuntu/tc/clang/bin/"

echo -e "${YELLOW}Digite um nome para o kernel: ${DEFAULT}"
read KERNEL_NAME

if [ -z "$KERNEL_NAME" ]; then
    echo -e "${RED}Nome do kernel não pode ser vazio. Saindo.${DEFAULT}"
    exit 1
fi

echo -e "${YELLOW}Digite 1 para Beta ou 2 para Stable: ${DEFAULT}"
read VERSION_OPTION

if [ "$VERSION_OPTION" != "1" ] && [ "$VERSION_OPTION" != "2" ]; then
    echo -e "${RED}Opção inválida. Saindo.${DEFAULT}"
    exit 1
fi

if [ "$VERSION_OPTION" == "1" ]; then
    VERSION="Beta"
else
    VERSION="Stable"
fi

TC_PATH="/home/ubuntu/tc/clang/bin/"
GCC_PATH="/usr/bin/"

BUILD_ENV="CC=${TC_PATH}clang CROSS_COMPILE=${GCC_PATH}aarch64-linux-gnu- LLVM=1 LLVM_IAS=1 PATH=$LLVM_PATH:$LLD_PATH:$PATH"  

KERNEL_MAKE_ENV="DTC_EXT=$(pwd)/tools/dtc CONFIG_BUILD_ARM64_DT_OVERLAY=y"

make O=out ARCH=arm64 $BUILD_ENV r8q_defconfig

DATE_START=$(date +"%s")

echo -e "${MUSTARD}***********************************************${DEFAULT}"
echo -e "${MUSTARD}          Compiling CalamityKernel                ${DEFAULT}"
echo -e "${MUSTARD}***********************************************${DEFAULT}"

make -j$(nproc --all) O=out ARCH=arm64 $KERNEL_MAKE_ENV $BUILD_ENV Image.gz

make -j$(nproc --all) O=out ARCH=arm64 $KERNEL_MAKE_ENV $BUILD_ENV dtbs

DTB_OUT="out/arch/arm64/boot/dts/vendor/qcom"
IMAGE="out/arch/arm64/boot/Image.gz"

cat $DTB_OUT/*.dtb > AnyKernel3/dtb

DATE_END=$(date +"%s")
DIFF=$(($DATE_END - $DATE_START))
echo -e "${GREEN}Tempo de compilação: $(($DIFF / 60)) minutos(s) and $(($DIFF % 60)) segundos.${DEFAULT}"

echo -e "${MUSTARD}***********************************************${DEFAULT}"
echo -e "${MUSTARD}                Zipping Kernel                 ${DEFAULT}"
echo -e "${MUSTARD}***********************************************${DEFAULT}"

cp $IMAGE AnyKernel3/Image.gz
cd AnyKernel3
rm *.zip
zip -r9 "${VERSION}-${KERNEL_NAME}.zip" .

echo -e "${MUSTARD}***********************************************${DEFAULT}"
echo -e "${MUSTARD}                 Cleaning up                   ${DEFAULT}"
echo -e "${MUSTARD}***********************************************${DEFAULT}"

cd ../