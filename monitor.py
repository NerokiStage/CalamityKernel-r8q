import os
import sys
import subprocess
import time
import asyncio
import threading
import re
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

DEFAULT_ESTIMATED_BUILD_TIME_SECONDS = 900
CONFIG_FILE = ".bot_env"
BUILD_SCRIPT = "./caly.sh"
LOG_FILE = "build.log"
NAME_FILE = ".kernel_name_tmp"
TIME_FILE = ".last_build_time"

build_status = {
    "running": False,
    "progress": 0.0,
    "elapsed_str": "0m 0s",
    "log_snippet": "Aguardando início...",
    "start_time": 0,
    "kernel_name": "N/A",
    "notified_50": False,
    "notified_99": False,
}
status_lock = threading.Lock()
stop_event = asyncio.Event()

def clean_log_snippet(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned_text = ansi_escape.sub('', text)
    return "".join(c for c in cleaned_text if c.isprintable() or c in '\n\t')

def load_config():
    bot_token = None
    chat_ids = []
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                if key == 'BOT_TOKEN':
                    bot_token = value
                elif key == 'CHAT_IDS':
                    chat_ids = [int(cid.strip()) for cid in value.split(',') if cid.strip()]
    return bot_token, chat_ids

def save_config(bot_token, chat_ids):
    with open(CONFIG_FILE, 'w') as f:
        f.write(f"BOT_TOKEN={bot_token}\n")
        f.write(f"CHAT_IDS={','.join(map(str, chat_ids))}\n")

async def broadcast_message(bot: Bot, text: str):
    _, chat_ids = load_config()
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"Não foi possível enviar para o chat {chat_id}: {e}")

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Agente de Campo ativado.\n"
        "Use `/status` para verificar o andamento.\n"
        "Adicione este bot a um grupo e use `/addgroup` para receber notificações lá."
    )

