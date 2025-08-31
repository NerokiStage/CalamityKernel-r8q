#!/bin/bash

TOOLCHAIN_PATH="/home/neroki/proton-clang"
ANYKERNEL_DIR="AnyKernel3"

export USE_CCACHE=1
export CCACHE_EXEC=/usr/bin/ccache

GREEN="\e[1;32m"
RED="\e[1;31m"
YELLOW="\e[1;33m"
CYAN="\e[1;36m"
PURPLE="\e[1;35m"
DEFAULT="\e[0m"

clear
echo -e "${PURPLE}=======================================================${DEFAULT}"
echo -e "${PURPLE}  ~|~  R I T U A L   D E   C A L A M I D A D E  ~|~   ${DEFAULT}"
echo -e "${PURPLE}=======================================================${DEFAULT}"
echo ""

if [ ! -d "$TOOLCHAIN_PATH" ]; then
    echo -e "${RED}AVISO: A ferramenta unificada (Proton Clang) não foi encontrada em: ${TOOLCHAIN_PATH}${DEFAULT}"
    exit 1
fi
if [ ! -f "arch/arm64/configs/calamity_defconfig" ]; then
    echo -e "${RED}AVISO: O Pergaminho de Configuração 'calamity_defconfig' não foi encontrado!${DEFAULT}"
    echo -e "${RED}Execute o script 'prepara_config.sh' para criá-lo.${DEFAULT}"
    exit 1
fi
if [ ! -d "$ANYKERNEL_DIR" ]; then
    echo -e "${RED}AVISO: O Receptáculo '${ANYKERNEL_DIR}' está ausente.${DEFAULT}"
    exit 1
fi

export ARCH=arm64
export KBUILD_BUILD_USER="Ordo Realitas"
export KBUILD_BUILD_HOST="Agente de Campo"
export PATH="${TOOLCHAIN_PATH}/bin:${PATH}"
export CROSS_COMPILE="aarch64-linux-gnu-"
export CROSS_COMPILE_COMPAT="arm-linux-gnueabi-"

prompt() {
    echo -e "${YELLOW}==============================================${DEFAULT}"
    echo -e "${YELLOW}$1${DEFAULT}"
    echo -e "${YELLOW}----------------------------------------------${DEFAULT}"
    shift
    for option in "$@"; do
        echo -e "${GREEN}$option${DEFAULT}"
    done
    echo -e "${YELLOW}==============================================${DEFAULT}"
}

yes_no_prompt() {
    local var_name=$1
    local message=$2
    local choice
    prompt "$message" "Confirmar" "Negar (padrão)"
    read -p " - Sua ordem: " choice
    choice=$(echo "$choice" | tr '[:upper:]' '[:lower:]')
    
    if [[ "$choice" == "y" || "$choice" == "yes" || "$choice" == "confirmar" ]]; then
        eval "$var_name=true"
    else
        eval "$var_name=false"
    fi
}

model_choice="r8q"
echo -e "${GREEN}>>> Alvo do Ritual: Dispositivo ${CYAN}${model_choice}${DEFAULT}. A Realidade será moldada para ele."
echo ""

yes_no_prompt "PERMISSIVE" "Enfraquecer a Membrana do Sistema? (SELinux Permissivo)"

echo -e "${YELLOW}>>> Insira o codinome para esta Manifestação de Calamidade:${DEFAULT}"
read -p " - Nome do Artefato: " KERNEL_NAME

# Sussurra o nome para o bot monitor e continua
echo "$KERNEL_NAME" > .kernel_name_tmp &

if [ -z "$KERNEL_NAME" ]; then
    KERNEL_NAME="Calamidade-${model_choice}"
fi

DATE_START=$(date +"%s")

CONFIG_FILES="calamity_defconfig"
BUILD_ENV="O=out LLVM=1 LLVM_IAS=1 KCFLAGS=-fno-integrated-as"

if [ "$PERMISSIVE" = true ]; then
    echo "CONFIG_SECURITY_SELINUX_DEVELOP=y" >> arch/arm64/configs/$CONFIG_FILES
    echo "CONFIG_SECURITY_SELINUX_PERMISSIVE=y" >> arch/arm64/configs/$CONFIG_FILES
    echo -e "${CYAN}>>> A Membrana do Sistema será afinada. Defesas reduzidas.${DEFAULT}"
fi

echo -e "${GREEN}>>> Decifrando os Símbolos de Configuração...${DEFAULT}"
make ${BUILD_ENV} ${CONFIG_FILES}
make ${BUILD_ENV} olddefconfig

echo -e "${PURPLE}=======================================================${DEFAULT}"
echo -e "${PURPLE}    INICIANDO O RITUAL DE MANIFESTAÇÃO... CUIDADO.    ${DEFAULT}"
echo -e "${PURPLE}=======================================================${DEFAULT}"
make -j$(nproc --all) ${BUILD_ENV}

IMAGE="out/arch/arm64/boot/Image"
DTBO="out/arch/arm64/boot/dtbo.img"
DTB_DIR="out/arch/arm64/boot/dts/vendor/qcom"

if [ -f "$IMAGE" ]; then
    echo -e "${GREEN}>>> O Símbolo foi manifestado! Selando a energia no Receptáculo...${DEFAULT}"
    
    rm -f "${ANYKERNEL_DIR}/Image.gz-dtb" "${ANYKERNEL_DIR}/Image" "${ANYKERNEL_DIR}/dtb" "${ANYKERNEL_DIR}/dtbo.img"
    
    cp "$IMAGE" "${ANYKERNEL_DIR}/Image"
    cat "$DTB_DIR"/*.dtb > "${ANYKERNEL_DIR}/dtb"
    
    if [ -f "$DTBO" ]; then
        cp "$DTBO" "${ANYKERNEL_DIR}/dtbo.img"
    fi
    
    cd "$ANYKERNEL_DIR"
    rm -f *.zip
    zip -r9 "${KERNEL_NAME}.zip" .
    cd ..
    
    echo -e "${GREEN}=======================================================${DEFAULT}"
    echo -e "${GREEN}     RITUAL CONCLUÍDO. A REALIDADE FOI ALTERADA.     ${DEFAULT}"
    echo -e "${GREEN}  Artefato: ${CYAN}${ANYKERNEL_DIR}/${KERNEL_NAME}.zip${DEFAULT}"
    echo -e "${GREEN}=======================================================${DEFAULT}"
else
    echo -e "${RED}=======================================================${DEFAULT}"
    echo -e "${RED}     A MEMBRANA SE ROMPEU! O RITUAL FOI CORROMPIDO.    ${DEFAULT}"
    echo -e "${RED} Sinais do Outro Lado detectados nos logs. Análise necessária. ${DEFAULT}"
    echo -e "${RED}=======================================================${DEFAULT}"
    exit 1
fi

DATE_END=$(date +"%s")
DIFF=$(($DATE_END - $DATE_START))
echo -e "${YELLOW}>>> O Ritual de Calamidade durou: $(($DIFF / 60)) minuto(s) e $(($DIFF % 60)) segundos de distorção temporal.${DEFAULT}"

