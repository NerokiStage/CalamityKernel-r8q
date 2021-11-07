import os
import sys
import subprocess
import time
import asyncio
import threading
import re
import hashlib
import math
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

DEFAULT_ESTIMATED_BUILD_TIME_SECONDS = 900
CONFIG_FILE = ".bot_env"
BUILD_SCRIPT = "./caly.sh"
LOG_FILE = "build.log"
NAME_FILE = ".kernel_name_tmp"
TIME_FILE = ".last_build_time"
BUILD_HISTORY_COUNT = 5

build_status = {
    "running": False,
    "progress": 0.0,
    "elapsed_str": "0m 0s",
    "log_snippet": "Aguardando início...",
    "start_time": 0,
    "kernel_name": "N/A",
}
status_lock = threading.Lock()
stop_event = asyncio.Event()

def clean_log_for_telegram(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned_text = ansi_escape.sub('', text)
    escape_chars = r"_*[]()~`>#+-=|{}.!-"
    cleaned_text = re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', cleaned_text)
    return cleaned_text

def clean_log_for_code_block(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned_text = ansi_escape.sub('', text)
    escape_chars = r">#+-=|{}.!-"
    cleaned_text = re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', cleaned_text)
    return cleaned_text

def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        return "Não foi possível calcular"

def load_config():
    bot_token, chat_ids, authorized_users = None, [], []
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                try:
                    key, value = line.strip().split('=', 1)
                    if key == 'BOT_TOKEN':
                        bot_token = value
                    elif key == 'CHAT_IDS':
                        chat_ids = [int(cid.strip()) for cid in value.split(',') if cid.strip()]
                    elif key == 'AUTHORIZED_USERS':
                        authorized_users = [int(uid.strip()) for uid in value.split(',') if uid.strip()]
                except ValueError:
                    continue
    return bot_token, chat_ids, authorized_users

def save_config(bot_token, chat_ids, authorized_users):
    with open(CONFIG_FILE, 'w') as f:
        f.write(f"BOT_TOKEN={bot_token}\n")
        f.write(f"CHAT_IDS={','.join(map(str, chat_ids))}\n")
        f.write(f"AUTHORIZED_USERS={','.join(map(str, authorized_users))}\n")

def get_estimated_time():
    if not os.path.exists(TIME_FILE):
        return DEFAULT_ESTIMATED_BUILD_TIME_SECONDS
    times = []
    try:
        with open(TIME_FILE, 'r') as f:
            for line in f:
                times.append(float(line.strip()))
    except (ValueError, IndexError):
        return DEFAULT_ESTIMATED_BUILD_TIME_SECONDS
    if not times:
        return DEFAULT_ESTIMATED_BUILD_TIME_SECONDS
    average_time = sum(times) / len(times)
    print(f"Usando tempo médio estimado de {int(average_time)}s com base nas últimas {len(times)} builds.")
    return average_time

def save_last_build_time(seconds):
    times = []
    if os.path.exists(TIME_FILE):
        try:
            with open(TIME_FILE, 'r') as f:
                for line in f:
                    times.append(float(line.strip()))
        except (ValueError, IndexError):
            times = []
    times.append(seconds)
    times_to_keep = times[-BUILD_HISTORY_COUNT:]
    with open(TIME_FILE, 'w') as f:
        for t in times_to_keep:
            f.write(f"{t}\n")

def upload_file(file_path):
    if not os.path.exists(file_path):
        print("Arquivo ZIP não encontrado para upload.")
        return None, "Arquivo não encontrado"
    try:
        print(f"\nEnviando Artefato ({os.path.basename(file_path)}) para o portal (0x0.st)...")
        command = ["curl", "-F", f"file=@{file_path}", "https://0x0.st"]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        download_link = result.stdout.strip()
        if download_link.startswith("http"):
            print(f"Portal retornou o link: {download_link}")
            return download_link, None
        else:
            print(f"Erro no upload: {download_link}")
            return None, "Resposta inesperada do portal."
    except subprocess.CalledProcessError as e:
        print(f"Erro no subprocesso de upload: {e.stderr}")
        return None, e.stderr

async def broadcast_message(bot: Bot, text: str, reply_markup=None):
    _, chat_ids, _ = load_config()
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
        except Exception as e:
            print(f"Não foi possível enviar para o chat {chat_id}: {e}")

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Agente de Campo ativado. Use /status para relatórios.")

async def addgroup(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para esta ação.")
        return
    bot_token, chat_ids, authorized_users = load_config()
    new_chat_id = update.message.chat_id
    if new_chat_id not in chat_ids:
        chat_ids.append(new_chat_id)
        save_config(bot_token, chat_ids, authorized_users)
        await update.message.reply_text(f"Posto avançado `{new_chat_id}` adicionado à rede.")
    else:
        await update.message.reply_text("Este posto avançado já está na rede de vigilância.")

async def removegroup(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para esta ação.")
        return
    bot_token, chat_ids, authorized_users = load_config()
    chat_id_to_remove = update.message.chat_id
    if chat_id_to_remove in chat_ids:
        chat_ids.remove(chat_id_to_remove)
        save_config(bot_token, chat_ids, authorized_users)
        await update.message.reply_text(f"Posto avançado `{chat_id_to_remove}` removido da rede.")
    else:
        await update.message.reply_text("Este posto avançado não está na rede de vigilância.")

async def grant_access(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para esta ação.")
        return
    try:
        user_id_to_grant = int(context.args[0])
        bot_token, chat_ids, authorized_users = load_config()
        if user_id_to_grant not in authorized_users:
            authorized_users.append(user_id_to_grant)
            save_config(bot_token, chat_ids, authorized_users)
            await update.message.reply_text(f"Permissão de status concedida ao usuário `{user_id_to_grant}`.")
        else:
            await update.message.reply_text(f"O usuário `{user_id_to_grant}` já possui permissão.")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: /grant <ID do usuário>")

async def revoke_access(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para esta ação.")
        return
    try:
        user_id_to_revoke = int(context.args[0])
        if user_id_to_revoke == owner_id:
            await update.message.reply_text("Não é possível revogar a permissão do dono do bot.")
            return
        bot_token, chat_ids, authorized_users = load_config()
        if user_id_to_revoke in authorized_users:
            authorized_users.remove(user_id_to_revoke)
            save_config(bot_token, chat_ids, authorized_users)
            await update.message.reply_text(f"Permissão de status revogada do usuário `{user_id_to_revoke}`.")
        else:
            await update.message.reply_text(f"O usuário `{user_id_to_revoke}` não possuía permissão.")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: /revoke <ID do usuário>")

async def status(update, context: ContextTypes.DEFAULT_TYPE):
    _, _, authorized_users = load_config()
    if update.effective_user.id not in authorized_users:
        await update.message.reply_text("Você não tem autorização para solicitar um relatório de status.")
        return
    with status_lock:
        if not build_status["running"]:
            await update.message.reply_text("Nenhum Ritual está em andamento.")
            return
        progress = build_status["progress"]
        k_name = clean_log_for_telegram(build_status["kernel_name"])
        elapsed_str = build_status["elapsed_str"]
        log_snippet_raw = build_status['log_snippet']
        log_snippet_for_code_block = clean_log_for_code_block(log_snippet_raw)
        progress_bar = '🟩' * int(progress / 10) + '🔲' * (10 - int(progress / 10))
        status_message = f"""
*🔥 Ritual em Andamento*
*📜 Artefato:* `{k_name}`

*📊 Progresso:* `[{progress_bar}] {progress:.1f}%`
*⏳ Tempo Decorrido:* `{elapsed_str}`

*👁️ Último Sinal Detectado:*
"""
        status_message += f"```\n{log_snippet_for_code_block}\n```"
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN_V2)

def run_build_and_monitor(bot: Bot, loop):
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    if os.path.exists(NAME_FILE): os.remove(NAME_FILE)
    estimated_time = get_estimated_time()
    process = subprocess.Popen(f"script -q --flush -c '{BUILD_SCRIPT}' {LOG_FILE}", shell=True, executable='/bin/bash')
    with status_lock:
        build_status["running"] = True
        build_status["start_time"] = time.time()
    kernel_name_found = False
    while process.poll() is None:
        if not kernel_name_found and os.path.exists(NAME_FILE):
            time.sleep(0.5) 
            try:
                with open(NAME_FILE, 'r') as f: kernel_name = f.read().strip()
                if kernel_name:
                    kernel_name_found = True
                    with status_lock: build_status["kernel_name"] = kernel_name
                    cleaned_kernel_name = clean_log_for_telegram(kernel_name)
                    start_message = f"⚠️ *Início do Ritual*\nA Manifestação do Artefato `{cleaned_kernel_name}` começou\."
                    asyncio.run_coroutine_threadsafe(broadcast_message(bot, start_message), loop)
                    os.remove(NAME_FILE)
            except FileNotFoundError: pass
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f: full_log = f.readlines()
            non_empty_lines = [line.strip() for line in full_log if line.strip()][-10:]
            with status_lock:
                elapsed = time.time() - build_status["start_time"]
                progress_percent = (elapsed / estimated_time) * 100 if estimated_time > 0 else 0
                build_status.update({
                    "progress": min(progress_percent, 99.9),
                    "elapsed_str": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
                    "log_snippet": "\n".join(non_empty_lines)
                })
        time.sleep(5)
    total_time = time.time() - build_status["start_time"]
    total_time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"
    if process.returncode == 0:
        save_last_build_time(total_time)
        zip_path = f"AnyKernel3/{build_status['kernel_name']}.zip"
        maintainer = "NerokiStage"
        build_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        localversion = "4.19.325-CALY-Madness/86e2319d"
        clang_version = "Proton-Clang"
        defconfig = "calamity_defconfig"
        kernelsu = "Incluído"
        selinux = "Enforcing"
        file_name = os.path.basename(zip_path)
        file_size = format_file_size(os.path.getsize(zip_path)) if os.path.exists(zip_path) else "N/A"
        sha256_sum = calculate_sha256(zip_path) if os.path.exists(zip_path) else "N/A"
        download_link, upload_error = upload_file(zip_path)
        reply_markup = None
        if download_link:
            custom_download_link = f"{download_link}/{file_name}"
            keyboard = [[InlineKeyboardButton("Baixar Artefato 📜", url=custom_download_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        final_kernel_name = clean_log_for_telegram(build_status['kernel_name'])
        final_maintainer = clean_log_for_telegram(maintainer)
        final_file_name = clean_log_for_telegram(file_name)
        msg = f"""
*✅ Ritual Concluído: {final_kernel_name}*

👤 *Mantenedor:* `{final_maintainer}`
⏱ *Duração:* `{total_time_str}`
🗓 *Finalizado em:* `{build_date}`

*🔧 Informações do Kernel:*
• *Localversion:* `{clean_log_for_telegram(localversion)}`
• *Clang:* `{clean_log_for_telegram(clang_version)}`
• *Defconfig:* `{clean_log_for_telegram(defconfig)}`
• *KernelSU:* `{clean_log_for_telegram(kernelsu)}`
• *SELinux:* `{clean_log_for_telegram(selinux)}`

*📦 Artefato Gerado:*
• *Arquivo:* `{final_file_name}`
• *Tamanho:* `{file_size}`
• *SHA256:* `{sha256_sum}`
"""
        if upload_error:
            cleaned_error = clean_log_for_telegram(upload_error)
            msg += f"\n*⚠️ Falha no Upload:* `{cleaned_error}`"
        asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg, reply_markup), loop)
    else:
        final_kernel_name = clean_log_for_telegram(build_status['kernel_name'])
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f: final_log = f.readlines()
        log_snip = clean_log_for_telegram("".join(final_log[-20:]))
        msg = f"""
*❌ A MEMBRANA SE ROMPEU*
*📜 Artefato:* `{final_kernel_name}`
*⏱ Tempo total:* `{total_time_str}`
*Últimos Sinais:*
{log_snip}
"""
        asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg), loop)
    with status_lock: build_status["running"] = False
    time.sleep(2)
    loop.call_soon_threadsafe(stop_event.set)

async def main():
    bot_token, chat_ids, authorized_users = load_config()
    if not bot_token:
        print(">>> Configuração inicial do Agente de Campo Digital...")
        bot_token = input("Cole aqui o seu BOT_TOKEN do BotFather: ")
        owner_id = int(input("Cole aqui o seu CHAT_ID pessoal do @userinfobot: "))
        chat_ids = [owner_id]
        authorized_users = [owner_id]
        save_config(bot_token, chat_ids, authorized_users)
        print("Credenciais salvas em .bot_env! Você não precisará digitá-las novamente.")
        bot_token, chat_ids, authorized_users = load_config()
    if chat_ids and not authorized_users:
        print("Detectado arquivo de configuração antigo. Atualizando com permissões de dono...")
        owner_id = chat_ids[0]
        authorized_users = [owner_id]
        save_config(bot_token, chat_ids, authorized_users)
        print(f"Usuário {owner_id} definido como dono e autorizado.")
    owner_id = authorized_users[0] if authorized_users else None
    application = Application.builder().token(bot_token).build()
    application.bot_data['owner_id'] = owner_id
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("addgroup", addgroup))
    application.add_handler(CommandHandler("removegroup", removegroup))
    application.add_handler(CommandHandler("grant", grant_access))
    application.add_handler(CommandHandler("revoke", revoke_access))
    loop = asyncio.get_running_loop()
    build_thread = threading.Thread(target=run_build_and_monitor, args=(application.bot, loop))
    global stop_event
    stop_event = asyncio.Event()
    print("\nAgente de Campo Digital ativado. O Ritual de Calamidade foi iniciado no terminal.")
    print("O bot está online no Telegram para receber comandos.")
    async with application:
        await application.start()
        await application.updater.start_polling()
        build_thread.start()
        await stop_event.wait()
        await application.updater.stop()
        await application.stop()
    build_thread.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRitual interrompido pelo Agente.")
