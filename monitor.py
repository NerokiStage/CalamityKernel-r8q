import os
import sys
import subprocess
import time
import threading
from telegram import Bot, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext

ESTIMATED_BUILD_TIME_SECONDS = 900
CONFIG_FILE = ".bot_env"
BUILD_SCRIPT = "./caly.sh"

build_status = {
    "running": False,
    "progress": 0.0,
    "elapsed_str": "0m 0s",
    "log_snippet": "Aguardando início...",
    "start_time": 0,
    "kernel_name": "N/A"
}
status_lock = threading.Lock()

def start(update, context):
    update.message.reply_text(
        "Agente de Campo Digital ativado. Pronto para monitorar o Ritual.\n"
        "Use /status para verificar o andamento de uma compilação."
    )

def status(update, context):
    with status_lock:
        if not build_status["running"]:
            update.message.reply_text("Nenhum Ritual está em andamento no momento.")
            return

        progress = build_status["progress"]
        progress_bar = '█' * int(progress / 10) + '░' * (10 - int(progress / 10))
        
        status_message = f"""
*⚙️ Ritual em Andamento...*
*Artefato:* `{build_status['kernel_name']}`
*Progresso (estimado):* `[{progress_bar}] {progress:.1f}%`
*Tempo decorrido:* `{build_status['elapsed_str']}`

*Último Sinal:*
```
{build_status['log_snippet']}
```
"""
    update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)

def send_message(bot, chat_id, text):
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def run_build(bot, chat_id, kernel_name):
    start_time = time.time()
    with status_lock:
        build_status["running"] = True
        build_status["start_time"] = start_time
        build_status["kernel_name"] = kernel_name

    start_message = f"""
*⚠️ Início do Ritual de Calamidade*
*Artefato:* `{kernel_name}`
*Alvo:* `r8q`

A Manifestação começou. Use /status para atualizações.
"""
    send_message(bot, chat_id, start_message)

    full_log = []
    try:
        process = subprocess.Popen(
            BUILD_SCRIPT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            executable='/bin/bash',
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            if line:
                print(line)
                full_log.append(line)
                
                with status_lock:
                    elapsed_time = time.time() - build_status["start_time"]
                    build_status["progress"] = min((elapsed_time / ESTIMATED_BUILD_TIME_SECONDS) * 100, 99.9)
                    build_status["elapsed_str"] = f"{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s"
                    build_status["log_snippet"] = "\n".join(full_log[-5:])

        process.wait()

        end_time = time.time()
        total_time = end_time - start_time
        total_time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"

        if process.returncode == 0:
            success_message = f"""
*✅ Ritual Concluído com Sucesso!*
*Artefato:* `{kernel_name}`
*Tempo total:* `{total_time_str}`
*Localização:* `AnyKernel3/{kernel_name}.zip`

A Manifestação está completa e selada.
"""
            send_message(bot, chat_id, success_message)
        else:
            last_log_lines = "\n".join(full_log[-15:])
            failure_message = f"""
*❌ A MEMBRANA SE ROMPEU!*
*Artefato:* `{kernel_name}`
*Tempo total:* `{total_time_str}`
*O Ritual foi corrompido.*

*Últimos Sinais recebidos:*
```
{last_log_lines}
```
"""
            send_message(bot, chat_id, failure_message)

    except Exception as e:
        error_message = f"*🔥 ANOMALIA CRÍTICA!*\nO Agente de Campo digital falhou: ```{str(e)}```"
        send_message(bot, chat_id, error_message)
    finally:
        with status_lock:
            build_status["running"] = False

def setup_and_run():
    bot_token = None
    chat_id = None
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                if key == 'BOT_TOKEN':
                    bot_token = value
                elif key == 'CHAT_ID':
                    chat_id = value
    
    if not bot_token or not chat_id:
        print(">>> Configuração inicial do Agente de Campo Digital...")
        bot_token = input("Cole aqui o seu BOT_TOKEN do BotFather: ")
        chat_id = input("Cole aqui o seu CHAT_ID do @userinfobot: ")
        with open(CONFIG_FILE, 'w') as f:
            f.write(f"BOT_TOKEN={bot_token}\n")
            f.write(f"CHAT_ID={chat_id}\n")
        print("Credenciais salvas em .bot_env! Você não precisará digitá-las novamente.")

    kernel_name = input(">>> Insira o codinome para esta Manifestação de Calamidade: ")
    if not kernel_name:
        kernel_name = f"Calamidade-{time.strftime('%Y%m%d')}"

    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("status", status))

    build_thread = threading.Thread(target=run_build, args=(updater.bot, chat_id, kernel_name))
    build_thread.start()

    print("\nAgente de Campo Digital ativado. Monitorando o Ritual no Telegram...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    setup_and_run()