async def addgroup(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para modificar a rede de vigilância.")
        return

    new_chat_id = update.message.chat_id
    bot_token, chat_ids = load_config()
    if new_chat_id in chat_ids:
        await update.message.reply_text("Este posto avançado já está na rede de vigilância.")
    else:
        chat_ids.append(new_chat_id)
        save_config(bot_token, chat_ids)
        await update.message.reply_text(f"Posto avançado `{new_chat_id}` adicionado à rede com sucesso.")

async def status(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para solicitar um relatório de status.")
        return

    with status_lock:
        if not build_status["running"]:
            await update.message.reply_text("Nenhum Ritual está em andamento no momento.")
            return

        progress = build_status["progress"]
        progress_bar = '🌀' * int(progress / 10) + '◌' * (10 - int(progress / 10))
        log_snippet = clean_log_snippet(build_status['log_snippet'])
        
        status_message = f"""
*🔥 Ritual em Andamento...*

*📜 Artefato:* `{build_status['kernel_name']}`
*📊 Progresso:* `[{progress_bar}] {progress:.1f}%`
*⏳ Tempo Decorrido:* `{build_status['elapsed_str']}`

*👁️ Último Sinal Detectado:*
{log_snippet}

"""
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)

def get_estimated_time():
    if os.path.exists(TIME_FILE):
        with open(TIME_FILE, 'r') as f:
            try:
                return float(f.read().strip())
            except ValueError:
                return DEFAULT_ESTIMATED_BUILD_TIME_SECONDS
    return DEFAULT_ESTIMATED_BUILD_TIME_SECONDS

def save_last_build_time(seconds):
    with open(TIME_FILE, 'w') as f:
        f.write(str(seconds))

def run_build_and_monitor(bot: Bot, loop):
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    if os.path.exists(NAME_FILE): os.remove(NAME_FILE)
    
    estimated_time = get_estimated_time()

    process = subprocess.Popen(
        f"script -q --flush -c '{BUILD_SCRIPT}' {LOG_FILE}",
        shell=True, executable='/bin/bash'
    )
    
    with status_lock:
        build_status["running"] = True
        build_status["start_time"] = time.time()
    
    kernel_name_found = False
    while process.poll() is None:
        if not kernel_name_found and os.path.exists(NAME_FILE):
            time.sleep(0.5) 
            with open(NAME_FILE, 'r') as f:
                kernel_name = f.read().strip()
            if kernel_name:
                kernel_name_found = True
                with status_lock:
                    build_status["kernel_name"] = kernel_name
                start_message = f"⚠️ *Início do Ritual!*\nA Manifestação do Artefato `{kernel_name}` começou."
                asyncio.run_coroutine_threadsafe(broadcast_message(bot, start_message), loop)
                os.remove(NAME_FILE)

        full_log = []
        if os.path.exists(LOG_FILE):
             with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
                full_log = f.readlines()
        
        non_empty_lines = [line.strip() for line in full_log if line.strip()][-10:]

        with status_lock:
            elapsed = time.time() - build_status["start_time"]
            progress = min((elapsed / estimated_time) * 100, 99.9)
            build_status.update({
                "progress": progress,
                "elapsed_str": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
                "log_snippet": "\n".join(non_empty_lines)
            })
            
            if kernel_name_found and progress >= 50 and not build_status["notified_50"]:
                build_status["notified_50"] = True
                msg = f"⏳ *Ritual a 50%...* A Membrana está estável. Artefato: `{build_status['kernel_name']}`."
                asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg), loop)
            
            if kernel_name_found and progress >= 99 and not build_status["notified_99"]:
                build_status["notified_99"] = True
                msg = f"⏳ *Ritual a 99%...* Selando a energia. Artefato: `{build_status['kernel_name']}`."
                asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg), loop)
        
        time.sleep(5)
    
    total_time = time.time() - build_status["start_time"]
    total_time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"

    final_log = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            final_log = f.readlines()

    if process.returncode == 0:
        save_last_build_time(total_time)
        msg = f"""
*✅ Ritual Concluído com Sucesso!*
*Artefato:* `{build_status['kernel_name']}`
*Tempo total:* `{total_time_str}`
*Localização:* `AnyKernel3/{build_status['kernel_name']}.zip`

A Manifestação está completa.
"""
        asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg), loop)
    else:
        log_snip = clean_log_snippet("".join(final_log[-15:]))
        msg = f"""
*❌ A MEMBRANA SE ROMPEU!*
*Artefato:* `{build_status['kernel_name']}`
*Tempo total:* `{total_time_str}`

*Últimos Sinais:*
{log_snip}

"""
        asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg), loop)

    with status_lock:
        build_status["running"] = False
    
    time.sleep(2)
    loop.call_soon_threadsafe(stop_event.set)


async def main():
    bot_token, chat_ids = load_config()
    
    if not bot_token or not chat_ids:
        print(">>> Configuração inicial do Agente de Campo Digital...")
        bot_token = input("Cole aqui o seu BOT_TOKEN do BotFather: ")
        chat_id = input("Cole aqui o seu CHAT_ID pessoal do @userinfobot: ")
        chat_ids = [int(chat_id)]
        save_config(bot_token, chat_ids)
        print("Credenciais salvas em .bot_env! Você não precisará digitá-las novamente.")

    application = Application.builder().token(bot_token).build()
    
    owner_id = chat_ids[0] if chat_ids else None
    application.bot_data['owner_id'] = owner_id

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("addgroup", addgroup))

    loop = asyncio.get_running_loop()
    build_thread = threading.Thread(target=run_build_and_monitor, args=(application.bot, loop))
    build_thread.start()
    
    global stop_event
    stop_event = asyncio.Event()

    print("\nAgente de Campo Digital ativado. O Ritual de Calamidade foi iniciado no terminal.")
    print("O bot está online no Telegram para receber comandos /status.")
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        await stop_event.wait()
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        
    build_thread.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRitual interrompido pelo Agente.")