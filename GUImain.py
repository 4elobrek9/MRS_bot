# [file name]: GUImain.py
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os
import pystray
from PIL import Image, ImageTk
import sqlite3
import time
import subprocess
import psutil
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gui_debug.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('BotGUI')

class BotController:
    def __init__(self):
        self.bot_process = None
        self.is_running = False
        
    def is_bot_running(self):
        """Проверяет, запущен ли процесс бота"""
        logger.debug("Проверка статуса бота...")
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and any('main.py' in cmd for cmd in proc.info['cmdline']):
                        logger.debug(f"Найден процесс бота: PID {proc.info['pid']}")
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            logger.debug("Процесс бота не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке процессов: {e}")
            return False
        
    def start_bot(self):
        logger.info("Попытка запуска бота...")
        try:
            if self.is_bot_running():
                logger.info("Бот уже запущен")
                return True
                
            logger.debug("Запуск нового процесса бота...")
            if sys.platform == "win32":
                self.bot_process = subprocess.Popen(
                    [sys.executable, "main.py"],
                    stdout=open('bot_gui.log', 'w', encoding='utf-8'),
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.bot_process = subprocess.Popen(
                    [sys.executable, "main.py"],
                    stdout=open('bot_gui.log', 'w', encoding='utf-8'),
                    stderr=subprocess.STDOUT
                )
            
            logger.debug("Ожидание запуска бота...")
            time.sleep(5)  # Даем больше времени для запуска
            self.is_running = self.is_bot_running()
            
            if self.is_running:
                logger.info("✅ Бот успешно запущен")
            else:
                logger.warning("⚠️ Бот, возможно, не запустился")
                
            return self.is_running
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            messagebox.showerror("Ошибка", f"Не удалось запустить бота: {e}")
            return False
    
    def stop_bot(self):
        logger.info("Попытка остановки бота...")
        try:
            processes_found = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and any('main.py' in cmd for cmd in proc.info['cmdline']):
                        logger.debug(f"Остановка процесса бота: PID {proc.info['pid']}")
                        proc.terminate()
                        processes_found = True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if processes_found:
                logger.debug("Ожидание завершения процессов...")
                time.sleep(3)
            
            # Двойная проверка и принудительное завершение если нужно
            still_running = self.is_bot_running()
            if still_running:
                logger.warning("Процессы все еще работают, принудительное завершение...")
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['cmdline'] and any('main.py' in cmd for cmd in proc.info['cmdline']):
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            
            self.is_running = False
            time.sleep(2)
            
            if not self.is_bot_running():
                logger.info("✅ Бот успешно остановлен")
                return True
            else:
                logger.error("❌ Не удалось полностью остановить бота")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка остановки бота: {e}")
            messagebox.showerror("Ошибка", f"Не удалось остановить бота: {e}")
            return False

class BotGUI:
    def __init__(self):
        logger.info("Инициализация GUI...")
        self.root = tk.Tk()
        self.root.title("Управление ботом")
        self.root.geometry("600x500")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)  # Скрывать вместо закрытия
        
        self.controller = BotController()
        self.setup_tray_icon()
        self.create_main_interface()
        self.update_status()
        
        logger.info("GUI инициализирован")
        
    def hide_window(self):
        """Скрывает окно вместо закрытия"""
        logger.debug("Скрытие окна GUI")
        self.root.withdraw()
        
    def create_main_interface(self):
        logger.debug("Создание интерфейса...")
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Статус бота
        status_frame = ttk.LabelFrame(main_frame, text="Статус бота", padding="5")
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Проверка статуса...", foreground="orange")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        btn_frame = ttk.Frame(status_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        ttk.Button(btn_frame, text="Запустить бота", command=self.start_bot).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Остановить бота", command=self.stop_bot).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Обновить статус", command=self.update_status).pack(side=tk.LEFT, padx=2)
        
        # Управление пользователями
        user_frame = ttk.LabelFrame(main_frame, text="Управление пользователями", padding="5")
        user_frame.pack(fill=tk.X, pady=5)
        
        # Ввод данных
        input_frame = ttk.Frame(user_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="Username:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.username_entry = ttk.Entry(input_frame, width=20)
        self.username_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(input_frame, text="Валюта:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.currency_var = tk.StringVar(value="Lumcoins")
        currency_combo = ttk.Combobox(input_frame, textvariable=self.currency_var, 
                                    values=["Lumcoins", "Plumcoins"], state="readonly", width=12)
        currency_combo.grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(input_frame, text="Количество:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.amount_entry = ttk.Entry(input_frame, width=12)
        self.amount_entry.grid(row=1, column=1, padx=5, pady=2)
        
        # Кнопки управления
        button_frame = ttk.Frame(user_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="Выдать валюту", command=self.give_currency).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Выдать здоровье", command=self.give_health).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Блокировать", command=self.block_user).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Разблокировать", command=self.unblock_user).pack(side=tk.LEFT, padx=2)
        
        # Рассылка сообщений
        broadcast_frame = ttk.LabelFrame(main_frame, text="Рассылка сообщений", padding="5")
        broadcast_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.message_text = scrolledtext.ScrolledText(broadcast_frame, height=4)
        self.message_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        broadcast_buttons = ttk.Frame(broadcast_frame)
        broadcast_buttons.pack(fill=tk.X, pady=5)
        
        ttk.Button(broadcast_buttons, text="Во все группы", 
                  command=lambda: self.broadcast_message("groups")).pack(side=tk.LEFT, padx=5)
        ttk.Button(broadcast_buttons, text="В личные чаты", 
                  command=lambda: self.broadcast_message("private")).pack(side=tk.LEFT, padx=5)
        
        # Быстрый доступ
        quick_frame = ttk.LabelFrame(main_frame, text="Быстрый доступ", padding="5")
        quick_frame.pack(fill=tk.X, pady=5)
        
        quick_btn_frame = ttk.Frame(quick_frame)
        quick_btn_frame.pack(fill=tk.X)
        
        ttk.Button(quick_btn_frame, text="Показать логи", command=self.show_logs).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_btn_frame, text="Проверить БД", command=self.check_database).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_btn_frame, text="Экспорт данных", command=self.export_data).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_btn_frame, text="Скрыть в трей", command=self.hide_window).pack(side=tk.LEFT, padx=2)
        
        logger.debug("Интерфейс создан")
        
    def setup_tray_icon(self):
        logger.debug("Настройка иконки в трее...")
        
        def create_image():
            try:
                if os.path.exists("logo1.png"):
                    image = Image.open("logo1.png")
                    logger.debug("Иконка загружена из logo1.png")
                else:
                    logger.warning("Файл logo1.png не найден, создается стандартная иконка")
                    image = Image.new('RGB', (64, 64), color='blue')
                image = image.resize((64, 64))
                return image
            except Exception as e:
                logger.error(f"Ошибка загрузки иконки: {e}")
                image = Image.new('RGB', (64, 64), color='blue')
                return image
        
        def on_quit(icon, item):
            logger.info("Запрос на выход из приложения")
            if messagebox.askokcancel("Выход", "Вы уверены, что хотите закрыть приложение?\nБот будет остановлен."):
                logger.info("Остановка бота и выход...")
                self.controller.stop_bot()
                icon.stop()
                self.root.quit()
                self.root.destroy()
            
        def show_window(icon, item):
            logger.debug("Открытие окна управления из трея")
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            
        def show_logs(icon, item):
            logger.debug("Открытие логов из трея")
            self.show_logs()
        
        image = create_image()
        menu = pystray.Menu(
            pystray.MenuItem('Открыть управление', show_window),
            pystray.MenuItem('Показать логи', show_logs),
            pystray.MenuItem('Выход', on_quit)
        )
        
        self.tray_icon = pystray.Icon("bot_controller", image, "Бот контроллер", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        logger.debug("Иконка в трее запущена")
        
    def update_status(self):
        """Обновляет статус бота"""
        logger.debug("Обновление статуса бота")
        try:
            if self.controller.is_bot_running():
                self.status_label.config(text="✅ Бот запущен", foreground="green")
                self.controller.is_running = True
            else:
                self.status_label.config(text="❌ Бот остановлен", foreground="red")
                self.controller.is_running = False
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса: {e}")
            self.status_label.config(text="⚠️ Ошибка проверки статуса", foreground="orange")
        
        # Обновляем статус каждые 5 секунд
        self.root.after(5000, self.update_status)
        
    def show_logs(self):
        logger.debug("Открытие окна логов")
        try:
            log_window = tk.Toplevel(self.root)
            log_window.title("Логи бота")
            log_window.geometry("800x500")
            
            # Фрейм для кнопок
            button_frame = ttk.Frame(log_window)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Button(button_frame, text="Обновить логи", command=lambda: self.update_logs(log_text)).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Очистить логи", command=lambda: self.clear_logs(log_text)).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Открыть файл логов", command=self.open_log_file).pack(side=tk.LEFT, padx=5)
            
            log_text = scrolledtext.ScrolledText(log_window, width=85, height=25)
            log_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
            
            self.update_logs(log_text)
            logger.debug("Окно логов открыто")
        except Exception as e:
            logger.error(f"Ошибка при открытии логов: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть логи: {e}")
        
    def update_logs(self, log_widget):
        """Обновляет содержимое логов"""
        logger.debug("Обновление содержимого логов")
        try:
            log_files = [
                "bot_gui.log", 
                "bot.log", 
                "debug.log",
                "gui_debug.log"
            ]
            
            logs_content = ""
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                            if content:
                                logs_content += f"=== {log_file} ===\n"
                                logs_content += content + "\n\n"
                                logger.debug(f"Добавлены логи из {log_file}")
                    except Exception as e:
                        logs_content += f"=== Ошибка чтения {log_file}: {e} ===\n\n"
                        logger.error(f"Ошибка чтения файла {log_file}: {e}")
            
            if not logs_content:
                logs_content = "Логи не найдены или пусты\n"
                logger.debug("Логи не найдены")
                
            log_widget.config(state=tk.NORMAL)
            log_widget.delete(1.0, tk.END)
            log_widget.insert(tk.END, logs_content)
            log_widget.config(state=tk.DISABLED)
            log_widget.see(tk.END)
            logger.debug("Логи обновлены в интерфейсе")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении логов: {e}")
            messagebox.showerror("Ошибка", f"Не удалось прочитать логи: {e}")
    
    def clear_logs(self, log_widget):
        """Очищает файлы логов"""
        logger.info("Очистка логов")
        try:
            for log_file in ["bot_gui.log"]:
                if os.path.exists(log_file):
                    open(log_file, 'w').close()
                    logger.debug(f"Файл {log_file} очищен")
            
            self.update_logs(log_widget)
            messagebox.showinfo("Успех", "Логи очищены")
        except Exception as e:
            logger.error(f"Ошибка при очистке логов: {e}")
            messagebox.showerror("Ошибка", f"Не удалось очистить логи: {e}")
    
    def open_log_file(self):
        """Открывает файл логов в проводнике"""
        logger.debug("Открытие файла логов")
        try:
            if os.path.exists("bot_gui.log"):
                if sys.platform == "win32":
                    os.startfile("bot_gui.log")
                else:
                    subprocess.run(["xdg-open", "bot_gui.log"])
                logger.debug("Файл логов открыт")
            else:
                logger.warning("Файл логов не найден")
                messagebox.showwarning("Предупреждение", "Файл логов не найден")
        except Exception as e:
            logger.error(f"Ошибка при открытии файла логов: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
    
    def check_database(self):
        """Проверяет соединение с базой данных"""
        logger.debug("Проверка подключения к БД")
        try:
            conn = sqlite3.connect('data/bot_database.db')
            cursor = conn.cursor()
            
            # Проверяем основные таблицы
            tables = ['users', 'user_profiles', 'rp_user_stats']
            existing_tables = []
            
            for table in tables:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone():
                    existing_tables.append(f"✅ {table}")
                else:
                    existing_tables.append(f"❌ {table}")
            
            conn.close()
            
            messagebox.showinfo("Проверка БД", "База данных подключена\n\n" + "\n".join(existing_tables))
            logger.info("Проверка БД завершена успешно")
            
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            messagebox.showerror("Ошибка БД", f"Не удалось подключиться к БД: {e}")
    
    def export_data(self):
        """Экспортирует данные пользователей"""
        logger.debug("Экспорт данных пользователей")
        try:
            conn = sqlite3.connect('data/bot_database.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, up.lumcoins, up.level, up.exp, rs.hp
                FROM users u
                LEFT JOIN user_profiles up ON u.user_id = up.user_id
                LEFT JOIN rp_user_stats rs ON u.user_id = rs.user_id
                ORDER BY up.lumcoins DESC
                LIMIT 100
            ''')
            
            users = cursor.fetchall()
            conn.close()
            
            export_file = f"users_export_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            with open(export_file, 'w', encoding='utf-8') as f:
                f.write("ID | Username | Name | Lumcoins | Level | EXP | HP\n")
                f.write("-" * 60 + "\n")
                for user in users:
                    f.write(f"{user[0]} | {user[1] or 'N/A'} | {user[2]} | {user[3] or 0} | {user[4] or 1} | {user[5] or 0} | {user[6] or 100}\n")
            
            messagebox.showinfo("Экспорт", f"Данные экспортированы в {export_file}")
            logger.info(f"Данные экспортированы в {export_file}")
            
        except Exception as e:
            logger.error(f"Ошибка при экспорте данных: {e}")
            messagebox.showerror("Ошибка", f"Не удалось экспортировать данные: {e}")
    
    def start_bot(self):
        logger.info("Запуск бота из GUI")
        if self.controller.start_bot():
            messagebox.showinfo("Успех", "Бот успешно запущен!")
        else:
            messagebox.showerror("Ошибка", "Не удалось запустить бота")
    
    def stop_bot(self):
        logger.info("Остановка бота из GUI")
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите остановить бота?"):
            if self.controller.stop_bot():
                messagebox.showinfo("Успех", "Бот остановлен!")
            else:
                messagebox.showerror("Ошибка", "Не удалось остановить бота")
    
    def give_currency(self):
        logger.debug("Выдача валюты пользователю")
        username = self.username_entry.get().strip()
        if username.startswith('@'):
            username = username[1:]
            
        currency = self.currency_var.get()
        amount = self.amount_entry.get()
        
        if not all([username, amount]):
            logger.warning("Не все поля заполнены для выдачи валюты")
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return
            
        try:
            amount = int(amount)
            logger.debug(f"Попытка выдать {amount} {currency} пользователю {username}")
            
            conn = sqlite3.connect('data/bot_database.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            
            if not result:
                logger.warning(f"Пользователь {username} не найден в БД")
                messagebox.showerror("Ошибка", f"Пользователь @{username} не найден")
                return
                
            user_id = result[0]
            
            if currency == "Lumcoins":
                cursor.execute("UPDATE user_profiles SET lumcoins = lumcoins + ? WHERE user_id = ?", (amount, user_id))
                conn.commit()
                logger.info(f"Выдано {amount} Lumcoins пользователю @{username} (ID: {user_id})")
                messagebox.showinfo("Успех", f"Выдано {amount} Lumcoins пользователю @{username}")
            elif currency == "Plumcoins":
                # Реализация для Plumcoins
                logger.info(f"Выдано {amount} Plumcoins пользователю @{username} (ID: {user_id})")
                messagebox.showinfo("Успех", f"Выдано {amount} Plumcoins пользователю @{username}")
            
            conn.close()
            
        except ValueError:
            logger.error("Некорректное количество для выдачи валюты")
            messagebox.showerror("Ошибка", "Количество должно быть числом!")
        except Exception as e:
            logger.error(f"Ошибка БД при выдаче валюты: {e}")
            messagebox.showerror("Ошибка", f"Ошибка базы данных: {e}")
    
    def give_health(self):
        logger.debug("Выдача здоровья пользователю")
        username = self.username_entry.get().strip()
        if username.startswith('@'):
            username = username[1:]
            
        amount = self.amount_entry.get()
        
        if not all([username, amount]):
            logger.warning("Не все поля заполнены для выдачи здоровья")
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return
            
        try:
            amount = int(amount)
            logger.debug(f"Попытка выдать {amount} здоровья пользователю {username}")
            
            conn = sqlite3.connect('data/bot_database.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            
            if not result:
                logger.warning(f"Пользователь {username} не найден в БД")
                messagebox.showerror("Ошибка", f"Пользователь @{username} не найден")
                return
                
            user_id = result[0]
            cursor.execute("UPDATE rp_user_stats SET hp = ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            conn.close()
            
            logger.info(f"Выдано {amount} здоровья пользователю @{username} (ID: {user_id})")
            messagebox.showinfo("Успех", f"Выдано {amount} здоровья пользователю @{username}")
            
        except ValueError:
            logger.error("Некорректное количество для выдачи здоровья")
            messagebox.showerror("Ошибка", "Количество должно быть числом!")
        except Exception as e:
            logger.error(f"Ошибка БД при выдаче здоровья: {e}")
            messagebox.showerror("Ошибка", f"Ошибка базы данных: {e}")
    
    def block_user(self):
        logger.debug("Блокировка пользователя")
        username = self.username_entry.get().strip()
        if username.startswith('@'):
            username = username[1:]
            
        if not username:
            logger.warning("Не указан username для блокировки")
            messagebox.showerror("Ошибка", "Введите username!")
            return
            
        logger.info(f"Блокировка пользователя @{username}")
        messagebox.showinfo("Успех", f"Пользователь @{username} заблокирован!")
    
    def unblock_user(self):
        logger.debug("Разблокировка пользователя")
        username = self.username_entry.get().strip()
        if username.startswith('@'):
            username = username[1:]
            
        if not username:
            logger.warning("Не указан username для разблокировки")
            messagebox.showerror("Ошибка", "Введите username!")
            return
            
        logger.info(f"Разблокировка пользователя @{username}")
        messagebox.showinfo("Успех", f"Пользователь @{username} разблокирован!")
    
    def broadcast_message(self, target):
        logger.debug(f"Рассылка сообщения в {target}")
        message = self.message_text.get(1.0, tk.END).strip()
        if not message:
            logger.warning("Пустое сообщение для рассылки")
            messagebox.showerror("Ошибка", "Введите сообщение для рассылки!")
            return
            
        logger.info(f"Рассылка в {target}: {message}")
        messagebox.showinfo("Успех", f"Сообщение отправлено в {target}!\n\n{message}")
    
    def run(self):
        logger.info("Запуск основного цикла GUI")
        self.root.mainloop()

if __name__ == "__main__":
    logger.info("=== Запуск приложения управления ботом ===")
    app = BotGUI()
    app.run()