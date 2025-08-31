#!/bin/bash

# --- SCRIPT DE USO ÚNICO PARA CRIAR O ARQUIVO DE CONFIGURAÇÃO ---

TOOLCHAIN_PATH="/home/neroki/proton-clang"

# Cores
GREEN="\e[1;32m"
YELLOW="\e[1;33m"

# Configurando o ambiente completo
export ARCH=arm64
export PATH="${TOOLCHAIN_PATH}/bin:${PATH}"
export CROSS_COMPILE="aarch64-linux-gnu-"

echo -e "${YELLOW}Iniciando Ritual de Preparação... limpando a área.${DEFAULT}"
make O=out ARCH=arm64 LLVM=1 mrproper

echo -e "${YELLOW}Aplicando configurações base...${DEFAULT}"
make O=out ARCH=arm64 LLVM=1 vendor/kona-sec-perf_defconfig vendor/samsung/r8q.config

echo -e "${YELLOW}Abrindo menu de configuração. Apenas salve e saia.${DEFAULT}"
sleep 2
make O=out ARCH=arm64 LLVM=1 menuconfig
# Instrução: Na tela azul, navegue até <Save>, aperte Enter, confirme e depois navegue até <Exit> e saia.

echo -e "${YELLOW}Copiando a configuração final...${DEFAULT}"
cp out/.config arch/arm64/configs/calamity_defconfig

echo -e "${GREEN}Pergaminho 'calamity_defconfig' criado com sucesso!${DEFAULT}"
echo -e "${GREEN}Você já pode usar o script principal 'ritual_calamidade.sh' para compilar.${DEFAULT}"