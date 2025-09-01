import os
import sys
import subprocess
import time
import asyncio
import threading
import re
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# --- CONFIGURAÇÕES ---
DEFAULT_ESTIMATED_BUILD_TIME_SECONDS = 900
CONFIG_FILE = ".bot_env"
BUILD_SCRIPT = "./caly.sh"
LOG_FILE = "build.log"
NAME_FILE = ".kernel_name_tmp"
TIME_FILE = ".last_build_time"

# --- ESTADO GLOBAL DA BUILD ---
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

# --- FUNÇÕES AUXILIARES ---

def clean_log_for_telegram(text):
    """Purifica os Sinais para evitar anomalias de formatação no Telegram."""
    # Remove códigos de cor ANSI
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned_text = ansi_escape.sub('', text)
    # Escapa caracteres que conflitam com MarkdownV2
    # Itens a escapar: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    cleaned_text = re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', cleaned_text)
    return cleaned_text

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

def get_estimated_time():
    if os.path.exists(TIME_FILE):
        with open(TIME_FILE, 'r') as f:
            try: return float(f.read().strip())
            except (ValueError, IndexError): pass
    return DEFAULT_ESTIMATED_BUILD_TIME_SECONDS

def save_last_build_time(seconds):
    with open(TIME_FILE, 'w') as f:
        f.write(str(seconds))

def upload_file(file_path):
    """Usa um portal confiável (0x0.st) que mantém o nome do arquivo."""
    if not os.path.exists(file_path):
        print("Arquivo ZIP não encontrado para upload.")
        return None, "Arquivo não encontrado"
    try:
        print(f"\nEnviando Artefato ({os.path.basename(file_path)}) para o portal (0x0.st)...")
        command = f"curl -F'file=@{file_path}' https://0x0.st"
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        download_link = result.stdout.strip()
        if download_link.startswith("http"):
            print(f"Portal retornou o link: {download_link}")
            return download_link, None
        else:
            return None, "Resposta inesperada do portal."
    except subprocess.CalledProcessError as e:
        return None, e.stderr

# --- FUNÇÕES DO TELEGRAM (THREAD DO BOT) ---

async def broadcast_message(bot: Bot, text: str, reply_markup=None):
    _, chat_ids = load_config()
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
        await update.message.reply_text("Você não tem autorização para modificar a rede de vigilância.")
        return
    new_chat_id, bot_token, chat_ids = update.message.chat_id, *load_config()
    if new_chat_id not in chat_ids:
        chat_ids.append(new_chat_id)
        save_config(bot_token, chat_ids)
        await update.message.reply_text(f"Posto avançado `{new_chat_id}` adicionado à rede.")
    else:
        await update.message.reply_text("Este posto avançado já está na rede de vigilância.")

async def status(update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get('owner_id')
    if update.effective_user.id != owner_id:
        await update.message.reply_text("Você não tem autorização para solicitar um relatório de status.")
        return
    with status_lock:
        if not build_status["running"]:
            await update.message.reply_text("Nenhum Ritual está em andamento.")
            return
        progress, k_name, elapsed_str = build_status["progress"], build_status["kernel_name"], build_status["elapsed_str"]
        progress_bar = '🌀' * int(progress / 10) + '◌' * (10 - int(progress / 10))
        log_snippet = clean_log_for_telegram(build_status['log_snippet'])
        
        status_message = f"""
*🔥 Ritual em Andamento*
*📜 Artefato:* `{k_name}`
*📊 Progresso:* `[{progress_bar}] {progress:.1f}%`
*⏳ Tempo Decorrido:* `{elapsed_str}`
*👁️ Último Sinal Detectado:*
{log_snippet}

"""
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN_V2)

# --- FUNÇÃO PRINCIPAL DA BUILD (THREAD DE TRABALHO) ---

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
                    start_message = f"⚠️ *Início do Ritual*\nA Manifestação do Artefato `{kernel_name}` começou\."
                    asyncio.run_coroutine_threadsafe(broadcast_message(bot, start_message), loop)
                    os.remove(NAME_FILE)
            except FileNotFoundError: pass

        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f: full_log = f.readlines()
            non_empty_lines = [line.strip() for line in full_log if line.strip()][-10:]
            with status_lock:
                elapsed = time.time() - build_status["start_time"]
                build_status.update({
                    "progress": min((elapsed / estimated_time) * 100, 99.9),
                    "elapsed_str": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
                    "log_snippet": "\n".join(non_empty_lines)
                })
        time.sleep(5)
    
    total_time = time.time() - build_status["start_time"]
    total_time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"

    if process.returncode == 0:
        save_last_build_time(total_time)
        zip_path = f"AnyKernel3/{build_status['kernel_name']}.zip"
        download_link, upload_error = upload_file(zip_path)
        
        reply_markup = None
        if download_link:
            keyboard = [[InlineKeyboardButton("Baixar Artefato 📜", url=download_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

        msg = f"""
*✅ Ritual Concluído com Sucesso*
*Artefato:* `{build_status['kernel_name']}`
*Tempo total:* `{total_time_str}`
*Localização:* `{zip_path}`
"""
        if upload_error: msg += f"\n*Falha no Upload:* `{upload_error}`"
        asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg, reply_markup), loop)
    else:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f: final_log = f.readlines()
        log_snip = clean_log_for_telegram("".join(final_log[-20:]))
        msg = f"""
*❌ A MEMBRANA SE ROMPEU*
*Artefato:* `{build_status['kernel_name']}`
*Tempo total:* `{total_time_str}`
*Últimos Sinais:*
{log_snip}

"""
        asyncio.run_coroutine_threadsafe(broadcast_message(bot, msg), loop)

    with status_lock: build_status["running"] = False
    time.sleep(2)
    loop.call_soon_threadsafe(stop_event.set)

# --- INICIALIZAÇÃO ---

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
    application.bot_data['owner_id'] = chat_ids[0] if chat_ids else None
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("addgroup", addgroup))

    loop = asyncio.get_running_loop()
    build_thread = threading.Thread(target=run_build_and_monitor, args=(application.bot, loop))
    
    global stop_event
    stop_event = asyncio.Event()

    print("\nAgente de Campo Digital ativado. O Ritual de Calamidade foi iniciado no terminal.")
    print("O bot está online no Telegram para receber comandos /status.")
    
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